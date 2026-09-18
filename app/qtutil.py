from __future__ import annotations

import re

from PySide6.QtGui import QColor

_RGBA_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", re.I
)


def qcolor(spec: str, alpha: float | None = None) -> QColor:
    """支持 '#rrggbb' / '#rgb' / 'rgb(...)' / 'rgba(...)'。"""
    if not spec:
        return QColor(0, 0, 0, 0)
    match = _RGBA_RE.match(spec.strip())
    if match:
        r, g, b = (int(match.group(i)) for i in (1, 2, 3))
        a = float(match.group(4)) if match.group(4) is not None else 1.0
        color = QColor(r, g, b)
        color.setAlphaF(a if alpha is None else alpha)
        return color
    color = QColor(spec)
    if alpha is not None:
        color.setAlphaF(alpha)
    return color


def with_alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(max(0.0, min(1.0, alpha)))
    return out


def apply_stylesheet(widget, sheet: str) -> None:
    """给带子控件的窗口设置样式表。

    Qt 有个坑：子控件已经建好之后再 setStyleSheet，子控件往往不会重新应用新样式，
    这里清空一次并强制重新 polish，保证换主题时真的会变。
    """
    from PySide6.QtWidgets import QWidget

    widget.setStyleSheet("")
    widget.setStyleSheet(sheet)
    for child in widget.findChildren(QWidget):
        style = child.style()
        style.unpolish(child)
        style.polish(child)
    child_style = widget.style()
    child_style.unpolish(widget)
    child_style.polish(widget)
