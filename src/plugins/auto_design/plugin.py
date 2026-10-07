"""Registers Auto Design in the UI. TODO: real page."""
from __future__ import annotations

from src.plugins.base import Plugin
from src.plugins.placeholder import PlaceholderPage


class AutoDesignPlugin(Plugin):
    name = "auto_design"
    title = "Auto Design"
    icon = "auto_design.png"
    description = "Automatic structural design using genetic algorithm."

    def create_widget(self):
        # TODO: replace with the real page (auto_design/ui/page.py) once it exists.
        return PlaceholderPage(self.title, self.description)