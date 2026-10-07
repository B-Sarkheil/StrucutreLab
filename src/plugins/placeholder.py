"""Placeholder page and plugin for tools that are not implemented yet."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.plugins.base import Plugin


class PlaceholderPage(QWidget):
    """Simple page telling the user that a tool is not available yet."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")

        description_label = QLabel(description)
        description_label.setObjectName("pageSubtitle")
        description_label.setWordWrap(True)

        status_label = QLabel("Under development")
        status_label.setObjectName("plannedBadge")

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addSpacing(16)
        layout.addWidget(status_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()


class PlaceholderPlugin(Plugin):
    """Plugin for a planned tool; opens a PlaceholderPage."""

    available = False

    def __init__(self, name: str, title: str, icon: str, description: str):
        self.name = name
        self.title = title
        self.icon = icon
        self.description = description

    def create_widget(self) -> QWidget:
        return PlaceholderPage(self.title, self.description)
