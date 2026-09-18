from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.app import DesktopCalendar

MUTEX_NAME = "Global\\DesktopCalendarWidget_SingleInstance"


def acquire_single_instance() -> bool:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        return True
    ERROR_ALREADY_EXISTS = 183
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def main() -> int:
    if not acquire_single_instance():
        app = QApplication(sys.argv)
        QMessageBox.information(None, "桌面月历", "桌面月历已经在运行了。\n把鼠标移到屏幕右边缘就能呼出。")
        return 0

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("桌面月历")
    app.setApplicationDisplayName("桌面月历")
    app.setQuitOnLastWindowClosed(False)

    calendar = DesktopCalendar(app)
    calendar.start()
    if "--demo-add" in sys.argv:
        # 调试用：直接打开「添加日程」，方便截图检查
        calendar.timer.stop()
        calendar.show_panel(instant=True)
        calendar.panel.open_add_schedule()
        return app.exec()
    if "--pin" in sys.argv:
        # 调试用：固定显示，不自动收起
        calendar.timer.stop()
        calendar.show_panel(instant=True)
        return app.exec()
    if "--show" in sys.argv:
        calendar.show_panel(instant=True)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
