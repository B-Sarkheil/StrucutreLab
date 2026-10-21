"""SLD to SAP plugin: loads the structure from piping SLD files exported from AutoCAD."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.plugins.base import Plugin

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class SldToSapPlugin(Plugin):
    name = "sld_to_sap"
    title = "SLD to SAP"
    icon = "sld2sap.png"
    description = "Automatic loading of the structure using piping SLD."
    available = True

    def create_widget(self) -> QWidget:
        from src.plugins.sld_to_sap.ui.page import SldToSapPage

        return SldToSapPage()
