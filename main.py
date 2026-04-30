import sys

from PyQt6.QtWidgets import QApplication

import search


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = search.SearchWindow()
    sys.exit(app.exec())
