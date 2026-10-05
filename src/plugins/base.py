"""Base class every tool (plugin) must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Plugin(ABC):
    name: str = ""
    title: str = ""
    icon: str = ""

    @abstractmethod
    def create_widget(self):
        """Return the QWidget shown in the main window."""
