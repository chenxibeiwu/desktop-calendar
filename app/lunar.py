from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

try:
    from lunardate import LunarDate

    HAS_LUNAR = True
except Exception:  # pragma: no cover - 装不上时自动降级
    LunarDate = None  # type: ignore
    HAS_LUNAR = False


_CN_NUM = "零一二三四五六七八九十"
_LUNAR_DAY = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]
_LUNAR_MONTH = [
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "冬月", "腊月",
]

# 公历固定日期的节日
_SOLAR_FESTIVALS = {
    (1, 1): "元旦",
    (2, 14): "情人节",
    (3, 8): "妇女节",
    (3, 12): "植树节",
    (4, 1): "愚人节",
    (5, 1): "劳动节",
    (5, 4): "青年节",
    (6, 1): "儿童节",
    (7, 1): "建党节",
    (8, 1): "建军节",
    (9, 10): "教师节",
    (10, 1): "国庆节",
    (12, 25): "圣诞节",
}

_WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def weekday_label(index: int) -> str:
    return _WEEKDAY_CN[index % 7]


@lru_cache(maxsize=4096)
def lunar_info(day: date) -> tuple[str, bool]:
    """返回 (格子右上角显示的文字, 是否是节日/重要日子)。"""
    festival = _lunar_festival(day)
    if festival:
        return festival, True

    solar = _SOLAR_FESTIVALS.get((day.month, day.day))
    if solar:
        return solar, True

    if not HAS_LUNAR:
        return "", False

    try:
        lunar = LunarDate.fromSolarDate(day.year, day.month, day.day)
    except Exception:
        return "", False

    if lunar.day == 1:
        text = _LUNAR_MONTH[lunar.month - 1]
        if lunar.isLeapMonth:
            text = "闰" + text
        return text, True
    return _LUNAR_DAY[lunar.day - 1], False


def _lunar_festival(day: date) -> str | None:
    if not HAS_LUNAR:
        return None
    try:
        lunar = LunarDate.fromSolarDate(day.year, day.month, day.day)
    except Exception:
        return None
    if lunar.isLeapMonth:
        return None
    key = (lunar.month, lunar.day)
    table = {
        (1, 1): "春节",
        (1, 15): "元宵",
        (5, 5): "端午",
        (7, 7): "七夕",
        (7, 15): "中元",
        (8, 15): "中秋",
        (9, 9): "重阳",
        (12, 8): "腊八",
        (12, 23): "小年",
    }
    name = table.get(key)
    if name:
        return name
    # 除夕：第二天是正月初一
    nxt = day + timedelta(days=1)
    try:
        nl = LunarDate.fromSolarDate(nxt.year, nxt.month, nxt.day)
    except Exception:
        return None
    if nl.month == 1 and nl.day == 1 and not nl.isLeapMonth:
        return "除夕"
    return None


def today_lunar_text(day: date) -> str:
    if not HAS_LUNAR:
        return ""
    try:
        lunar = LunarDate.fromSolarDate(day.year, day.month, day.day)
    except Exception:
        return ""
    return f"{_LUNAR_MONTH[lunar.month - 1]}{_LUNAR_DAY[lunar.day - 1]}"
