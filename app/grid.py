from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QLineEdit, QWidget

from . import lunar
from .layout import MonthModel, Segment
from .qtutil import qcolor, with_alpha
from .store import Task
from .theme import Palette, chip_color


@dataclass(frozen=True)
class Metrics:
    pad: int = 6
    weekday_h: int = 30
    row_h: int = 100
    chip_h: int = 20
    chip_gap: int = 3
    day_num_h: int = 23
    corner: int = 6
    day_font: int = 15
    chip_font: int = 12
    lunar_font: int = 10
    weekday_font: int = 12
    panel_width: int = 760
    resize_zone: int = 9

    @property
    def lane_pitch(self) -> int:
        return self.chip_h + self.chip_gap

    @property
    def visible_lanes(self) -> int:
        usable = self.row_h - self.day_num_h - 2
        return max(1, int(usable // self.lane_pitch) if self.lane_pitch else 1)


PRESETS: dict[str, Metrics] = {
    "小": Metrics(
        row_h=84, chip_h=17, chip_gap=3, day_num_h=21, day_font=13,
        chip_font=11, lunar_font=9, weekday_font=11, panel_width=680,
    ),
    "中": Metrics(
        row_h=100, chip_h=20, chip_gap=3, day_num_h=23, day_font=15,
        chip_font=12, lunar_font=10, weekday_font=12, panel_width=780,
    ),
    "大": Metrics(
        row_h=118, chip_h=23, chip_gap=4, day_num_h=26, day_font=17,
        chip_font=13, lunar_font=11, weekday_font=13, panel_width=920,
    ),
}


def metrics_for(preset: str) -> Metrics:
    return PRESETS.get(preset, PRESETS["中"])


class MonthGrid(QWidget):
    taskActivated = Signal(str)
    taskCreated = Signal(str, object)
    taskToggled = Signal(str)
    taskMoved = Signal(str, int)
    taskResized = Signal(str, object, object)
    overflowActivated = Signal(object)
    geometryChanged = Signal()

    def __init__(self, metrics: Metrics, palette: Palette, parent=None) -> None:
        super().__init__(parent)
        self.m = metrics
        self.palette_ = palette
        self.model: MonthModel | None = None
        self.tasks: list[Task] = []
        self.hover_cell: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self._fonts: dict[str, QFont] = {}
        self._build_fonts()

        self._drag: dict | None = None
        self._press_pos: QPoint | None = None
        self._hover_task: str | None = None

        self._inline = _InlineEdit(self)
        self._inline.hide()
        self._inline.returnPressed.connect(self._commit_inline)
        self._inline.editingFinished.connect(self._on_inline_finished)
        self._inline.escapePressed.connect(self._cancel_inline)
        self._inline.activity.connect(self._note_inline_activity)
        self._inline_date: date | None = None
        self._inline_closing = False
        self._inline_active_at = 0.0

    def _note_inline_activity(self) -> None:
        self._inline_active_at = time.monotonic()

    def inline_idle_seconds(self) -> float:
        if self._inline_active_at <= 0:
            return 0.0
        return time.monotonic() - self._inline_active_at

    def inline_text(self) -> str:
        return self._inline.text() if self._inline.isVisible() else ""

    def commit_inline(self) -> None:
        """外部调用：把正在输入的内容存下来（用于面板自动收起前）。"""
        if self._inline.isVisible():
            self._commit_inline()

    # ------------------------------------------------------------------ 基础

    def _build_fonts(self) -> None:
        self._fonts = {
            "day": QFont("Microsoft YaHei UI", self.m.day_font, QFont.DemiBold),
            "chip": QFont("Microsoft YaHei UI", self.m.chip_font),
            "lunar": QFont("Microsoft YaHei UI", self.m.lunar_font),
            "weekday": QFont("Microsoft YaHei UI", self.m.weekday_font, QFont.Medium),
        }

    def apply_metrics(self, metrics: Metrics) -> None:
        self.m = metrics
        self._build_fonts()
        self.updateGeometry()
        self.update()

    def set_palette_obj(self, palette: Palette) -> None:
        self.palette_ = palette
        self._style_inline()
        self.update()

    def apply_model(self, model: MonthModel, tasks: list[Task]) -> None:
        self.model = model
        self.tasks = tasks
        self.update()

    def sizeHint(self):
        from PySide6.QtCore import QSize

        rows = len(self.model.weeks) if self.model else 6
        return QSize(self.m.panel_width, self.m.pad * 2 + self.m.weekday_h + rows * self.m.row_h)

    def grid_height(self) -> int:
        rows = len(self.model.weeks) if self.model else 6
        return self.m.pad * 2 + self.m.weekday_h + rows * self.m.row_h

    # ------------------------------------------------------------- 几何计算

    @property
    def cell_w(self) -> int:
        usable = max(0, self.width() - self.m.pad * 2)
        return max(1, usable // 7)

    def grid_left(self) -> int:
        usable = max(0, self.width() - self.m.pad * 2)
        return self.m.pad + max(0, (usable - self.cell_w * 7) // 2)

    def cell_rect(self, week: int, col: int) -> QRect:
        return QRect(
            self.grid_left() + col * self.cell_w,
            self.m.pad + self.m.weekday_h + week * self.m.row_h,
            self.cell_w,
            self.m.row_h,
        )

    def cell_at(self, pos: QPoint) -> tuple[int, int] | None:
        if self.model is None:
            return None
        top = self.m.pad + self.m.weekday_h
        if pos.y() < top:
            return None
        week = (pos.y() - top) // self.m.row_h
        if week < 0 or week >= len(self.model.weeks):
            return None
        left = self.grid_left()
        col = (pos.x() - left) // self.cell_w
        if col < 0 or col > 6:
            return None
        return int(week), int(col)

    def _lane_rect(self, cell: QRect, lane: int) -> QRect:
        y = cell.y() + self.m.day_num_h + lane * self.m.lane_pitch
        return QRect(cell.x(), y, cell.width(), self.m.chip_h)

    def _segment_rect(self, week_index: int, col: int, span: int, head: bool, tail: bool) -> QRectF:
        first = self.cell_rect(week_index, col)
        last = self.cell_rect(week_index, col + span - 1)
        x0 = float(first.x() + (4 if head else 0))
        x1 = float(last.x() + last.width() - (4 if tail else 0))
        return QRectF(x0, 0.0, max(4.0, x1 - x0), float(self.m.chip_h))

    # --------------------------------------------------------------- 绘制

    def paintEvent(self, event) -> None:  # noqa: N802
        if self.model is None:
            return
        palette = self.palette_
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self._paint_weekday_header(painter, palette)
        for week_index, week in enumerate(self.model.weeks):
            self._paint_week(painter, palette, week_index, week)
        self._paint_drag_preview(painter, palette)
        painter.end()

    def _paint_weekday_header(self, painter: QPainter, palette: Palette) -> None:
        painter.setFont(self._fonts["weekday"])
        for col in range(7):
            rect = QRect(
                self.grid_left() + col * self.cell_w,
                self.m.pad + 2,
                self.cell_w,
                self.m.weekday_h - 4,
            )
            color = qcolor(palette.text_muted)
            if col == 5:
                color = qcolor(palette.saturday)
            elif col == 6:
                color = qcolor(palette.sunday)
            painter.setPen(QPen(color))
            text = lunar.weekday_label(col)
            painter.drawText(rect, Qt.AlignCenter, text)
        painter.setPen(QPen(qcolor(palette.grid_line)))
        y = self.m.pad + self.m.weekday_h
        painter.drawLine(self.grid_left(), y, self.grid_left() + self.cell_w * 7, y)

    def _paint_week(self, painter: QPainter, palette: Palette, week_index: int, week) -> None:
        assert self.model is not None
        visible = self.m.visible_lanes
        overflow = week.lane_count > visible
        display_lanes = visible - 1 if overflow else visible
        display_lanes = max(1, display_lanes)

        today = date.today()
        for col, day in enumerate(week.days):
            cell = self.cell_rect(week_index, col)
            in_month = day.month == self.model.month and day.year == self.model.year
            alpha = 1.0 if in_month else palette.other_month_alpha
            is_today = day == today

            if self.hover_cell == (week_index, col) and not is_today:
                painter.setPen(Qt.NoPen)
                painter.setBrush(qcolor(palette.cell_hover))
                painter.drawRoundedRect(QRectF(cell).adjusted(2, 2, -2, -2), 7, 7)

            # 日期数字
            painter.setFont(self._fonts["day"])
            if is_today:
                badge_w = 26 if day.day < 10 else 32
                badge = QRectF(
                    float(cell.x() + 5),
                    float(cell.y() + 2),
                    float(badge_w),
                    float(self.m.day_num_h - 3),
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(qcolor(palette.today_ring))
                painter.drawRoundedRect(badge, 8, 8)
                painter.setPen(QPen(qcolor("#ffffff")))
                painter.drawText(badge, Qt.AlignCenter, str(day.day))
                lunar_left = cell.x() + 5 + badge_w + 7
            else:
                num_rect = QRect(cell.x() + 7, cell.y() + 3, 40, self.m.day_num_h - 4)
                color = qcolor(
                    palette.sunday
                    if col == 6
                    else palette.saturday
                    if col == 5
                    else palette.text
                )
                color = with_alpha(color, alpha)
                if not in_month:
                    color = with_alpha(color, palette.other_month_alpha)
                painter.setPen(QPen(color))
                painter.drawText(num_rect, Qt.AlignLeft | Qt.AlignVCenter, str(day.day))
                lunar_left = cell.x() + 38

            # 农历 / 节日
            if self.palette_.name and self._lunar_enabled:
                text, important = lunar.lunar_info(day)
                if text:
                    lunar_rect = QRect(
                        lunar_left,
                        cell.y() + 5,
                        max(10, cell.x() + cell.width() - 6 - lunar_left),
                        self.m.day_num_h - 6,
                    )
                    lunar_color = qcolor(palette.sunday if important else palette.text_muted)
                    if important and not in_month:
                        lunar_color = with_alpha(lunar_color, palette.other_month_alpha)
                    elif not important:
                        lunar_color = with_alpha(lunar_color, 0.85 if in_month else palette.other_month_alpha)
                    painter.setFont(self._fonts["lunar"])
                    painter.setPen(QPen(lunar_color))
                    painter.drawText(
                        lunar_rect,
                        Qt.AlignRight | Qt.AlignVCenter,
                        _elide(painter, text, lunar_rect.width()),
                    )

        drag = self.drag_preview()
        dragging_id = drag[0].id if drag else None

        # 任务横条
        for segment in week.segments:
            if segment.lane >= display_lanes:
                continue
            if dragging_id is not None and segment.task.id == dragging_id:
                continue
            self._paint_segment(painter, palette, week_index, segment, alpha=1.0)

        # 溢出提示
        if overflow:
            for col in range(7):
                hidden = [
                    s
                    for s in week.segments_in_col(col)
                    if s.lane >= display_lanes
                ]
                if not hidden:
                    continue
                cell = self.cell_rect(week_index, col)
                rect = self._lane_rect(cell, display_lanes)
                rect = rect.adjusted(4, 0, -4, 0)
                painter.setPen(Qt.NoPen)
                painter.setBrush(qcolor(palette.button_bg))
                painter.drawRoundedRect(QRectF(rect), self.m.corner, self.m.corner)
                painter.setFont(self._fonts["chip"])
                painter.setPen(QPen(qcolor(palette.text_dim)))
                painter.drawText(rect.adjusted(6, 0, -2, 0), Qt.AlignVCenter, f"+{len(hidden)}")

    def _paint_drag_preview(self, painter: QPainter, palette: Palette) -> None:
        if self.model is None or self._drag is None or not self._drag["started"]:
            return
        task = self._drag["task"]
        start, end = self._drag["preview"]
        lane = self._drag.get("lane", 0)
        for week_index, week in enumerate(self.model.weeks):
            if start > week.days[6] or end < week.days[0]:
                continue
            segment = Segment(task=task, lane=lane, col=0, span=1, head=True, tail=True)
            self._paint_segment(
                painter, palette, week_index, segment, preview=(start, end), alpha=0.88
            )

    def _paint_segment(
        self,
        painter: QPainter,
        palette: Palette,
        week_index: int,
        segment: Segment,
        preview: tuple[date, date] | None = None,
        alpha: float = 1.0,
    ) -> None:
        assert self.model is not None
        task = segment.task
        start, end = preview or (task.start, task.end)

        week = self.model.weeks[week_index]
        week_start, week_end = week.days[0], week.days[6]
        if start > week_end or end < week_start:
            return
        col = (max(start, week_start) - week_start).days
        last_col = (min(end, week_end) - week_start).days
        head = start >= week_start
        tail = end <= week_end
        span = last_col - col + 1

        cell = self.cell_rect(week_index, col)
        lane_rect = self._lane_rect(cell, segment.lane)
        base = self._segment_rect(week_index, col, span, head, tail)
        rect = QRectF(base.x(), lane_rect.y(), base.width(), base.height())

        color = qcolor(chip_color(palette, task.color))
        if preview is None and self._hover_task == task.id:
            color = color.lighter(118)
        if task.done:
            color = with_alpha(color, 0.45 * alpha)
        else:
            color = with_alpha(color, palette.chip_alpha * alpha)

        radius = float(self.m.corner)
        path = QPainterPath()
        tl = radius if head else 0.0
        bl = radius if head else 0.0
        tr = radius if tail else 0.0
        br = radius if tail else 0.0
        rect = QRectF(rect)
        path.moveTo(rect.left() + tl, rect.top())
        path.lineTo(rect.right() - tr, rect.top())
        if tr:
            path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + tr)
        path.lineTo(rect.right(), rect.bottom() - br)
        if br:
            path.quadTo(rect.right(), rect.bottom(), rect.right() - br, rect.bottom())
        path.lineTo(rect.left() + bl, rect.bottom())
        if bl:
            path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - bl)
        path.lineTo(rect.left(), rect.top() + tl)
        if tl:
            path.quadTo(rect.left(), rect.top(), rect.left() + tl, rect.top())
        path.closeSubpath()

        painter.setPen(Qt.NoPen)
        gradient = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        gradient.setColorAt(0.0, color.lighter(112))
        gradient.setColorAt(1.0, color.darker(106))
        painter.setBrush(gradient)
        painter.drawPath(path)

        # 文字
        text_rect = QRectF(rect)
        text_rect.adjust(7, 0, -5, 0)
        if head and task.start == start:
            # 画完成小圆点
            dot = 8.5
            cy = rect.center().y()
            cx = rect.left() + 9
            painter.setPen(QPen(with_alpha(qcolor("#ffffff"), 0.85), 1.3))
            if task.done:
                painter.setBrush(with_alpha(qcolor("#ffffff"), 0.85))
            else:
                painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(cx - dot / 2, cy - dot / 2, dot, dot))
            if task.done:
                painter.setPen(QPen(qcolor(palette.chip_text), 1.6))
                painter.drawLine(
                    QRectF(cx - 2.4, cy + 0.2, 2.0, 2.0).topLeft(),
                    QRectF(cx + 2.4, cy - 2.6, 2.0, 2.0).topLeft(),
                )
            text_rect.setLeft(rect.left() + 17)

        painter.setFont(self._fonts["chip"])
        font = self._fonts["chip"]
        if task.done:
            font = QFont(font)
            font.setStrikeOut(True)
            painter.setFont(font)
        text_color = with_alpha(qcolor(palette.chip_text), 0.95 * alpha)
        painter.setPen(QPen(text_color))
        label = _elide(painter, task.title or "（空）", int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

    # --------------------------------------------------------------- 交互

    _lunar_enabled = True

    def set_lunar_enabled(self, enabled: bool) -> None:
        self._lunar_enabled = enabled
        self.update()

    def hit_test(self, pos: QPoint):
        """返回 (类型, 数据)。类型: task / overflow / empty。"""
        if self.model is None:
            return ("empty", None)
        cell = self.cell_at(pos)
        if cell is None:
            return ("empty", None)
        week_index, col = cell
        week = self.model.weeks[week_index]
        visible = self.m.visible_lanes
        overflow = week.lane_count > visible
        display_lanes = max(1, visible - 1) if overflow else visible

        cell_rect = self.cell_rect(week_index, col)
        if overflow and self._lane_at(pos, cell_rect) == display_lanes:
            hidden = [s for s in week.segments_in_col(col) if s.lane >= display_lanes]
            if hidden:
                return ("overflow", week.days[col])

        for segment in week.segments:
            if not (segment.col <= col <= segment.last_col):
                continue
            if segment.lane >= display_lanes:
                continue
            lane_rect = self._lane_rect(self.cell_rect(week_index, col), segment.lane)
            if not lane_rect.adjusted(0, -self.m.chip_gap // 2, 0, self.m.chip_gap // 2).contains(pos):
                continue
            rect = self._segment_rect(
                week_index, segment.col, segment.span, segment.head, segment.tail
            )
            part = "body"
            if segment.head and pos.x() - rect.left() <= 16:
                part = "check"
            elif segment.tail and rect.right() - pos.x() <= self.m.resize_zone:
                part = "resize_end"
            elif segment.head and pos.x() - rect.left() <= self.m.resize_zone:
                part = "resize_start"
            return ("task", (segment, part))
        return ("empty", None)

    def _lane_at(self, pos: QPoint, cell: QRect) -> int:
        y = pos.y() - (cell.y() + self.m.day_num_h)
        if y < 0:
            return -1
        return int(y // self.m.lane_pitch)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = _pos_of(event)
        cell = self.cell_at(pos)
        if cell != self.hover_cell:
            self.hover_cell = cell
            self.update()

        if self._drag is not None:
            self._update_drag(pos)
            return

        kind, payload = self.hit_test(pos)
        hover_id: str | None = None
        if kind == "task":
            segment, part = payload
            hover_id = segment.task.id
            if part in ("resize_end", "resize_start"):
                self.setCursor(Qt.SizeHorCursor)
            elif part == "check":
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
            task = segment.task
            if task.start == task.end:
                tip = f"{task.title}\n{task.start:%Y-%m-%d}"
            else:
                tip = (
                    f"{task.title}\n{task.start:%Y-%m-%d} → {task.end:%Y-%m-%d}"
                    f"（{task.days} 天）"
                )
            tip += "\n\n点一下编辑 · 拖右端改天数 · 拖中间整体挪"
            self.setToolTip(tip)
        elif kind == "overflow":
            self.setCursor(Qt.PointingHandCursor)
            day = payload
            self.setToolTip(f"{day.month}月{day.day}日还有更多任务，点开看全部")
        else:
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")
        if hover_id != self._hover_task:
            self._hover_task = hover_id
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hover_cell = None
        self._hover_task = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if self._inline.isVisible():
            self._commit_inline()
        pos = _pos_of(event)
        kind, payload = self.hit_test(pos)
        if kind == "overflow":
            self.overflowActivated.emit(payload)
            return
        if kind == "task":
            segment, part = payload
            task = segment.task
            if part == "check":
                self.taskToggled.emit(task.id)
                return
            self._press_pos = pos
            self._drag = {
                "mode": {"resize_end": "resize_end", "resize_start": "resize_start"}.get(
                    part, "move"
                ),
                "task": task,
                "orig_start": task.start,
                "orig_end": task.end,
                "press_day": self._day_at(pos),
                "started": False,
                "preview": (task.start, task.end),
                "lane": segment.lane,
            }
            return
        day = self._day_at(pos)
        if day is not None:
            self._open_inline(day, pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or self._drag is None:
            super().mouseReleaseEvent(event)
            return
        drag = self._drag
        self._drag = None
        if not drag["started"]:
            self.taskActivated.emit(drag["task"].id)
            self.update()
            return
        preview = drag["preview"]
        task: Task = drag["task"]
        if preview != (task.start, task.end):
            if drag["mode"] == "move":
                delta = (preview[0] - drag["orig_start"]).days
                self.taskMoved.emit(task.id, delta)
            else:
                self.taskResized.emit(task.id, preview[0], preview[1])
        self.update()

    def _update_drag(self, pos: QPoint) -> None:
        drag = self._drag
        if drag is None:
            return
        if not drag["started"]:
            if self._press_pos is not None and (pos - self._press_pos).manhattanLength() < 6:
                return
            drag["started"] = True

        week_index_col = self._day_at(pos)
        if week_index_col is None:
            return
        target = week_index_col
        task: Task = drag["task"]
        preview = drag["preview"]
        if drag["mode"] == "move":
            delta = (target - drag["press_day"]).days
            new_start = drag["orig_start"] + timedelta(days=delta)
            new_end = drag["orig_end"] + timedelta(days=delta)
            preview = (new_start, new_end)
        elif drag["mode"] == "resize_end":
            new_end = max(target, task.start)
            preview = (task.start, new_end)
        else:
            new_start = min(target, task.end)
            preview = (new_start, task.end)
        if preview != drag["preview"]:
            drag["preview"] = preview
            self.update()

    def _day_at(self, pos: QPoint) -> date | None:
        cell = self.cell_at(pos)
        if cell is None or self.model is None:
            return None
        return self.model.weeks[cell[0]].days[cell[1]]

    # --------------------------------------------------------- 快速输入框

    def _style_inline(self) -> None:
        palette = self.palette_
        background = "#%02x%02x%02x" % palette.tint
        self._inline.setStyleSheet(
            f"""
            QLineEdit {{
                background: {background};
                border: 2px solid {palette.accent};
                border-radius: 5px;
                color: {palette.text};
                padding: 0px 6px;
                selection-background-color: {palette.accent};
                selection-color: {palette.accent_text};
            }}
            """
        )
        font = QFont("Microsoft YaHei UI", self.m.chip_font + 1)
        self._inline.setFont(font)
        self._inline.setPlaceholderText("输入待办，回车确认")

    def _open_inline(self, day: date, pos: QPoint) -> None:
        cell_info = self.cell_at(pos)
        if cell_info is None:
            return
        week_index, col = cell_info
        cell = self.cell_rect(week_index, col)
        lane = max(0, self._lane_at(pos, cell))
        lane = min(lane, max(0, self.m.visible_lanes - 1))
        rect = self._lane_rect(cell, lane).adjusted(3, 0, -3, 0)
        if rect.height() < 22:
            rect.setHeight(22)
        self._style_inline()
        self._inline.setGeometry(rect)
        self._inline.clear()
        self._inline_date = day
        self._inline.show()
        self._inline.setFocus(Qt.MouseFocusReason)
        self._inline_closing = False
        self._note_inline_activity()

    def _commit_inline(self) -> None:
        """提交当前输入。点别的地方、按回车、切到别的日期都会走这里。"""
        if self._inline_closing:
            return
        text = self._inline.text().strip()
        day = self._inline_date
        self._close_inline()
        if text and day is not None:
            self.taskCreated.emit(text, day)

    def _on_inline_finished(self) -> None:
        if self._inline_closing:
            return
        if self._inline.isVisible():
            self._commit_inline()

    def _cancel_inline(self) -> None:
        self._close_inline()

    def _close_inline(self) -> None:
        if not self._inline.isVisible():
            self._inline_date = None
            return
        self._inline_closing = True
        self._inline.hide()
        self._inline.clear()
        self._inline_date = None
        self._inline_closing = False

    def open_inline_for(self, day: date) -> None:
        """外部（比如双击空白处）调用，直接在指定日期开始输入。"""
        if self.model is None:
            return
        located = self.model.locate(day)
        if located is None:
            return
        cell = self.cell_rect(*located)
        self._open_inline(day, QPoint(cell.center().x(), cell.y() + self.m.day_num_h + 2))

    def drag_preview(self) -> tuple[Task, date, date] | None:
        if self._drag is None or not self._drag["started"]:
            return None
        task = self._drag["task"]
        start, end = self._drag["preview"]
        return task, start, end


def _elide(painter: QPainter, text: str, width: int) -> str:
    if width <= 0:
        return ""
    metrics = QFontMetrics(painter.font())
    return metrics.elidedText(text, Qt.ElideRight, width)


def _pos_of(event) -> QPoint:
    try:
        return event.position().toPoint()
    except AttributeError:
        return event.pos()


class _InlineEdit(QLineEdit):
    """格子里的快速输入框：Esc 取消，回车提交。"""

    escapePressed = Signal()
    activity = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.escapePressed.emit()
            return
        self.activity.emit()
        super().keyPressEvent(event)
