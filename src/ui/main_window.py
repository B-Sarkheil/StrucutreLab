"""Main window. TODO: sidebar listing plugins, content area for the active plugin."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self, version: str) -> None:
        super().__init__()
        self.setWindowTitle(f"Structure Lab {version}")
        self.resize(1100, 700)
        self.setCentralWidget(QLabel("Structure Lab"))


def run(version: str) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(version)
    win.show()
    return app.exec()
