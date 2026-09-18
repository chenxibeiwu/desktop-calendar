from __future__ import annotations

from dataclasses import replace
from datetime import date

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import lunar
from .grid import Metrics, MonthGrid, metrics_for
from .layout import build_month, shift_month
from .qtutil import apply_stylesheet, qcolor
from .store import TaskStore
from .theme import Palette

HEADER_H = 60
HINT_H = 22
PANEL_MARGIN = 18          # 卡片外留给阴影的空间
CARD_RADIUS = 16.0


class CalendarPanel(QWidget):
    hideRequested = Signal()
    quitRequested = Signal()
    settingsChanged = Signal()

    def __init__(self, store: TaskStore, settings, palette: Palette) -> None:
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint,
        )
        self.store = store
        self.settings = settings
        self.palette_ = palette
        self.metrics = metrics_for(settings.size_preset)
        self.view_year, self.view_month = date.today().year, date.today().month
        self._backdrop_pixmap = None
        self._settings_popup = None
        self._add_popup = None

        self.setWindowTitle("桌面月历")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            20 + PANEL_MARGIN, 14 + PANEL_MARGIN, 20 + PANEL_MARGIN, 16 + PANEL_MARGIN
        )
        root.setSpacing(6)

        header = QWidget(self)
        header.setFixedHeight(HEADER_H)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 0, 0, 0)
        header_layout.setSpacing(10)

        self.accent_dot = _Dot(header)
        header_layout.addWidget(self.accent_dot, 0, Qt.AlignVCenter)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(1)
        self.title_label = QLabel(header)
        title_font = QFont("Microsoft YaHei UI", 20)
        title_font.setWeight(QFont.DemiBold)
        self.title_label.setFont(title_font)
        self.subtitle_label = QLabel(header)
        sub_font = QFont("Microsoft YaHei UI", 10)
        self.subtitle_label.setFont(sub_font)
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        header_layout.addLayout(titles)
        header_layout.addStretch(1)

        self.add_button = self._make_button("＋", "添加日程（可设每天/每周几）", circle=True)
        self.add_button.setProperty("accent", True)
        self.prev_button = self._make_button("‹", "上个月", circle=True)
        self.next_button = self._make_button("›", "下个月", circle=True)
        self.today_button = self._make_button("今天", "回到今天")
        self.menu_button = self._make_button("☰", "设置", circle=True)
        for button in (
            self.add_button,
            self.prev_button,
            self.next_button,
            self.today_button,
            self.menu_button,
        ):
            header_layout.addWidget(button)

        root.addWidget(header)

        self.grid = MonthGrid(self.metrics, palette, self)
        root.addWidget(self.grid)

        self.hint_label = QLabel(self)
        hint_font = QFont("Microsoft YaHei UI", 10)
        self.hint_label.setFont(hint_font)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setText(
            "点日期格直接输入待办 · 点 ＋ 可加每天/每周的日程 · 拖任务条右端拉长"
        )
        root.addWidget(self.hint_label)

        self.prev_button.clicked.connect(lambda: self.go_month(-1))
        self.next_button.clicked.connect(lambda: self.go_month(1))
        self.today_button.clicked.connect(self.go_today)
        self.add_button.clicked.connect(self.open_add_schedule)
        self.menu_button.clicked.connect(self.open_settings)

        self.apply_style()
        self.refresh()

    # ------------------------------------------------------------- 几何

    def card_size(self) -> QSize:
        width = self.metrics.panel_width
        height = 14 + HEADER_H + 6 + self.grid.grid_height() + 6 + HINT_H + 12
        return QSize(width, height)

    def preferred_size(self) -> QSize:
        card = self.card_size()
        return QSize(card.width() + PANEL_MARGIN * 2, card.height() + PANEL_MARGIN * 2)

    def card_rect(self) -> QRect:
        card = self.card_size()
        return QRect(PANEL_MARGIN, PANEL_MARGIN, card.width(), card.height())

    # ------------------------------------------------------------- 外观

    def _make_button(self, text: str, tip: str, circle: bool = False) -> QPushButton:
        button = QPushButton(text, self)
        button.setToolTip(tip)
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedHeight(32)
        if circle:
            button.setFixedWidth(32)
            button.setProperty("round", True)
        else:
            button.setMinimumWidth(58)
        return button

    def apply_style(self) -> None:
        palette = self.palette_
        self.setFont(QFont("Microsoft YaHei UI", 13))
        self.title_label.setStyleSheet(
            f"color: {palette.header_text}; background: transparent;"
        )
        self.subtitle_label.setStyleSheet(
            f"color: {palette.text_muted}; background: transparent;"
        )
        self.hint_label.setStyleSheet(
            f"color: {palette.text_muted}; background: transparent;"
        )
        self.accent_dot.set_color(palette.accent)
        hover_accent = QColor(palette.accent).lighter(114).name()
        apply_stylesheet(
            self,
            f"""
            QPushButton {{
                background: {palette.button_bg};
                border: none;
                border-radius: 10px;
                color: {palette.button_text};
                padding: 0px 12px;
                font-family: "Microsoft YaHei UI";
                font-size: 13px;
            }}
            QPushButton[round="true"] {{
                border-radius: 16px;
                padding: 0px;
                font-size: 16px;
            }}
            QPushButton[accent="true"] {{
                background: {palette.accent};
                color: {palette.accent_text};
            }}
            QPushButton[accent="true"]:hover {{
                background: {hover_accent};
            }}
            QPushButton:hover {{ background: {palette.button_bg_hover}; }}
            QPushButton:pressed {{ background: {palette.accent_soft}; }}
            """
        )
        self.grid.set_palette_obj(palette)

    def set_palette_obj(self, palette: Palette) -> None:
        self.palette_ = palette
        self.apply_style()
        self.update()

    def set_metrics(self, preset: str) -> None:
        self.metrics = metrics_for(preset)
        self.grid.apply_metrics(self.metrics)
        self.refresh()

    def set_backdrop_pixmap(self, pixmap) -> None:
        self._backdrop_pixmap = pixmap
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        card = QRectF(self.card_rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        self._paint_shadow(painter, card)

        path = QPainterPath()
        path.addRoundedRect(card, CARD_RADIUS, CARD_RADIUS)
        painter.setClipPath(path)

        mode = self.settings.backdrop
        if mode == "frosted" and self._backdrop_pixmap is not None:
            if not self._backdrop_pixmap.isNull():
                painter.drawPixmap(self.card_rect(), self._backdrop_pixmap)

        tint = qcolor("#%02x%02x%02x" % self.palette_.tint)
        alpha = 1.0 if mode == "solid" else max(0.25, min(1.0, self.settings.opacity))
        tint.setAlphaF(alpha)
        painter.fillPath(path, tint)

        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(qcolor(self.palette_.card_border), 1))
        painter.drawRoundedRect(card, CARD_RADIUS, CARD_RADIUS)
        painter.end()

    def _paint_shadow(self, painter: QPainter, card: QRectF) -> None:
        strength = self.palette_.shadow_alpha
        outer = QPainterPath()
        outer.addRect(QRectF(self.rect()))
        inner = QPainterPath()
        inner.addRoundedRect(card, CARD_RADIUS, CARD_RADIUS)
        painter.setClipPath(outer.subtracted(inner))
        painter.setPen(Qt.NoPen)
        steps = 22
        for index in range(steps, 0, -1):
            ratio = index / steps
            alpha = strength * 0.062 * (1.0 - ratio) ** 1.5
            if alpha < 0.003:
                continue
            color = QColor(0, 0, 0)
            color.setAlphaF(alpha)
            painter.setBrush(color)
            radius = CARD_RADIUS + index
            rect = card.adjusted(-index, -index + 3, index, index + 3)
            painter.drawRoundedRect(rect, radius, radius)
        painter.setClipping(False)

    # ------------------------------------------------------------- 数据

    def refresh(self) -> None:
        tasks = self.store.tasks
        model = build_month(self.view_year, self.view_month, tasks)
        metrics = self._fitted_metrics(len(model.weeks))
        if metrics != self.metrics:
            self.metrics = metrics
            self.grid.apply_metrics(metrics)
        self.grid.apply_model(model, tasks)
        self.grid.set_lunar_enabled(self.settings.show_lunar)
        self.title_label.setText(f"{model.year}年{model.month}月")
        today = date.today()
        text = f"今天 {today.month}月{today.day}日"
        lunar_text = lunar.today_lunar_text(today)
        if self.settings.show_lunar and lunar_text:
            text += f" · {lunar_text}"
        if not self._is_current_month():
            count = len(
                [
                    t
                    for t in tasks
                    if t.start <= date(self.view_year, self.view_month, 28)
                    and t.end >= date(self.view_year, self.view_month, 1)
                ]
            )
            text = f"{model.title} · {count} 项任务"
        self.subtitle_label.setText(text)
        self.setFixedSize(self.preferred_size())
        self.update()

    def _is_current_month(self) -> bool:
        today = date.today()
        return (self.view_year, self.view_month) == (today.year, today.month)

    def _fitted_metrics(self, rows: int) -> Metrics:
        base = metrics_for(self.settings.size_preset)
        from PySide6.QtGui import QGuiApplication

        screen = (
            QGuiApplication.screenAt(self.frameGeometry().center())
            or QGuiApplication.primaryScreen()
        )
        avail = (screen.availableGeometry().height() if screen else 900) - 40
        fixed = (
            14
            + HEADER_H
            + 6
            + 6
            + HINT_H
            + 12
            + PANEL_MARGIN * 2
            + base.pad * 2
            + base.weekday_h
        )
        room = avail - fixed
        if rows <= 0 or room <= 0:
            return base
        max_row = room / rows
        if max_row >= base.row_h:
            return base
        scale = max(0.55, max_row / base.row_h)
        return replace(
            base,
            row_h=int(base.row_h * scale),
            chip_h=max(14, int(base.chip_h * scale)),
            chip_gap=2 if scale < 0.9 else base.chip_gap,
            day_num_h=max(15, int(base.day_num_h * scale)),
            day_font=max(11, int(base.day_font * scale)),
            chip_font=max(10, int(base.chip_font * scale)),
            lunar_font=max(8, int(base.lunar_font * scale)),
            weekday_font=max(9, int(base.weekday_font * scale)),
        )

    def go_month(self, delta: int) -> None:
        self.view_year, self.view_month = shift_month(self.view_year, self.view_month, delta)
        self.refresh()

    def go_today(self) -> None:
        today = date.today()
        self.view_year, self.view_month = today.year, today.month
        self.refresh()

    # ------------------------------------------------------------- 设置

    def open_settings(self) -> None:
        from .popups import SettingsPopup

        if self._settings_popup is None:
            self._settings_popup = SettingsPopup(self, self.settings, self.palette_, self)
            self._settings_popup.changed.connect(self.settingsChanged.emit)
        else:
            self._settings_popup.settings = self.settings
            self._settings_popup.set_palette_obj(self.palette_)
            self._settings_popup.sync()
        button_rect = self.menu_button.rect()
        anchor = self.menu_button.mapToGlobal(QPoint(button_rect.left(), button_rect.bottom()))
        self._settings_popup.place_below(anchor)
        self._settings_popup.show()
        self._settings_popup.raise_()

    def _default_day(self) -> date:
        """添加日程时默认填的日期：本月就用今天，翻到别的月就用 1 号。"""
        today = date.today()
        if self._is_current_month():
            return today
        return date(self.view_year, self.view_month, 1)

    def open_add_schedule(self) -> None:
        from .popups import AddSchedulePopup

        if self._add_popup is None:
            self._add_popup = AddSchedulePopup(self.store, self.palette_, self)
            self._add_popup.added.connect(self._on_schedule_added)
        else:
            self._add_popup.apply_palette(self.palette_)
        self._add_popup.reset(self._default_day())
        button_rect = self.add_button.rect()
        anchor = self.add_button.mapToGlobal(QPoint(button_rect.left(), button_rect.bottom()))
        self._add_popup.place_below(anchor)
        self._add_popup.show()
        self._add_popup.raise_()
        self._add_popup.title_edit.setFocus(Qt.PopupFocusReason)

    def _on_schedule_added(self, _count: int) -> None:
        self.refresh()

    # ------------------------------------------------------------- 事件

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hideRequested.emit()
            return
        if event.key() == Qt.Key_PageUp:
            self.go_month(-1)
            return
        if event.key() == Qt.Key_PageDown:
            self.go_month(1)
            return
        super().keyPressEvent(event)

    def popup_open(self) -> bool:
        popups = [self._settings_popup, self._add_popup]
        return any(p is not None and p.isVisible() for p in popups)

    def close_popups(self) -> None:
        for popup in (self._settings_popup, self._add_popup):
            if popup is not None and popup.isVisible():
                popup.close()

    def inline_open(self) -> bool:
        return self.grid._inline.isVisible()


class _Dot(QWidget):
    """标题左边的小圆点，用主题色。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = "#4A7DFF"

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolor(self._color))
        painter.drawEllipse(QRectF(2.0, 2.0, 8.0, 8.0))
        painter.end()


_ = QPointF
