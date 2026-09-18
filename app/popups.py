from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QEvent, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .qtutil import apply_stylesheet, qcolor
from .store import Task, TaskStore
from .theme import ACCENT_ORDER, ACCENTS, CHIP_LABELS, CHIP_ORDER, Palette, chip_color


def _popup_qss(palette: Palette) -> str:
    text = palette.text
    dim = palette.text_muted
    field_bg = palette.button_bg
    field_border = palette.grid_line
    hover = palette.button_bg_hover
    return f"""
    QWidget {{
        color: {text};
        font-family: "Microsoft YaHei UI";
        font-size: 13px;
    }}
    QLineEdit, QDateEdit {{
        background: {field_bg};
        border: 1px solid {field_border};
        border-radius: 6px;
        padding: 4px 8px;
        color: {text};
        selection-background-color: {palette.today_ring};
    }}
    QDateEdit {{ font-size: 12px; padding: 4px 4px; }}
    QLineEdit:focus, QDateEdit:focus {{
        border: 1px solid {palette.today_ring};
    }}
    QDateEdit::drop-down {{
        border: none;
        width: 20px;
    }}
    QDateEdit::up-button, QDateEdit::down-button {{
        width: 0px;
        border: none;
    }}
    QCalendarWidget QWidget {{ alternate-background-color: {field_bg}; }}
    QCalendarWidget QAbstractItemView {{
        selection-background-color: {palette.today_ring};
        selection-color: #ffffff;
        background: {field_bg};
        color: {text};
    }}
    QPushButton {{
        background: {field_bg};
        border: 1px solid {field_border};
        border-radius: 6px;
        padding: 5px 12px;
        color: {text};
    }}
    QPushButton:hover {{ background: {hover}; }}
    QCheckBox {{ color: {text}; spacing: 7px; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px;
        border-radius: 4px;
        border: 1px solid {palette.text_muted};
        background: transparent;
    }}
    QCheckBox::indicator:checked {{
        background: {palette.accent};
        border: 1px solid {palette.accent};
    }}
    QLabel#hint {{ color: {dim}; font-size: 11px; }}
    """


