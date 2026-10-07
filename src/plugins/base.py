"""Base class every Structure Lab plugin must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class Plugin(ABC):
    """Base interface for Structure Lab plugins."""

    name: str = ""
    title: str = ""
    icon: str = ""
    description: str = ""

    # False for tools that are only planned; the UI shows them as such.
    available: bool = True

    @abstractmethod
    def create_widget(self) -> QWidget:
        """Return the main QWidget shown for this plugin."""
        raise NotImplementedError