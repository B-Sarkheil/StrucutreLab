"""Discover and load plugins. TODO: scan src.plugins.* for Plugin subclasses."""
from __future__ import annotations

from src.plugins.base import Plugin


def load_plugins() -> list[Plugin]:
    return []
