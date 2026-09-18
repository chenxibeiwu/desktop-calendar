"""生成 assets/icon.ico（多尺寸），供打包和快捷方式使用。"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import theme  # noqa: E402
from app.app import render_icon_pixmap  # noqa: E402


def pixmap_png(pixmap) -> bytes:
    store = QByteArray()
    buffer = QBuffer(store)
    buffer.open(QBuffer.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(store)


def write_ico(payloads: list[tuple[int, bytes]], target: Path) -> None:
    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = 6 + 16 * len(payloads)
    entries = b""
    body = b""
    for size, data in payloads:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)
    target.write_bytes(header + entries + body)


def main() -> int:
    app = QApplication(sys.argv)
    palette = theme.DARK
    payloads = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = render_icon_pixmap(palette, size)
        pixmap.setDevicePixelRatio(1.0)
        payloads.append((size, pixmap_png(pixmap)))
    target = ROOT / "assets" / "icon.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_ico(payloads, target)
    print("saved", target, target.stat().st_size, "bytes")
    preview = ROOT / "assets" / "icon_preview.png"
    render_icon_pixmap(palette, 256).save(str(preview))
    print("preview", preview)
    _ = (app, Qt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
