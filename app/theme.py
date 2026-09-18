from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Palette:
    name: str                       # light / dark
    accent_key: str
    accent_label: str
    swatch: str                     # 设置里的色块颜色
    tint: tuple[int, int, int]      # 面板底色（再乘上透明度）
    accent: str                     # 主色：今天、选中态、强调
    accent_soft: str                # 主色的浅底
    accent_text: str                # 主色底上的文字色
    text: str
    text_dim: str
    text_muted: str
    sunday: str
    saturday: str
    today_fill: str
    today_ring: str
    grid_line: str
    cell_hover: str
    weekday_band: str
    other_month_alpha: float
    header_text: str
    card_border: str
    shadow_alpha: float
    button_bg: str
    button_bg_hover: str
    button_text: str
    chip_text: str
    chip_alpha: float
    chips: dict[str, str] = field(default_factory=dict)
    solid_bg: str = "rgba(255, 255, 255, 0.96)"


_CHIPS_LIGHT = {
    "blue": "#4C7DF0",
    "red": "#E2606E",
    "orange": "#D9963A",
    "green": "#43A47B",
    "purple": "#8478DF",
    "pink": "#E77BA8",
    "gray": "#7C8697",
}

_CHIPS_DARK = {
    "blue": "#5B8CF5",
    "red": "#EC6F7C",
    "orange": "#E3A64B",
    "green": "#4FB68A",
    "purple": "#9589EC",
    "pink": "#F08CB5",
    "gray": "#8A93A6",
}

CHIP_ORDER = ["theme", "blue", "red", "orange", "green", "purple", "pink", "gray"]
CHIP_LABELS = {
    "theme": "主题色",
    "blue": "蓝",
    "red": "红",
    "orange": "橙",
    "green": "绿",
    "purple": "紫",
    "pink": "粉",
    "gray": "灰",
}


@dataclass(frozen=True)
class Accent:
    key: str
    label: str
    swatch: str
    default_chip: str
    light_tint: tuple[int, int, int]
    light_accent: str
    dark_tint: tuple[int, int, int]
    dark_accent: str


ACCENTS: dict[str, Accent] = {
    "white": Accent(
        key="white",
        label="白色",
        swatch="#F2F3F5",
        default_chip="blue",
        light_tint=(255, 255, 255),
        light_accent="#5B6575",
        dark_tint=(23, 24, 28),
        dark_accent="#C2CAD8",
    ),
    "pink": Accent(
        key="pink",
        label="粉色",
        swatch="#F06292",
        default_chip="pink",
        light_tint=(255, 243, 247),
        light_accent="#E0528A",
        dark_tint=(29, 20, 25),
        dark_accent="#F583AC",
    ),
    "blue": Accent(
        key="blue",
        label="蓝色",
        swatch="#4A7DFF",
        default_chip="blue",
        light_tint=(242, 247, 255),
        light_accent="#3B72EF",
        dark_tint=(17, 22, 32),
        dark_accent="#6D9BFF",
    ),
    "yellow": Accent(
        key="yellow",
        label="黄色",
        swatch="#F0B429",
        default_chip="orange",
        light_tint=(255, 249, 233),
        light_accent="#C98A11",
        dark_tint=(28, 24, 15),
        dark_accent="#E8B94A",
    ),
    "green": Accent(
        key="green",
        label="绿色",
        swatch="#41A572",
        default_chip="green",
        light_tint=(240, 250, 245),
        light_accent="#2F8F62",
        dark_tint=(16, 25, 21),
        dark_accent="#54BE8B",
    ),
}

ACCENT_ORDER = ["white", "pink", "blue", "yellow", "green"]


def _soft(color: str, alpha: float) -> str:
    value = color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def build(mode: str, accent_key: str, accent_chip: bool = False) -> Palette:
    accent = ACCENTS.get(accent_key) or ACCENTS["white"]
    dark = mode == "dark"
    if dark:
        return Palette(
            name="dark",
            accent_key=accent.key,
            accent_label=accent.label,
            swatch=accent.swatch,
            tint=accent.dark_tint,
            accent=accent.dark_accent,
            accent_soft=_soft(accent.dark_accent, 0.22),
            accent_text="#14161b" if accent.key == "white" else "#ffffff",
            text="#eef1f6",
            text_dim="#c6ccd9",
            text_muted="#8d95a6",
            sunday="#ec7c86",
            saturday="#7ba6e8",
            today_fill=_soft(accent.dark_accent, 0.20),
            today_ring=accent.dark_accent,
            grid_line="rgba(255, 255, 255, 0.07)",
            cell_hover="rgba(255, 255, 255, 0.06)",
            weekday_band="rgba(255, 255, 255, 0.04)",
            other_month_alpha=0.32,
            header_text="#f7f9fc",
            card_border="rgba(255, 255, 255, 0.13)",
            shadow_alpha=0.72,
            button_bg="rgba(255, 255, 255, 0.08)",
            button_bg_hover="rgba(255, 255, 255, 0.17)",
            button_text="#e8ecf4",
            chip_text="#ffffff",
            chip_alpha=0.92,
            chips=dict(_CHIPS_DARK),
            solid_bg="rgba(23, 25, 31, 0.97)",
        )
    return Palette(
        name="light",
        accent_key=accent.key,
        accent_label=accent.label,
        swatch=accent.swatch,
        tint=accent.light_tint,
        accent=accent.light_accent,
        accent_soft=_soft(accent.light_accent, 0.14),
        accent_text="#ffffff",
        text="#1d2027",
        text_dim="#414754",
        text_muted="#79808f",
        sunday="#cf4a5c",
        saturday="#3a6fb8",
        today_fill=_soft(accent.light_accent, 0.12),
        today_ring=accent.light_accent,
        grid_line="rgba(24, 30, 46, 0.075)",
        cell_hover="rgba(24, 30, 46, 0.045)",
        weekday_band="rgba(24, 30, 46, 0.022)",
        other_month_alpha=0.34,
        header_text="#171a21",
        card_border="rgba(255, 255, 255, 0.72)",
        shadow_alpha=0.42,
        button_bg="rgba(24, 30, 46, 0.055)",
        button_bg_hover="rgba(24, 30, 46, 0.12)",
        button_text="#2b3140",
        chip_text="#ffffff",
        chip_alpha=0.94,
        chips=dict(_CHIPS_LIGHT),
        solid_bg="rgba(252, 252, 254, 0.97)",
    )


def get(name: str) -> Palette:
    return build("dark" if name == "dark" else "light", "white")


def chip_color(palette: Palette, name: str) -> str:
    """任务条的取色：'theme' 表示跟随主题色。"""
    if name == "theme":
        return palette.accent
    return palette.chips.get(name) or palette.chips.get("blue", "#4C7DF0")


def system_prefers_dark() -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False
