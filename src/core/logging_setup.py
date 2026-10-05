"""Local rotating log + best-effort server log (must never raise or block)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from src.core.paths import logs_dir


def setup_logging() -> None:
    handler = RotatingFileHandler(
        logs_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def append_server_log(line: str) -> None:
    """TODO: append a line to the shared server log; retry a few times, fail silently."""
