from __future__ import annotations

import time
from datetime import date

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import paths, settings as settings_mod, theme, winapi
from .panel import PANEL_MARGIN, CalendarPanel
from .popups import DayListPopup, TaskEditor
from .store import TaskStore

POLL_MS = 80


def _blur_pixmap(pixmap, rounds: int = 3):
    """逐级对半缩小再逐级放大，得到平滑的模糊。

    直接一次性缩小 8~12 倍时，双线性采样只看邻近像素，会留下明显的马赛克。
    """
    image = pixmap
    done = 0
    for _ in range(rounds):
        width = max(1, image.width() // 2)
        height = max(1, image.height() // 2)
        if width < 4 or height < 4:
            break
        image = image.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        done += 1
    for _ in range(done):
        if image.width() >= pixmap.width():
            break
        image = image.scaled(
            min(pixmap.width(), image.width() * 2),
            min(pixmap.height(), image.height() * 2),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
    if image.size() != pixmap.size():
        image = image.scaled(pixmap.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return image


def render_icon_pixmap(palette: theme.Palette, size: int = 64) -> QPixmap:
    """画一个日历小图标，任意尺寸都按比例缩放。"""
    unit = size / 64.0

    def s(value: float) -> int:
        return int(round(value * unit))

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    accent = QColor(palette.accent)
    margin = s(4)
    radius = s(14)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#f2f4f8"))
    painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, radius, radius)
    painter.setBrush(accent)
    path = QPainterPath()
    path.addRoundedRect(margin, margin, size - margin * 2, size - margin * 2, radius, radius)
    painter.setClipPath(path)
    painter.drawRect(margin, margin, size - margin * 2, s(20))
    painter.setClipping(False)
    painter.setPen(QPen(QColor("#c9cfdb"), max(1.0, s(2))))
    for i in range(1, 3):
        y = s(30 + i * 10)
        painter.drawLine(s(12), y, size - s(12), y)
    for i in range(1, 4):
        x = s(12 + i * 10)
        painter.drawLine(x, s(30), x, size - s(12))
    painter.setPen(QPen(QColor("#e0575f"), max(1.0, s(3))))
    painter.drawLine(s(14), s(30), s(22), s(30))
    painter.end()
    return pixmap


def make_icon(palette: theme.Palette) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_icon_pixmap(palette, size))
    return icon


class DesktopCalendar(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.settings = settings_mod.load()
        self.store = TaskStore()
        self.store.load()
        self.store.auto_merge = self.settings.merge_same_title
        self.palette = self._resolve_palette()

        self.panel = CalendarPanel(self.store, self.settings, self.palette)
        self.editor = TaskEditor(self.store, self.palette, self.panel)
        self.day_popup = DayListPopup(self.store, self.palette, self.panel)

        self._hiding = False
        self._dwell = 0
        self._backdrop_applied_for: int | None = None
        self._anim: QPropertyAnimation | None = None
        self._last_interaction = time.monotonic()
        app.installEventFilter(self)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_panel)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)

        self._wire()
        self._build_tray()

        # 跨零点时自动刷新到今天
        self.day_check = QTimer(self)
        self.day_check.setInterval(60_000)
        self.day_check.timeout.connect(self._check_day_change)
        self._today = date.today()

    # ------------------------------------------------------------------ 初始化

    def _resolve_palette(self) -> theme.Palette:
        mode = self.settings.theme
        if mode == "auto":
            mode = "dark" if theme.system_prefers_dark() else "light"
        return theme.build(mode, self.settings.accent)

    def _wire(self) -> None:
        grid = self.panel.grid
        grid.taskCreated.connect(self._on_task_created)
        grid.taskActivated.connect(self._on_task_activated)
        grid.taskToggled.connect(self._on_task_toggled)
        grid.taskMoved.connect(self._on_task_moved)
        grid.taskResized.connect(self._on_task_resized)
        grid.overflowActivated.connect(self._on_overflow)

        self.editor.changed.connect(self.panel.refresh)
        self.editor.deleted.connect(lambda _id: self.panel.refresh())
        self.day_popup.taskPicked.connect(self._on_task_activated)
        self.panel.hideRequested.connect(self.hide_panel)
        self.panel.quitRequested.connect(self.quit)
        self.panel.settingsChanged.connect(self._on_settings_changed)

    def _build_tray(self) -> None:
        self.icon = make_icon(self.palette)
        self.app.setWindowIcon(self.icon)
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("桌面月历 · 把鼠标移到屏幕右边缘呼出")
        self.tray.activated.connect(self._on_tray_activated)
        self._tray_menu: QMenu | None = None
        self.tray.setContextMenu(self._make_tray_menu())
        self.tray.show()

    def _make_tray_menu(self) -> QMenu:
        menu = QMenu()
        show_action = QAction("呼出月历", menu)
        show_action.triggered.connect(lambda: self.show_panel(instant=True))
        menu.addAction(show_action)
        hide_action = QAction("收起", menu)
        hide_action.triggered.connect(self.hide_panel)
        menu.addAction(hide_action)
        menu.addSeparator()
        today_action = QAction("回到今天", menu)
        today_action.triggered.connect(self.panel.go_today)
        menu.addAction(today_action)
        folder_action = QAction("打开数据文件夹", menu)
        folder_action.triggered.connect(lambda: winapi.open_folder(str(paths.data_dir())))
        menu.addAction(folder_action)
        uninstall_action = QAction("退出", menu)
        uninstall_action.triggered.connect(self.quit)
        menu.addAction(uninstall_action)
        self._tray_menu = menu
        return menu

    def start(self) -> None:
        # 首次运行时把数据文件建出来，用户打开「文档\桌面月历」能直接看到
        settings_mod.save(self.settings)
        self.store.save()
        self.timer.start()
        self.day_check.start()
        self._notify_first_run()

    def _notify_first_run(self) -> None:
        flag = paths.data_dir() / ".welcomed"
        marker = "tips-v1"
        if flag.exists():
            try:
                if flag.read_text(encoding="utf-8").strip() == marker:
                    return
            except Exception:
                pass
        try:
            flag.write_text(marker, encoding="utf-8")
        except Exception:
            pass
        QTimer.singleShot(400, lambda: self.show_panel(instant=True))
        QTimer.singleShot(7000, self.hide_panel)
        self.tray.showMessage(
            "桌面月历已经在运行",
            "把鼠标移到屏幕最右边，月历就会滑出来；鼠标移开它自己会收起。\n"
            "右下角托盘里的小图标可以随时呼出或退出。",
            QSystemTrayIcon.Information,
            8000,
        )

    # ------------------------------------------------------------------ 数据

    def _on_task_created(self, title: str, day: date) -> None:
        accent = theme.ACCENTS.get(self.settings.accent)
        color = accent.default_chip if accent else "blue"
        self.store.add(title, day, color=color)
        self.panel.refresh()

    def _on_task_activated(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task is None:
            return
        from PySide6.QtGui import QCursor

        self.hide_timer.stop()
        self.editor.show_for(task, QCursor.pos())

    def _on_task_toggled(self, task_id: str) -> None:
        self.store.toggle_done(task_id)
        self.panel.refresh()

    def _on_task_moved(self, task_id: str, delta: int) -> None:
        self.store.move(task_id, delta)
        self.panel.refresh()

    def _on_task_resized(self, task_id: str, start: date, end: date) -> None:
        self.store.update(task_id, start=start, end=end)
        self.panel.refresh()

    def _on_overflow(self, day: date) -> None:
        from PySide6.QtGui import QCursor

        self.hide_timer.stop()
        self.day_popup.show_for(day, QCursor.pos())

    def _on_settings_changed(self) -> None:
        self.palette = self._resolve_palette()
        self.store.auto_merge = self.settings.merge_same_title
        self.panel.set_metrics(self.settings.size_preset)
        self.panel.set_palette_obj(self.palette)
        self.editor.apply_palette(self.palette)
        self.day_popup.apply_palette(self.palette)
        self.icon = make_icon(self.palette)
        self.app.setWindowIcon(self.icon)
        self.tray.setIcon(self.icon)
        self.panel.refresh()
        self._backdrop_applied_for = None
        if self.panel.isVisible():
            area = self._area()
            x_vis, _x_hid, y = self._geometry(area)
            self.panel.move(x_vis, y)
            self._apply_backdrop()
        settings_mod.save(self.settings)

    def _check_day_change(self) -> None:
        today = date.today()
        if today != self._today:
            self._today = today
            self.panel.refresh()

    # ------------------------------------------------------------------ 窗口

    def _area(self) -> QRect:
        from PySide6.QtGui import QCursor

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _panel_y(self, area: QRect, size: QSize) -> int:
        margin = self.settings.vertical_margin
        align = self.settings.vertical_align
        if align == "top":
            return area.top() + margin
        if align == "bottom":
            return area.bottom() - size.height() - margin
        return area.top() + max(0, (area.height() - size.height()) // 2)

    def _card_geometry(self, area: QRect):
        """返回 (卡片左上角x, 卡片左上角y, 卡片尺寸, 窗口收起时的x)。"""
        card = self.panel.card_size()
        y_card = self._panel_y(area, card)
        if self.settings.edge == "left":
            return area.left(), y_card, card, area.left() - card.width() - PANEL_MARGIN * 2
        return area.right() + 1 - card.width(), y_card, card, area.right() + 1

    def _geometry(self, area: QRect) -> tuple[int, int, int]:
        x_card, y_card, _card, x_hidden = self._card_geometry(area)
        return x_card - PANEL_MARGIN, x_hidden, y_card - PANEL_MARGIN

    def _in_hot_zone(self, pos: QPoint, area: QRect) -> bool:
        width = max(1, self.settings.trigger_width)
        if self.settings.edge == "left":
            if pos.x() > area.left() + width - 1:
                return False
        else:
            if pos.x() < area.right() - width + 1:
                return False
        _x, y_card, card, _hidden = self._card_geometry(area)
        return y_card - 40 <= pos.y() <= y_card + card.height() + 40

    def _apply_backdrop(self) -> None:
        hwnd = int(self.panel.winId())
        if self._backdrop_applied_for == hwnd:
            return
        self._backdrop_applied_for = hwnd
        winapi.set_dark_titlebar(hwnd, self.palette.name == "dark")
        # 磨砂效果由我们自己模糊背后画面来做，系统自带的 acrylic 会把整块面板压成不透明。
        winapi.clear_acrylic(hwnd)

    def _grab_backdrop(self) -> None:
        """抓取面板将要覆盖的那块桌面并做模糊，作为面板的磨砂背景。"""
        if self.settings.backdrop != "frosted":
            self.panel.set_backdrop_pixmap(None)
            return
        area = self._area()
        x_card, y_card, card, _hidden = self._card_geometry(area)
        screen = (
            QGuiApplication.screenAt(QPoint(x_card + card.width() // 2, y_card))
            or QGuiApplication.primaryScreen()
        )
        if screen is None:
            return
        geometry = screen.geometry()
        local_x = x_card - geometry.x()
        local_y = y_card - geometry.y()
        piece = screen.grabWindow(0, local_x, local_y, card.width(), card.height())
        if piece.isNull():
            return
        ratio = piece.devicePixelRatio() or 1.0
        blurred = _blur_pixmap(piece)
        blurred.setDevicePixelRatio(ratio)
        self.panel.set_backdrop_pixmap(blurred)

    def show_panel(self, instant: bool = False) -> None:
        self._hiding = False
        self.hide_timer.stop()
        area = self._area()
        x_vis, x_hid, y = self._geometry(area)
        self.panel.setFixedSize(self.panel.preferred_size())
        if self.panel.isVisible():
            self.panel.move(x_vis, y)
            self.panel.raise_()
            return
        self._grab_backdrop()
        self.panel.move(x_hid, y)
        self.panel.show()
        self.panel.raise_()
        self._apply_backdrop()
        duration = 0 if instant else self.settings.animation_ms
        self._animate(QPoint(x_hid, y), QPoint(x_vis, y), duration, QEasingCurve.OutCubic)

    def hide_panel(self) -> None:
        if not self.panel.isVisible() or self._hiding:
            return
        # 正在输入的内容先存下来，再收起，避免白打字
        self.panel.grid.commit_inline()
        self._close_popups()
        self._hiding = True
        area = self._area()
        _x_vis, x_hid, y = self._geometry(area)
        self._animate(self.panel.pos(), QPoint(x_hid, y), self.settings.animation_ms, QEasingCurve.InCubic)

    def _animate(self, start: QPoint, end: QPoint, duration: int, easing) -> None:
        if duration <= 0:
            self.panel.move(end)
            if not self.panel.isVisible():
                self.panel.show()
            return
        self._anim = QPropertyAnimation(self.panel, b"pos", self)
        self._anim.setDuration(duration)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(easing)
        self._anim.finished.connect(self._on_anim_finished)
        self._anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _on_anim_finished(self) -> None:
        if self._hiding and self.panel.isVisible():
            self.panel.hide()
        self._hiding = False

    def _close_popups(self) -> None:
        if self.editor.isVisible():
            self.editor.close()
        if self.day_popup.isVisible():
            self.day_popup.close()
        self.panel.close_popups()

    def _pinned(self) -> bool:
        idle = time.monotonic() - self._last_interaction
        if self.editor.isVisible() or self.day_popup.isVisible() or self.panel.popup_open():
            # 一直在点、一直在打字就不收；人走了（鼠标在外面 + 好一会儿没动作）就收
            return idle < 6.0
        if self.panel.inline_open():
            # 输入框是空的：说明只是在看，别拦着月历收起
            if not self.panel.grid.inline_text().strip():
                return False
            return idle < 4.0
        return False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            self._last_interaction = time.monotonic()
        return False

    # ------------------------------------------------------------------ 轮询

    def _poll(self) -> None:
        from PySide6.QtGui import QCursor

        pos = QCursor.pos()
        area = self._area()
        shown = self.panel.isVisible() and not self._hiding

        if shown:
            if self._pinned():
                self.hide_timer.stop()
                return
            grown = QRect(
                self.panel.x() - 4,
                self.panel.y() - 6,
                self.panel.width() + 8,
                self.panel.height() + 12,
            )
            if grown.contains(pos) or self._in_hot_zone(pos, area):
                self.hide_timer.stop()
            elif not self.hide_timer.isActive():
                delay = max(150, self.settings.hide_delay_ms)
                if self.panel.inline_open() and not self.panel.grid.inline_text().strip():
                    # 输入框是空的，人一走就马上收，不用等
                    delay = 150
                self.hide_timer.start(delay)
            return

        self.hide_timer.stop()
        if self._in_hot_zone(pos, area):
            self._dwell += POLL_MS
            if self._dwell >= max(0, self.settings.dwell_ms):
                self._dwell = 0
                self.show_panel()
        else:
            self._dwell = 0

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            if self.panel.isVisible():
                self.hide_panel()
            else:
                self.show_panel(instant=True)

    def quit(self) -> None:
        settings_mod.save(self.settings)
        self.store.purge_empty()
        self.timer.stop()
        self.tray.hide()
        self.app.quit()
