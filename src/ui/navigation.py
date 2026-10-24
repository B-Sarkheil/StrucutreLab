"""Main application navigation."""

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..plugins.base import Plugin
from .theme import AMBER
from .widgets import ClickableFrame

HOME_PAGE = "home"
ABOUT_PAGE = "about"


class NavButton(QPushButton):
    """Checkable sidebar item with an amber marker on the active page."""

    MARKER_HEIGHT = 24.0

    def __init__(self, parent=None):
        super().__init__(parent)

        self._marker = 0.0

        self._marker_animation = QVariantAnimation(self)
        self._marker_animation.setDuration(160)
        self._marker_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._marker_animation.valueChanged.connect(self._on_marker_value)

        self.toggled.connect(self._on_toggled)

    def _on_marker_value(self, value) -> None:
        self._marker = float(value)
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        self._marker_animation.stop()
        self._marker_animation.setStartValue(self._marker)
        self._marker_animation.setEndValue(1.0 if checked else 0.0)
        self._marker_animation.start()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._marker <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        height = self.MARKER_HEIGHT * self._marker
        top = (self.height() - height) / 2

        marker = QPainterPath()
        marker.addRoundedRect(QRectF(5, top, 3, height), 1.5, 1.5)

        painter.fillPath(marker, QBrush(QColor(AMBER)))


class Navigation(QWidget):
    """Left-side navigation for Structure Lab."""

    ASSETS_DIR = Path(__file__).parent / "assets" / "icons"

    page_requested = Signal(str)

    def __init__(self, version: str, plugins: list[Plugin], parent=None):
        super().__init__(parent)

        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(210)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        self._about_card: QFrame | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(6)

        # Home
        self._add_item(
            layout,
            HOME_PAGE,
            self.create_nav_button(
                "",
                "Home",
                icon_path="home.png",
            ),
        )

        # Plugins
        for plugin in plugins:
            self._add_item(
                layout,
                plugin.name,
                self.create_nav_button(
                    plugin.icon,
                    plugin.title,
                    icon_path=plugin.icon,
                    planned=not plugin.available,
                ),
            )

        self.set_current(HOME_PAGE)

        # Flexible space
        layout.addStretch()

        # About
        about = ClickableFrame()
        about.setObjectName("aboutCard")
        about.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        about.setToolTip("About Structure Lab")
        about.clicked.connect(
            lambda: self.page_requested.emit(ABOUT_PAGE)
        )
        self._about_card = about

        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(10, 10, 10, 10)
        about_layout.setSpacing(2)

        about_icon = QLabel()
        about_icon.setObjectName("aboutIcon")
        about_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        about_pixmap = QPixmap(
            str(self.ASSETS_DIR / "about.png")
        )

        if not about_pixmap.isNull():
            about_icon.setPixmap(
                about_pixmap.scaled(
                    35,
                    35,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        about_title = QLabel("About")
        about_title.setObjectName("aboutTitle")
        about_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        about_version = QLabel(f"v{version}")
        about_version.setObjectName("aboutVersion")
        about_version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        copyright_label = QLabel("Namvaran © 2026")
        copyright_label.setObjectName("copyright")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        about_layout.addWidget(about_icon)
        about_layout.addWidget(about_title)
        about_layout.addWidget(about_version)
        about_layout.addWidget(copyright_label)

        for child in (about_icon, about_title, about_version, copyright_label):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(about)

    def _add_item(
        self,
        layout: QVBoxLayout,
        key: str,
        button: QPushButton,
    ) -> None:
        """Add a navigation button and route its clicks to `page_requested`."""

        self._group.addButton(button)
        self._buttons[key] = button

        button.clicked.connect(
            lambda _checked=False, page_key=key: self.page_requested.emit(
                page_key
            )
        )

        layout.addWidget(button)

    def set_current(self, key: str) -> None:
        """Highlight the item for `key` (a plugin, Home or About)."""

        if key == ABOUT_PAGE:
            # The buttons are exclusive: release all of them to show About.
            self._group.setExclusive(False)

            for button in self._buttons.values():
                button.setChecked(False)

            self._group.setExclusive(True)
            self._set_about_active(True)
            return

        button = self._buttons.get(key)

        if button is not None:
            button.setChecked(True)

        self._set_about_active(False)

    def _set_about_active(self, active: bool) -> None:
        """Mark the About card as the current page (styled in theme.py)."""

        card = self._about_card

        if card is None:  # called before the card is built
            return

        card.setProperty("active", active)
        card.style().unpolish(card)
        card.style().polish(card)

    @classmethod
    def create_nav_button(
        cls,
        icon: str,
        title: str,
        icon_path: str | None = None,
        planned: bool = False,
    ) -> QPushButton:
        """Create a compact horizontal navigation item."""

        button = NavButton()
        button.setObjectName("navButton")
        button.setProperty("planned", planned)
        button.setCheckable(True)
        button.setFixedHeight(52)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

        button_layout = QHBoxLayout(button)
        button_layout.setContentsMargins(12, 4, 12, 4)
        button_layout.setSpacing(12)

        # Icon
        icon_label = QLabel()
        icon_label.setObjectName("navIcon")
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        if icon_path:
            path = cls.ASSETS_DIR / icon_path
            pixmap = QPixmap(str(path))

            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        40,
                        40,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        else:
            icon_label.setText(icon)

        # Title
        title_label = QLabel(title)
        title_label.setObjectName("navTitle")
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignLeft
        )
        title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        button_layout.addWidget(icon_label)
        button_layout.addWidget(title_label)
        button_layout.addStretch()

        return button