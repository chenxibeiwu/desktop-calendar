from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

WCA_ACCENT_POLICY = 19

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3

DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2
DWMSBT_TRANSIENTWINDOW = 3
DWMSBT_TABBEDWINDOW = 4


class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(ACCENTPOLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _hwnd(widget) -> int:
    return int(widget.winId())


def set_acrylic(hwnd: int, rgb: tuple[int, int, int], opacity: int, blur: bool = True) -> bool:
    """整块面板的毛玻璃效果。opacity 0-255。"""
    r, g, b = rgb
    alpha = max(0, min(255, int(opacity)))
    gradient = (alpha << 24) | (b << 16) | (g << 8) | r
    policy = ACCENTPOLICY()
    policy.AccentState = (
        ACCENT_ENABLE_ACRYLICBLURBEHIND if blur else ACCENT_ENABLE_BLURBEHIND
    )
    policy.AccentFlags = 0x20 | 0x40 | 0x80 | 0x100
    policy.GradientColor = gradient
    policy.AnimationId = 0
    data = WINCOMPATTRDATA()
    data.Attribute = WCA_ACCENT_POLICY
    data.Data = ctypes.pointer(policy)
    data.SizeOfData = ctypes.sizeof(policy)
    set_attr = getattr(user32, "SetWindowCompositionAttribute", None)
    if set_attr is None:
        return False
    set_attr.argtypes = [wintypes.HWND, ctypes.POINTER(WINCOMPATTRDATA)]
    set_attr.restype = wintypes.BOOL
    try:
        return bool(set_attr(wintypes.HWND(hwnd), ctypes.byref(data)))
    except Exception:
        return False


def clear_acrylic(hwnd: int) -> None:
    policy = ACCENTPOLICY()
    policy.AccentState = ACCENT_DISABLED
    policy.AccentFlags = 0
    policy.GradientColor = 0
    policy.AnimationId = 0
    data = WINCOMPATTRDATA()
    data.Attribute = WCA_ACCENT_POLICY
    data.Data = ctypes.pointer(policy)
    data.SizeOfData = ctypes.sizeof(policy)
    set_attr = getattr(user32, "SetWindowCompositionAttribute", None)
    if set_attr:
        try:
            set_attr(wintypes.HWND(hwnd), ctypes.byref(data))
        except Exception:
            pass


def set_dark_titlebar(hwnd: int, dark: bool) -> None:
    try:
        value = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def set_round_corners(hwnd: int, preference: int) -> None:
    try:
        value = ctypes.c_int(preference)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def apply_round_region(hwnd: int, width: int, height: int, radius: int) -> bool:
    """用窗口区域把方形窗口裁成圆角，这样毛玻璃也会跟着变圆角。"""
    if radius <= 0:
        return False
    try:
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        region = gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, radius, radius)
        if not region:
            return False
        user32.SetWindowRgn(wintypes.HWND(hwnd), region, True)
        return True
    except Exception:
        return False


AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "DesktopCalendarWidget"


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --autostart'
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    launcher = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{launcher}" "{script}" --autostart'


def is_autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return bool(value)
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    import winreg

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def open_folder(path: str) -> None:
    try:
        os.startfile(path)  # noqa: S606
    except Exception:
        pass


def executable_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py"
    )


def create_desktop_shortcut() -> str | None:
    """用 PowerShell 建一个桌面快捷方式，返回快捷方式路径。"""
    import subprocess

    from . import paths

    exe = executable_path()
    working = os.path.dirname(exe)
    target = paths.desktop_dir() / "桌面月历.lnk"
    if getattr(sys, "frozen", False):
        target_path = exe
        arguments = ""
        icon = exe
    else:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        target_path = pythonw if os.path.exists(pythonw) else sys.executable
        arguments = f'"{exe}"'
        icon = target_path
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{target}'); "
        f"$s.TargetPath = '{target_path}'; "
        f"$s.Arguments = '{arguments}'; "
        f"$s.WorkingDirectory = '{working}'; "
        f"$s.IconLocation = '{icon}'; "
        "$s.Description = '桌面月历 - 鼠标移到屏幕右边缘呼出'; "
        "$s.Save()"
    )
    creation_flags = 0x08000000  # CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            creationflags=creation_flags,
            timeout=30,
        )
        if result.returncode == 0 and target.exists():
            return str(target)
    except Exception:
        return None
    return None
