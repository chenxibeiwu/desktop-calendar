from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import paths


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


@dataclass
class Task:
    id: str
    title: str
    start: date
    end: date
    done: bool = False
    color: str = "blue"
    created: str = ""
    updated: str = ""

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end

    def overlaps(self, other: "Task") -> bool:
        return self.start <= other.end and other.start <= self.end

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "done": self.done,
            "color": self.color,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Task | None":
        try:
            start = parse_date(raw["start"])
            end = parse_date(raw.get("end") or raw["start"])
            if end < start:
                start, end = end, start
            return cls(
                id=str(raw.get("id") or uuid.uuid4().hex),
                title=str(raw.get("title", "")),
                start=start,
                end=end,
                done=bool(raw.get("done", False)),
                color=str(raw.get("color") or "blue"),
                created=str(raw.get("created", "")),
                updated=str(raw.get("updated", "")),
            )
        except Exception:
            return None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskStore:
    """任务数据的读写。每次改动立刻落盘，并且每天自动备份一次。"""

    def __init__(self, path: Path | None = None, auto_merge: bool = True) -> None:
        self.path = path or paths.data_file()
        self._tasks: list[Task] = []
        self._last_backup_day: date | None = None
        # 同名的连续任务自动并成一条
        self.auto_merge = auto_merge

    # ---------- 读写 ----------

    def load(self) -> None:
        tasks: list[Task] = []
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                items = raw.get("tasks", []) if isinstance(raw, dict) else raw
                for item in items or []:
                    if isinstance(item, dict):
                        task = Task.from_dict(item)
                        if task is not None:
                            tasks.append(task)
            except Exception:
                self._rescue_corrupt_file()
        self._tasks = tasks

    def _rescue_corrupt_file(self) -> None:
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(self.path, self.path.with_name(f"tasks-corrupt-{stamp}.json"))
        except Exception:
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "tasks": [t.to_dict() for t in self._tasks]}
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self._maybe_backup()

    def _maybe_backup(self) -> None:
        today = date.today()
        if self._last_backup_day == today:
            return
        self._last_backup_day = today
        try:
            target = paths.backup_dir() / f"tasks-{today.isoformat()}.json"
            if not target.exists():
                shutil.copy2(self.path, target)
            self._prune_backups()
        except Exception:
            pass

    def _prune_backups(self, keep: int = 30) -> None:
        try:
            files = sorted(paths.backup_dir().glob("tasks-*.json"))
            for old in files[:-keep]:
                old.unlink(missing_ok=True)
        except Exception:
            pass

    # ---------- 查询 ----------

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks)

    def get(self, task_id: str) -> Task | None:
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def in_range(self, start: date, end: date) -> list[Task]:
        return [t for t in self._tasks if t.start <= end and t.end >= start]

    def on_day(self, day: date) -> list[Task]:
        return [t for t in self._tasks if t.covers(day)]

    # ---------- 修改 ----------

    def add(self, title: str, start: date, end: date | None = None, color: str = "blue") -> Task:
        task = Task(
            id=uuid.uuid4().hex,
            title=title,
            start=start,
            end=end or start,
            color=color,
            created=_now(),
            updated=_now(),
        )
        self._tasks.append(task)
        if self.auto_merge:
            self.merge_contiguous()
        self.save()
        return task

    def merge_contiguous(self) -> int:
        """把标题相同的相邻（或重叠）任务并成一条，返回并掉的条数。

        这样「周一加了跑步、周二又加了跑步」会变成一条 周一~周二 的横条，
        而不是两个孤立的方块。
        """
        buckets: dict[str, list[Task]] = {}
        for task in self._tasks:
            key = task.title.strip().lower()
            buckets.setdefault(key, []).append(task)

        merged: list[Task] = []
        removed = 0
        for key, group in buckets.items():
            if not key or len(group) == 1:
                merged.extend(group)
                continue
            group.sort(key=lambda t: (t.start, t.end))
            current = group[0]
            for candidate in group[1:]:
                if candidate.start <= current.end + timedelta(days=1):
                    current.end = max(current.end, candidate.end)
                    current.done = current.done and candidate.done
                    current.updated = _now()
                    removed += 1
                else:
                    merged.append(current)
                    current = candidate
            merged.append(current)
        if removed:
            self._tasks = merged
        return removed

    def add_many(self, title: str, days: list[date], color: str = "theme") -> int:
        """一次加很多天（用于每天/每周几/每月几号的重复日程），只写一次文件。"""
        if not days or not title.strip():
            return 0
        stamp = _now()
        for day in days:
            self._tasks.append(
                Task(
                    id=uuid.uuid4().hex,
                    title=title.strip(),
                    start=day,
                    end=day,
                    color=color,
                    created=stamp,
                    updated=stamp,
                )
            )
        if self.auto_merge:
            self.merge_contiguous()
        self.save()
        return len(days)

    def update(self, task_id: str, **changes) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        for key, value in changes.items():
            if hasattr(task, key):
                setattr(task, key, value)
        if task.end < task.start:
            task.end = task.start
        task.title = task.title.strip()
        task.updated = _now()
        self.save()
        return task

    def move(self, task_id: str, delta_days: int) -> Task | None:
        task = self.get(task_id)
        if task is None or delta_days == 0:
            return task
        task.start = task.start + timedelta(days=delta_days)
        task.end = task.end + timedelta(days=delta_days)
        task.updated = _now()
        self.save()
        return task

    def remove(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]
        self.save()

    def toggle_done(self, task_id: str) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        task.done = not task.done
        task.updated = _now()
        self.save()
        return task

    def purge_empty(self) -> None:
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.title.strip()]
        if len(self._tasks) != before:
            self.save()
