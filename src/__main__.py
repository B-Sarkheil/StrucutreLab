"""Structure Lab application entry point."""

import ctypes
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .core.logging_setup import setup_logging
from .plugins.registry import register_builtin_plugins
from .ui.main_window import MainWindow
from .ui.theme import LOGO_ICO, apply_theme
from .ui.update_dialogs import UpdatePromptDialog
from .version import __version__

APP_USER_MODEL_ID = "StructureLab.App"

# The update window is closed by the launcher; this only protects against a
# launcher that died and left the window open.
PROMPT_SAFETY_MS = 30 * 60 * 1000


def _create_app() -> QApplication:
    """QApplication with the app icon and theme (shared by main and ask_update)."""

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

    return app


def main() -> int:
    """Start the Structure Lab application."""

    setup_logging()

    app = _create_app()
    register_builtin_plugins()

    window = MainWindow(version=__version__)
    window.show()

    # After an update: show "What's new" once the main window is up.
    QTimer.singleShot(300, window.show_release_notes_if_needed)

    return app.exec()


def ask_update(request_path: str) -> int:
    """Ask the user whether to install the new version (called by the launcher).

    `request_path` is a JSON file written by the launcher:
    ``{"current", "new", "mandatory", "notes"}``. ``notes`` (the raw
    ``release_notes`` list of latest.json) is ignored: the notes are shown
    once, after the update, in the "What's new" window.

    The answer goes to stdout, one line: ``UPDATE``, ``LATER`` or ``EXIT``.
    After ``UPDATE`` this process keeps showing the "Updating..." view until
    the launcher terminates it.
    """

    request = json.loads(Path(request_path).read_text(encoding="utf-8-sig"))

    current = str(request["current"])
    new = str(request["new"])
    mandatory = bool(request.get("mandatory"))

    app = _create_app()

    dialog = UpdatePromptDialog(current, new, mandatory)

    def report(choice: str) -> None:
        if sys.stdout is not None:
            print(choice.upper(), flush=True)

    dialog.chosen.connect(report)

    QTimer.singleShot(PROMPT_SAFETY_MS, app.quit)

    dialog.exec()

    return 0


def ping_app() -> bool:
    """Return True when the application can be imported successfully."""
    return True


if __name__ == "__main__":
    raise SystemExit(main())
