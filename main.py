import sys

from PyQt6.QtWidgets import QApplication

import search

# 关闭 Qt 无用日志
import os
os.environ["QT_LOGGING_RULES"] = "*=false"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = search.SearchWindow()
    sys.exit(app.exec())
