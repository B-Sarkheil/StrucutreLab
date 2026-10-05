"""Registers Auto Design in the UI. TODO."""
from __future__ import annotations

from src.plugins.base import Plugin


class AutoDesignPlugin(Plugin):
    name = "auto_design"
    title = "Auto Design"

    def create_widget(self):
        raise NotImplementedError
