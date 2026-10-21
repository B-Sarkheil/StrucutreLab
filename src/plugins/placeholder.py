"""Placeholder page and plugin for tools that are not implemented yet."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.plugins.base import Plugin

# src/ui/assets/icons/under_development.png
UNDER_DEVELOPMENT_IMAGE = (
    Path(__file__).resolve().parent.parent
    / "ui"
    / "assets"
    / "icons"
    / "under_development.png"
)

# The image is shrunk to this width if it is wider (never enlarged).
IMAGE_MAX_WIDTH = 420


def _under_development_label() -> QLabel:
    """Return the "under development" image, or the old text if it is missing."""

    pixmap = QPixmap(str(UNDER_DEVELOPMENT_IMAGE))

    if pixmap.isNull():
        label = QLabel("Under development")
        label.setObjectName("plannedBadge")
        return label

    if pixmap.width() > IMAGE_MAX_WIDTH:
        pixmap = pixmap.scaledToWidth(
            IMAGE_MAX_WIDTH,
            Qt.TransformationMode.SmoothTransformation,
        )

    label = QLabel()
    label.setObjectName("underDevelopmentImage")
    label.setPixmap(pixmap)

    return label

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

        layout.addWidget(title_label)
        layout.addWidget(description_label)

        # Equal stretch above and below centers the image in the free space.
        layout.addStretch(1)
        layout.addWidget(
            _under_development_label(), 0, Qt.AlignmentFlag.AlignHCenter
        )
        layout.addStretch(1)
        
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