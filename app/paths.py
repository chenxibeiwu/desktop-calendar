from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

APP_NAME = "桌面月历"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_FOLDERID_Documents = _GUID(
    0xFDD39AD0,
    0x238F,
    0x46AF,
    (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
)

_FOLDERID_Desktop = _GUID(
    0xB4BFCC3A,
    0xDB2C,
    0x424C,
    (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
)


def _known_folder(guid: _GUID) -> Path | None:
    try:
        ptr = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr))
        if hr != 0 or not ptr.value:
            return None
        try:
            return Path(ptr.value)
        finally:
            ole32.CoTaskMemFree(ctypes.cast(ptr, ctypes.c_void_p))
    except Exception:
        return None


def documents_dir() -> Path:
    override = os.environ.get("DESKTOP_CAL_DOCS")
    if override:
        return Path(override)
    found = _known_folder(_FOLDERID_Documents)
    if found is not None:
        return found
    return Path.home() / "Documents"


def desktop_dir() -> Path:
    found = _known_folder(_FOLDERID_Desktop)
    if found is not None:
        return found
    return Path.home() / "Desktop"


def data_dir() -> Path:
    """任务数据和备份存放的位置，放在「文档」里方便用户自己备份。"""
    override = os.environ.get("DESKTOP_CAL_DATA")
    path = Path(override) if override else documents_dir() / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file() -> Path:
    return data_dir() / "tasks.json"


def settings_file() -> Path:
    return data_dir() / "settings.json"


def backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_root() -> Path:
    """程序自身所在目录（打包后是 exe 所在目录）。"""
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    import sys

    return bool(getattr(sys, "frozen", False))
