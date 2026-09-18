from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .store import Task


@dataclass
class Segment:
    """任务在某一周里的一段（可能只是整条任务的一部分）。"""

    task: Task
    lane: int
    col: int
    span: int
    head: bool          # 左侧是真正的开头（画圆角 + 显示文字）
    tail: bool          # 右侧是真正的结尾（画圆角）

    @property
    def last_col(self) -> int:
        return self.col + self.span - 1


@dataclass
class WeekRow:
    days: list[date]
    segments: list[Segment] = field(default_factory=list)

    @property
    def lane_count(self) -> int:
        return max((s.lane for s in self.segments), default=-1) + 1

    def segments_in_col(self, col: int) -> list[Segment]:
        return [s for s in self.segments if s.col <= col <= s.last_col]


@dataclass
class MonthModel:
    year: int
    month: int
    weeks: list[WeekRow]

    @property
    def title(self) -> str:
        return f"{self.year}年{self.month}月"

    def locate(self, day: date) -> tuple[int, int] | None:
        """返回 (第几周, 第几列)，找不到返回 None。"""
        for row_index, week in enumerate(self.weeks):
            for col, cell_day in enumerate(week.days):
                if cell_day == day:
                    return row_index, col
        return None


def month_weeks(year: int, month: int) -> list[list[date]]:
    """按周一开头切分整月，返回若干周，每周 7 天。"""
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    start = first - timedelta(days=first.weekday())
    end = last + timedelta(days=6 - last.weekday())
    weeks: list[list[date]] = []
    cursor = start
    while cursor <= end:
        weeks.append([cursor + timedelta(days=i) for i in range(7)])
        cursor += timedelta(days=7)
    return weeks


def _pack_week(week_start: date, week_end: date, tasks: list[Task]) -> list[Segment]:
    active = [t for t in tasks if t.start <= week_end and t.end >= week_start]
    active.sort(key=lambda t: (t.start, -t.days, t.done, t.title.lower()))

    lane_ends: list[int] = []   # 每条泳道当前占到的最后一列
    segments: list[Segment] = []
    for task in active:
        col = (max(task.start, week_start) - week_start).days
        last_col = (min(task.end, week_end) - week_start).days
        lane = None
        for index, occupied_until in enumerate(lane_ends):
            if occupied_until < col:
                lane = index
                break
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(last_col)
        else:
            lane_ends[lane] = last_col
        segments.append(
            Segment(
                task=task,
                lane=lane,
                col=col,
                span=last_col - col + 1,
                head=task.start >= week_start,
                tail=task.end <= week_end,
            )
        )
    return segments


def build_month(year: int, month: int, tasks: list[Task]) -> MonthModel:
    weeks: list[WeekRow] = []
    for days in month_weeks(year, month):
        week = WeekRow(days=list(days))
        week.segments = _pack_week(days[0], days[6], tasks)
        weeks.append(week)
    return MonthModel(year=year, month=month, weeks=weeks)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1
