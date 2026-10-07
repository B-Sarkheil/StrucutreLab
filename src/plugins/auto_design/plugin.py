"""Registers Auto Design in the UI."""
from __future__ import annotations

from src.plugins.auto_design.ui.wizard import AutoDesignWizard
from src.plugins.base import Plugin


class AutoDesignPlugin(Plugin):
    name = "auto_design"
    title = "Auto Design"
    icon = "auto_design.png"
    description = "Automatic structural design using genetic algorithm."

    def create_widget(self):
        return AutoDesignWizard()
