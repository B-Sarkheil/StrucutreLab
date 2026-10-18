"""Entry point. The names main() and ping_app() are part of the frozen contract."""
from __future__ import annotations

import sys

from src.version import __version__


def ping_app() -> bool:
    """Self-check used by the launcher after each update. Always True."""
    return True


def main() -> int:
    # TODO: setup logging, create QApplication, load plugins, show main window
    from src.core.logging_setup import setup_logging
    from src.ui.main_window import run

    setup_logging()
    return run(version=__version__)


if __name__ == "__main__":
    sys.exit(main())
