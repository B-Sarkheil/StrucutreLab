"""Structure Lab application entry point."""

import ctypes
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .plugins.registry import register_builtin_plugins
from .ui.main_window import MainWindow
from .ui.theme import LOGO_ICO, apply_theme
from .version import __version__

APP_USER_MODEL_ID = "StructureLab.App"


def main() -> int:
    """Start the Structure Lab application."""

    # Without this, Windows groups the app under python.exe and the
    # taskbar shows the Python icon instead of ours.
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )

    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(str(LOGO_ICO)))

    apply_theme(app)
    register_builtin_plugins()

    window = MainWindow(version=__version__)
    window.show()

    return app.exec()


def ping_app() -> bool:
    """Return True when the application can be imported successfully."""
    return True


if __name__ == "__main__":
    raise SystemExit(main())