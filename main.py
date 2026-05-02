import sys
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QGuiApplication

import search

# 关闭 Qt 无用日志
os.environ["QT_LOGGING_RULES"] = "*=false"

if __name__ == "__main__":
    # 高分辨率支持
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    # 设置应用程序图标
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico')
    app.setWindowIcon(QIcon(icon_path))

    window = search.SearchWindow()
    sys.exit(app.exec())
