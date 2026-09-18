from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from typing import Any

from . import paths


@dataclass
class Settings:
    # 外观
    size_preset: str = "中"          # 小 / 中 / 大
    opacity: float = 0.94            # 面板不透明度 0.30 - 1.0
    theme: str = "auto"              # auto / dark / light
    accent: str = "blue"             # white / pink / blue / yellow / green
    show_lunar: bool = True          # 显示农历和节日
    show_weekday_header: bool = True
    merge_same_title: bool = True    # 同名的连续任务自动并成一条

    # 呼出行为
    edge: str = "right"              # right / left
    trigger_width: int = 3           # 贴边触发区的宽度（逻辑像素）
    dwell_ms: int = 180              # 需要停留多久才滑出
    hide_delay_ms: int = 380         # 鼠标离开后多久收起
    vertical_align: str = "center"   # top / center / bottom
    vertical_margin: int = 24
    animation_ms: int = 180

    # 行为
    autostart: bool = False
    backdrop: str = "translucent"    # frosted / translucent / solid

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in raw.items() if k in known}
        # 老版本留下的值做一次迁移
        if clean.get("backdrop") == "acrylic":
            clean["backdrop"] = "translucent"
        if clean.get("backdrop") not in {"frosted", "translucent", "solid"}:
            clean.pop("backdrop", None)
        if clean.get("accent") not in {"white", "pink", "blue", "yellow", "green"}:
            clean.pop("accent", None)
        # 老版本的 600ms 收起延迟感觉太迟钝，统一收快一点
        delay = clean.get("hide_delay_ms")
        if isinstance(delay, (int, float)) and delay > 450:
            clean["hide_delay_ms"] = 380
        return cls(**clean)


def load() -> Settings:
    path = paths.settings_file()
    if not path.exists():
        return Settings()
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):
            return Settings.from_dict(raw)
    except Exception:
        pass
    return Settings()


def save(settings: Settings) -> None:
    path = paths.settings_file()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(settings.to_dict(), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