class PopupBase(QWidget):
    SHADOW_INSET = 0

    def __init__(self, palette: Palette, parent=None) -> None:
        # 这里刻意不做成独立窗口，而是直接嵌在月历窗口里当浮层。
        # 独立窗口（Qt.Popup / Qt.Tool）在 Windows 上会另起一个输入上下文，
        # 中文输入法经常挂不上去，只能打英文；做成浮层就跟格子里的输入框一样了。
        super().__init__(parent)
        self.palette_ = palette
        self.setAutoFillBackground(False)
        apply_stylesheet(self, _popup_qss(palette))

    def global_rect(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.raise_()
        window = self.window()
        if window is not None:
            # 保证月历窗口在前台，中文输入法才会跟着走
            window.activateWindow()

    def hideEvent(self, event) -> None:  # noqa: N802
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """自己实现「点外面就关掉」，代替 Qt.Popup 的鼠标独占。"""
        if not self.isVisible():
            return False
        # 比如日期控件弹出来的小日历，它自己是个弹窗，先让它工作
        active_popup = QApplication.activePopupWidget()
        if active_popup is not None and active_popup.isVisible():
            return False
        kind = event.type()
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            try:
                position = event.globalPosition().toPoint()
            except AttributeError:
                return False
            if not self.global_rect().contains(position):
                if kind == QEvent.MouseButtonPress:
                    self.close()
                return True
        elif kind == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.close()
            return True
        return False

    def apply_palette(self, palette: Palette) -> None:
        self.palette_ = palette
        apply_stylesheet(self, _popup_qss(palette))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        inset = float(self.SHADOW_INSET)
        radius = 12.0 if inset else 10.0
        card = QRectF(self.rect()).adjusted(
            inset + 0.5, inset + 0.5, -(inset + 0.5), -(inset + 0.5)
        )
        if inset:
            outer = QPainterPath()
            outer.addRect(QRectF(self.rect()))
            inner = QPainterPath()
            inner.addRoundedRect(card, radius, radius)
            painter.setClipPath(outer.subtracted(inner))
            painter.setPen(Qt.NoPen)
            for index in range(int(inset), 0, -1):
                alpha = 0.55 * 0.12 * (1 - index / inset) ** 1.6
                color = QColor(0, 0, 0)
                color.setAlphaF(alpha)
                painter.setBrush(color)
                painter.drawRoundedRect(
                    QRectF(self.rect()).adjusted(
                        inset - index,
                        inset - index + 2,
                        -(inset - index),
                        -(inset - index) + 2,
                    ),
                    radius + index,
                    radius + index,
                )
            painter.setClipping(False)
        bg = qcolor("#%02x%02x%02x" % self.palette_.tint)
        bg.setAlphaF(0.985)
        painter.setPen(QPen(qcolor(self.palette_.card_border), 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(card, radius, radius)
        painter.end()

    def place_near(self, anchor: QPoint) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        size = self.sizeHint()
        self.resize(size)
        local = parent.mapFromGlobal(anchor)
        x = local.x() - self.width() - 10
        if x < 8:
            x = local.x() + 10
        y = local.y() - 24
        x = max(8, min(x, parent.width() - self.width() - 8))
        y = max(8, min(y, parent.height() - self.height() - 8))
        self.move(x, y)

    def place_below(self, anchor: QPoint) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        width = max(self.sizeHint().width(), self.minimumWidth())
        height = max(self.sizeHint().height(), self.minimumHeight())
        self.resize(width, height)
        width = self.width()
        height = self.height()
        local = parent.mapFromGlobal(anchor)
        x = local.x() - width + 60
        y = local.y() + 8
        x = max(8, min(x, parent.width() - width - 8))
        y = max(8, min(y, parent.height() - height - 8))
        self.move(x, y)


class TaskEditor(PopupBase):
    changed = Signal()
    deleted = Signal(str)

    def __init__(self, store: TaskStore, palette: Palette, parent=None) -> None:
        super().__init__(palette, parent)
        self.store = store
        self.task: Task | None = None
        self._loading = False
        self._color = "blue"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("要做什么？")
        self.title_edit.setMinimumWidth(300)
        font = QFont("Microsoft YaHei UI", 14)
        self.title_edit.setFont(font)
        layout.addWidget(self.title_edit)

        dates = QHBoxLayout()
        dates.setSpacing(8)
        dates.addWidget(QLabel("开始", self))
        self.start_edit = QDateEdit(self)
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_edit.setDate(QDate.currentDate())
        self.start_edit.setMinimumWidth(132)
        self.start_edit.setAlignment(Qt.AlignCenter)
        dates.addWidget(self.start_edit)
        dates.addSpacing(6)
        dates.addWidget(QLabel("结束", self))
        self.end_edit = QDateEdit(self)
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_edit.setDate(QDate.currentDate())
        self.end_edit.setMinimumWidth(132)
        self.end_edit.setAlignment(Qt.AlignCenter)
        dates.addWidget(self.end_edit)
        dates.addStretch(1)
        layout.addLayout(dates)

        colors = QHBoxLayout()
        colors.setSpacing(6)
        colors.addWidget(QLabel("颜色", self))
        self._swatches: dict[str, QPushButton] = {}
        for name in CHIP_ORDER:
            button = QPushButton("", self)
            button.setFixedSize(22, 22)
            button.setToolTip(CHIP_LABELS.get(name, name))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, n=name: self._set_color(n))
            colors.addWidget(button)
            self._swatches[name] = button
        colors.addStretch(1)
        layout.addLayout(colors)

        self.done_box = QCheckBox("已完成", self)
        layout.addWidget(self.done_box)

        buttons = QHBoxLayout()
        self.delete_button = QPushButton("删除", self)
        self.delete_button.clicked.connect(self._delete)
        self.close_button = QPushButton("完成", self)
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        hint = QLabel("提示：直接拖动横条的右端可以拉长到多天；拖动中间可以整体挪到别的日期。", self)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        hint.setMaximumWidth(300)
        layout.addWidget(hint)

        self.title_edit.textEdited.connect(self._on_title)
        self.title_edit.editingFinished.connect(self._on_title)
        self.start_edit.dateChanged.connect(self._on_dates)
        self.end_edit.dateChanged.connect(self._on_dates)
        self.done_box.toggled.connect(self._on_done)

    # -------------------------------------------------------------- 数据

    def load(self, task: Task) -> None:
        self._loading = True
        self.task = task
        self._color = task.color if task.color in CHIP_ORDER else "blue"
        self.title_edit.setText(task.title)
        self.start_edit.setDate(QDate(task.start.year, task.start.month, task.start.day))
        self.end_edit.setDate(QDate(task.end.year, task.end.month, task.end.day))
        self.done_box.setChecked(task.done)
        self._refresh_swatches()
        self._loading = False

    def show_for(self, task: Task, anchor: QPoint) -> None:
        self.load(task)
        self.place_near(anchor)
        self.title_edit.setFocus(Qt.PopupFocusReason)
        self.title_edit.selectAll()
        self.show()

    # -------------------------------------------------------------- 事件

    def _on_title(self) -> None:
        if self._loading or self.task is None:
            return
        title = self.title_edit.text().strip()
        if title == self.task.title:
            return
        self.store.update(self.task.id, title=title)
        self.changed.emit()

    def _on_dates(self) -> None:
        if self._loading or self.task is None:
            return
        start = self.start_edit.date().toPython()
        end = self.end_edit.date().toPython()
        if end < start:
            if self.sender() is self.start_edit:
                end = start
                self._loading = True
                self.end_edit.setDate(self.start_edit.date())
                self._loading = False
            else:
                start = end
                self._loading = True
                self.start_edit.setDate(self.end_edit.date())
                self._loading = False
        self.store.update(self.task.id, start=start, end=end)
        self.changed.emit()

    def _on_done(self, checked: bool) -> None:
        if self._loading or self.task is None:
            return
        self.store.update(self.task.id, done=checked)
        self.changed.emit()

    def _set_color(self, name: str) -> None:
        if self.task is None:
            return
        self._color = name
        self.store.update(self.task.id, color=name)
        self._refresh_swatches()
        self.changed.emit()

    def _refresh_swatches(self) -> None:
        for name, button in self._swatches.items():
            color = chip_color(self.palette_, name)
            border = (
                f"2px solid {self.palette_.text}"
                if name == self._color
                else "1px solid rgba(255,255,255,0.28)"
            )
            button.setStyleSheet(
                f"QPushButton {{ background: {color}; border: {border}; border-radius: 11px; }}"
            )

    def _delete(self) -> None:
        if self.task is None:
            return
        task_id = self.task.id
        self.store.remove(task_id)
        self.close()
        self.deleted.emit(task_id)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.title_edit.hasFocus():
            self._on_title()
            self.close()
            return
        super().keyPressEvent(event)


class DayListPopup(PopupBase):
    """点「+N」时列出当天的全部任务。"""

    taskPicked = Signal(str)

    def __init__(self, store: TaskStore, palette: Palette, parent=None) -> None:
        super().__init__(palette, parent)
        self.store = store
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 12, 14, 12)
        self.layout_.setSpacing(6)
        self.head = QLabel(self)
        font = QFont("Microsoft YaHei UI", 13)
        font.setBold(True)
        self.head.setFont(font)
        self.layout_.addWidget(self.head)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(5)
        self.layout_.addWidget(self.body)
        self.setMinimumWidth(230)

    def show_for(self, day: date, anchor: QPoint) -> None:
        self.head.setText(f"{day.month}月{day.day}日")
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        tasks = sorted(self.store.on_day(day), key=lambda t: (t.done, t.title))
        if not tasks:
            label = QLabel("这天没有任务", self.body)
            self.body_layout.addWidget(label)
        for task in tasks:
            span = ""
            if task.days > 1:
                span = f"（{task.start.strftime('%m/%d')} - {task.end.strftime('%m/%d')}）"
            text = f"{task.title or '（空）'}{span}"
            button = QPushButton(text, self.body)
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            color = chip_color(self.palette_, task.color)
            accent = QColor(color).name()
            button.setStyleSheet(
                f"QPushButton {{ text-align: left; border-left: 4px solid {accent}; }}"
            )
            if task.done:
                button.setEnabled(True)
                button.setText("✓ " + text)
            button.clicked.connect(lambda _=False, tid=task.id: self._pick(tid))
            self.body_layout.addWidget(button)
        self.place_near(anchor)
        self.show()

    def _pick(self, task_id: str) -> None:
        self.close()
        self.taskPicked.emit(task_id)


def _settings_qss(palette: Palette) -> str:
    return f"""
    QPushButton#seg {{
        background: {palette.button_bg};
        border: none;
        border-radius: 9px;
        padding: 7px 12px;
        color: {palette.text_dim};
        font-size: 12px;
    }}
    QPushButton#seg:hover {{ background: {palette.button_bg_hover}; }}
    QPushButton#seg:checked {{
        background: {palette.accent};
        color: {palette.accent_text};
    }}
    QPushButton#day {{
        background: {palette.button_bg};
        border: none;
        border-radius: 9px;
        padding: 0px;
        color: {palette.text_dim};
        font-size: 12px;
    }}
    QPushButton#day:hover {{ background: {palette.button_bg_hover}; }}
    QPushButton#day:checked {{
        background: {palette.accent};
        color: {palette.accent_text};
    }}
    QPushButton#swatch {{
        border-radius: 13px;
        border: 2px solid rgba(0, 0, 0, 0.14);
    }}
    QPushButton#swatch:checked {{ border: 2px solid {palette.text}; }}
    QPushButton#ghost {{
        background: transparent;
        border: none;
        color: {palette.text_dim};
        text-align: left;
        padding: 7px 8px;
        font-size: 12px;
    }}
    QPushButton#ghost:hover {{ background: {palette.button_bg_hover}; border-radius: 8px; }}
    QLabel#section {{
        color: {palette.text_muted};
        font-size: 11px;
        padding-top: 4px;
    }}
    QLabel#value {{ color: {palette.text_dim}; font-size: 11px; }}
    QFrame#sep {{
        background: {palette.grid_line};
        max-height: 1px;
        border: none;
    }}
    QSlider::groove:horizontal {{
        height: 4px; background: {palette.button_bg}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        height: 4px; background: {palette.accent}; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px; margin: -5px 0;
        border-radius: 7px; background: #ffffff;
        border: 2px solid {palette.accent};
    }}
    """


class SettingsPopup(PopupBase):
    changed = Signal()
    SHADOW_INSET = 9

    def __init__(self, panel, settings, palette: Palette, parent=None) -> None:
        super().__init__(palette, parent)
        self.panel = panel
        self.settings = settings
        self.setMinimumWidth(252)
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 23, 25, 23)
        layout.setSpacing(7)

        head = QLabel("外观设置", self)
        head_font = QFont("Microsoft YaHei UI", 14)
        head_font.setWeight(QFont.DemiBold)
        head.setFont(head_font)
        layout.addWidget(head)
        layout.addSpacing(2)

        # 主题色
        layout.addWidget(self._section("主题色"))
        accent_row = QHBoxLayout()
        accent_row.setSpacing(8)
        self._accent_buttons: dict[str, QPushButton] = {}
        for key in ACCENT_ORDER:
            accent = ACCENTS[key]
            button = QPushButton("", self)
            button.setObjectName("swatch")
            button.setCheckable(True)
            button.setFixedSize(26, 26)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(accent.label)
            button.setStyleSheet(
                f"QPushButton#swatch {{ background: {accent.swatch}; }}"
            )
            button.clicked.connect(lambda _=False, k=key: self._set_accent(k))
            self._accent_buttons[key] = button
            accent_row.addWidget(button)
        accent_row.addStretch(1)
        layout.addLayout(accent_row)

        # 明暗
        layout.addWidget(self._section("明暗"))
        self._theme_group = self._segment(
            [("auto", "跟随系统"), ("light", "浅色"), ("dark", "深色")],
            self._set_theme,
        )
        layout.addWidget(self._theme_group[0])

        # 背景
        layout.addWidget(self._section("背景"))
        self._bg_group = self._segment(
            [("frosted", "磨砂"), ("translucent", "半透明"), ("solid", "不透明")],
            self._set_backdrop,
        )
        layout.addWidget(self._bg_group[0])

        # 透明度
        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(8)
        opacity_label = QLabel("透明度", self)
        opacity_label.setObjectName("section")
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        self.opacity_value = QLabel("", self)
        self.opacity_value.setObjectName("value")
        self.opacity_value.setFixedWidth(34)
        opacity_row.addWidget(opacity_label)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)

        # 大小
        layout.addWidget(self._section("面板大小"))
        self._size_group = self._segment(
            [("小", "小"), ("中", "中"), ("大", "大")], self._set_size
        )
        layout.addWidget(self._size_group[0])

        self.lunar_box = QCheckBox("显示农历和节日", self)
        self.lunar_box.toggled.connect(self._set_lunar)
        layout.addWidget(self.lunar_box)

        self.merge_box = QCheckBox("同名的连续任务自动并成一条", self)
        self.merge_box.setToolTip(
            "比如周一、周二都加了「跑步」，会自动合并成一条 周一~周二 的横条"
        )
        self.merge_box.toggled.connect(self._set_merge)
        layout.addWidget(self.merge_box)

        self.autostart_box = QCheckBox("开机自动启动", self)
        self.autostart_box.toggled.connect(self._set_autostart)
        layout.addWidget(self.autostart_box)

        separator = QFrame(self)
        separator.setObjectName("sep")
        separator.setFixedHeight(1)
        layout.addSpacing(4)
        layout.addWidget(separator)
        layout.addSpacing(4)
        for text, slot in (
            ("创建桌面快捷方式", self._create_shortcut),
            ("打开数据文件夹", self._open_folder),
            ("关于 / 使用说明", self._show_about),
            ("退出", self._quit),
        ):
            button = QPushButton(text, self)
            button.setObjectName("ghost")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            layout.addWidget(button)

        apply_stylesheet(self, _popup_qss(palette) + _settings_qss(palette))
        self.sync()

    # ---------------------------------------------------------------- 组装

    def _section(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("section")
        return label

    def _segment(self, options, callback):
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        buttons: dict[str, QPushButton] = {}
        for key, label in options:
            button = QPushButton(label, holder)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: callback(k))
            buttons[key] = button
            row.addWidget(button, 1)
        return holder, buttons

    def sync(self) -> None:
        self._loading = True
        for key, button in self._accent_buttons.items():
            button.setChecked(self.settings.accent == key)
        for key, button in self._theme_group[1].items():
            button.setChecked(self.settings.theme == key)
        for key, button in self._bg_group[1].items():
            button.setChecked(self.settings.backdrop == key)
        for key, button in self._size_group[1].items():
            button.setChecked(self.settings.size_preset == key)
        self.opacity_slider.setValue(int(round(self.settings.opacity * 100)))
        self.opacity_value.setText(f"{int(round(self.settings.opacity * 100))}%")
        self.lunar_box.setChecked(self.settings.show_lunar)
        self.merge_box.setChecked(self.settings.merge_same_title)
        self.autostart_box.setChecked(self.settings.autostart)
        self._loading = False

    def set_palette_obj(self, palette: Palette) -> None:
        self.palette_ = palette
        apply_stylesheet(self, _popup_qss(palette) + _settings_qss(palette))
        for key, button in self._accent_buttons.items():
            button.setStyleSheet(
                f"QPushButton#swatch {{ background: {ACCENTS[key].swatch}; }}"
            )
        self.update()

    # ---------------------------------------------------------------- 动作

    def _emit(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _set_accent(self, key: str) -> None:
        self.settings.accent = key
        self.sync()
        self._emit()

    def _set_theme(self, key: str) -> None:
        self.settings.theme = key
        self.sync()
        self._emit()

    def _set_backdrop(self, key: str) -> None:
        self.settings.backdrop = key
        self.sync()
        self._emit()

    def _set_size(self, key: str) -> None:
        self.settings.size_preset = key
        self.sync()
        self._emit()

    def _set_opacity(self, value: int) -> None:
        self.settings.opacity = value / 100.0
        self.opacity_value.setText(f"{value}%")
        self._emit()

    def _set_lunar(self, checked: bool) -> None:
        self.settings.show_lunar = checked
        self._emit()

    def _set_merge(self, checked: bool) -> None:
        self.settings.merge_same_title = checked
        self._emit()

    def _set_autostart(self, checked: bool) -> None:
        from . import winapi

        self.settings.autostart = checked
        winapi.set_autostart(checked)
        self._emit()

    def _create_shortcut(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from . import winapi

        result = winapi.create_desktop_shortcut()
        if result:
            QMessageBox.information(self, "桌面月历", f"已经在桌面创建好快捷方式：\n{result}")
        else:
            QMessageBox.warning(
                self,
                "桌面月历",
                "创建快捷方式失败了，可以手动把程序发送到桌面。",
            )

    def _open_folder(self) -> None:
        from . import paths, winapi

        winapi.open_folder(str(paths.data_dir()))

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "关于 桌面月历",
            "桌面月历 v1.1\n\n"
            "· 鼠标移到屏幕右边缘，月历滑出来；移开自动收起。\n"
            "· 日期格里点一下就能输入待办，回车确认。\n"
            "· 拖任务条右端可以拉长到多天，拖中间可以整体挪日期。\n"
            "· 点左边小圆圈=完成，点横条=编辑。\n"
            "· 数据保存在「文档\\桌面月历」，每天自动备份。\n",
        )

    def _quit(self) -> None:
        self.close()
        self.panel.quitRequested.emit()


class AddSchedulePopup(PopupBase):
    """直接添加日程：可指定每天 / 每周几 / 每月几号。"""

    added = Signal(int)
    SHADOW_INSET = 9

    def __init__(self, store: TaskStore, palette: Palette, parent=None) -> None:
        super().__init__(palette, parent)
        self.store = store
        self._color = "theme"
        self._repeat = "none"
        self._weekdays: set[int] = set()
        self._loading = False
        self.setMinimumWidth(272)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 23, 25, 23)
        layout.setSpacing(7)

        head = QLabel("添加日程", self)
        head_font = QFont("Microsoft YaHei UI", 14)
        head_font.setWeight(QFont.DemiBold)
        head.setFont(head_font)
        layout.addWidget(head)
        layout.addSpacing(2)

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("要做什么？例如：跑步 30 分钟")
        font = QFont("Microsoft YaHei UI", 13)
        self.title_edit.setFont(font)
        layout.addWidget(self.title_edit)

        layout.addWidget(self._section("重复"))
        self._repeat_group = self._segment(
            [("none", "只这一次"), ("daily", "每天"), ("weekly", "每周"), ("monthly", "每月")],
            self._set_repeat,
        )
        layout.addWidget(self._repeat_group[0])

        self.weekday_holder = QWidget(self)
        weekday_row = QHBoxLayout(self.weekday_holder)
        weekday_row.setContentsMargins(0, 0, 0, 0)
        weekday_row.setSpacing(4)
        self._weekday_buttons: dict[int, QPushButton] = {}
        for index, label in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            button = QPushButton(label, self.weekday_holder)
            button.setObjectName("day")
            button.setCheckable(True)
            button.setFixedSize(32, 30)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._toggle_weekday(i))
            self._weekday_buttons[index] = button
            weekday_row.addWidget(button)
        weekday_row.addStretch(1)
        layout.addWidget(self.weekday_holder)

        self.month_holder = QWidget(self)
        month_row = QHBoxLayout(self.month_holder)
        month_row.setContentsMargins(0, 0, 0, 0)
        month_row.setSpacing(8)
        month_label = QLabel("每月", self.month_holder)
        month_label.setObjectName("section")
        self.month_spin = QSpinBox(self.month_holder)
        self.month_spin.setRange(1, 31)
        self.month_spin.setValue(1)
        self.month_spin.setSuffix(" 号")
        self.month_spin.valueChanged.connect(lambda _v: self._update_summary())
        month_row.addWidget(month_label)
        month_row.addWidget(self.month_spin, 1)
        layout.addWidget(self.month_holder)

        layout.addWidget(self._section("日期"))
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        self.start_edit = QDateEdit(self)
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_edit.setDate(QDate.currentDate())
        self.start_edit.setMinimumWidth(132)
        self.start_edit.setAlignment(Qt.AlignCenter)
        self.start_edit.dateChanged.connect(lambda _d: self._update_summary())
        self.end_edit = QDateEdit(self)
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_edit.setDate(QDate.currentDate())
        self.end_edit.setMinimumWidth(132)
        self.end_edit.setAlignment(Qt.AlignCenter)
        self.end_edit.dateChanged.connect(lambda _d: self._update_summary())
        date_row.addWidget(self.start_edit)
        date_row.addWidget(QLabel("~", self))
        date_row.addWidget(self.end_edit)
        layout.addLayout(date_row)

        layout.addWidget(self._section("颜色"))
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self._swatches: dict[str, QPushButton] = {}
        for name in CHIP_ORDER:
            button = QPushButton("", self)
            button.setObjectName("swatch")
            button.setCheckable(True)
            button.setFixedSize(24, 24)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(CHIP_LABELS.get(name, name))
            button.clicked.connect(lambda _=False, n=name: self._set_color(n))
            self._swatches[name] = button
            color_row.addWidget(button)
        color_row.addStretch(1)
        layout.addLayout(color_row)

        self.summary = QLabel("", self)
        self.summary.setObjectName("value")
        layout.addWidget(self.summary)
        layout.addSpacing(2)

        self.submit_button = QPushButton("添加到日历", self)
        self.submit_button.setObjectName("primary")
        self.submit_button.setFixedHeight(36)
        self.submit_button.setCursor(Qt.PointingHandCursor)
        self.submit_button.clicked.connect(self._submit)
        layout.addWidget(self.submit_button)

        self.title_edit.returnPressed.connect(self._submit)
        self.apply_palette(palette)
        self._sync_visibility()

    # ------------------------------------------------------------ 复用小控件

    def _section(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("section")
        return label

    def _segment(self, options, callback):
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        buttons: dict[str, QPushButton] = {}
        for key, label in options:
            button = QPushButton(label, holder)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: callback(k))
            buttons[key] = button
            row.addWidget(button, 1)
        return holder, buttons

    def apply_palette(self, palette: Palette) -> None:
        self.palette_ = palette
        extra = """
    QPushButton#primary {
        background: %s;
        border: none;
        border-radius: 10px;
        color: %s;
        font-size: 13px;
    }
    QPushButton#primary:hover { background: %s; }
    QSpinBox {
        background: %s;
        border: 1px solid %s;
        border-radius: 6px;
        padding: 4px 6px;
        color: %s;
    }
    """ % (
            palette.accent,
            palette.accent_text,
            QColor(palette.accent).lighter(112).name(),
            palette.button_bg,
            palette.grid_line,
            palette.text,
        )
        apply_stylesheet(self, _popup_qss(palette) + _settings_qss(palette) + extra)
        for name, button in self._swatches.items():
            button.setStyleSheet(
                f"QPushButton#swatch {{ background: {chip_color(palette, name)}; }}"
            )
        self._refresh_colors()
        self.update()

    # ------------------------------------------------------------ 状态

    def reset(self, day: date, weekdays: set[int] | None = None) -> None:
        self._loading = True
        self.title_edit.clear()
        self.start_edit.setDate(QDate(day.year, day.month, day.day))
        self.end_edit.setDate(QDate(day.year, day.month, day.day))
        self._repeat = "none"
        self._weekdays = set(weekdays) if weekdays else {day.weekday()}
        self.month_spin.setValue(day.day)
        self._color = "theme"
        self._loading = False
        self._sync_buttons()
        self._sync_visibility()
        self._refresh_colors()

    def _sync_buttons(self) -> None:
        for key, button in self._repeat_group[1].items():
            button.setChecked(self._repeat == key)
        for index, button in self._weekday_buttons.items():
            button.setChecked(index in self._weekdays)

    def _sync_visibility(self) -> None:
        self.weekday_holder.setVisible(self._repeat == "weekly")
        self.month_holder.setVisible(self._repeat == "monthly")
        self.end_edit.setEnabled(self._repeat != "none")
        self._update_summary()

    def _refresh_colors(self) -> None:
        for name, button in self._swatches.items():
            button.setChecked(name == self._color)

    def _set_repeat(self, key: str) -> None:
        self._repeat = key
        if key != "none":
            start_date = self.start_edit.date()
            if self.end_edit.date() <= start_date:
                # 刚切到重复模式时，默认往后铺一段时间，省得只生成一天
                span = 365 if key == "monthly" else 90
                self._loading = True
                self.end_edit.setDate(start_date.addDays(span))
                self._loading = False
        self._sync_buttons()
        self._sync_visibility()

    def _toggle_weekday(self, index: int) -> None:
        if index in self._weekdays:
            self._weekdays.discard(index)
        else:
            self._weekdays.add(index)
        self._sync_buttons()
        self._update_summary()

    def _set_color(self, name: str) -> None:
        self._color = name
        self._refresh_colors()

    def _occurrences(self) -> list[date]:
        start = self.start_edit.date().toPython()
        end = self.end_edit.date().toPython()
        if self._repeat == "none":
            return [start]
        if end < start:
            start, end = end, start
        days: list[date] = []
        cursor = start
        while cursor <= end and len(days) < 400:
            if self._repeat == "daily":
                days.append(cursor)
            elif self._repeat == "weekly":
                if cursor.weekday() in self._weekdays:
                    days.append(cursor)
            elif self._repeat == "monthly":
                if cursor.day == self.month_spin.value():
                    days.append(cursor)
            cursor += timedelta(days=1)
        return days

    def _update_summary(self) -> None:
        if self._loading:
            return
        count = len(self._occurrences())
        label = self._repeat_group[1].get(self._repeat)
        text = label.text() if label is not None else ""
        self.summary.setText(
            f"{text} · 共 {count} 天" if count else "这个范围内没有符合条件的日期"
        )

    # ------------------------------------------------------------ 提交

    def _submit(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            self.title_edit.setFocus(Qt.OtherFocusReason)
            self.summary.setText("先写一下要做什么吧")
            return
        days = self._occurrences()
        if not days:
            self.summary.setText("这个范围内没有符合条件的日期")
            return
        self.store.add_many(title, days, color=self._color)
        self.added.emit(len(days))
        self.title_edit.clear()
        self.close()
