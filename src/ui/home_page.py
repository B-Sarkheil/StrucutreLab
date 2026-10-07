"""Home page: hero banner, available tools and planned tools.

Tools that exist get a large card; tools that are only planned get a
quiet dashed row (dashed = not built yet, as on a drawing).
"""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..plugins.base import Plugin
from .theme import AMBER, INK, INK_HI, INK_RAISED, RULE, RULE_HI, STEEL_DIM
from .widgets import ClickableFrame, HeroBanner, draw_corner_ticks, mix


def _ignore_mouse(*widgets: QWidget) -> None:
    """Let the parent card receive clicks that land on these widgets."""

    for widget in widgets:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class PluginCard(ClickableFrame):
    """Large card for a tool that can be opened."""

    RADIUS = 12
    ICON_SIZE = 64
    ASSETS_DIR = Path(__file__).parent / "assets" / "icons"

    def __init__(self, plugin: Plugin, parent=None):
        super().__init__(parent)

        self.setObjectName("pluginCard")
        self.setMinimumHeight(104)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(18)

        icon_label = QLabel()
        icon_label.setObjectName("pluginIcon")
        icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_path = self.ASSETS_DIR / plugin.icon
        pixmap = QPixmap(str(icon_path))

        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(
                    self.ICON_SIZE,
                    self.ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        title_label = QLabel(plugin.title)
        title_label.setObjectName("pluginTitle")

        description_label = QLabel(plugin.description)
        description_label.setObjectName("pluginDescription")
        description_label.setWordWrap(True)

        _ignore_mouse(icon_label, title_label, description_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.addStretch()
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)
        text_layout.addStretch()

        layout.addWidget(icon_label)
        layout.addLayout(text_layout, 1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self.emphasis

        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.fillPath(path, QBrush(mix(INK_RAISED, INK_HI, t)))
        painter.setPen(QPen(mix(RULE, RULE_HI, t), 1))
        painter.drawPath(path)

        # Sheet-corner marks turn amber when the card is hovered or focused.
        draw_corner_ticks(painter, rect, mix(RULE_HI, AMBER, t))


class PlannedRow(ClickableFrame):
    """Compact dashed row for a tool that is planned but not built."""

    RADIUS = 10
    ICON_SIZE = 28
    ASSETS_DIR = Path(__file__).parent / "assets" / "icons"

    def __init__(self, plugin: Plugin, parent=None):
        super().__init__(parent)

        self.setObjectName("plannedRow")
        self.setMinimumHeight(50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setObjectName("plannedIcon")
        icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_path = self.ASSETS_DIR / plugin.icon
        pixmap = QPixmap(str(icon_path))

        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(
                    self.ICON_SIZE,
                    self.ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        title_label = QLabel(plugin.title)
        title_label.setObjectName("plannedTitle")
        title_label.setMinimumWidth(110)

        description_label = QLabel(plugin.description)
        description_label.setObjectName("plannedDescription")
        description_label.setWordWrap(True)

        badge = QLabel("Planned")
        badge.setObjectName("plannedBadge")

        _ignore_mouse(icon_label, title_label, description_label, badge)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(description_label, 1)
        layout.addWidget(badge)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self.emphasis

        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.fillPath(path, QBrush(mix(INK, INK_RAISED, t)))

        pen = QPen(mix(RULE, STEEL_DIM, t), 1)
        pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        painter.drawPath(path)


class HomePage(QWidget):
    """Home page listing the engineering tools."""

    plugin_requested = Signal(str)

    def __init__(self, plugins: list[Plugin], parent=None):
        super().__init__(parent)

        self.setObjectName("page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        layout.addWidget(
            HeroBanner(
                "Structure Lab",
                "Engineering tools for modeling, design and optimization.",
            )
        )

        plugin_order = [
            "auto_design",
            "sld_to_sap",
            "pdms_to_sap",
            "auto_cps",
        ]

        ordered_plugins = [
            next(plugin for plugin in plugins if plugin.name == name)
            for name in plugin_order
            if any(plugin.name == name for plugin in plugins)
        ]

        available = [plugin for plugin in ordered_plugins if plugin.available]
        planned = [plugin for plugin in ordered_plugins if not plugin.available]

        if available:
            layout.addSpacing(24)
            layout.addWidget(self._section_title("Tools"))
            layout.addSpacing(10)

            for plugin in available:
                layout.addWidget(self._connect(PluginCard(plugin), plugin))
                layout.addSpacing(12)

        if planned:
            layout.addSpacing(12)
            layout.addWidget(self._section_title("Planned"))
            layout.addSpacing(10)

            for plugin in planned:
                layout.addWidget(self._connect(PlannedRow(plugin), plugin))
                layout.addSpacing(8)

        layout.addStretch()

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")

        return label

    def _connect(self, card: ClickableFrame, plugin: Plugin) -> ClickableFrame:
        """Open `plugin` when `card` is clicked."""

        card.clicked.connect(
            lambda name=plugin.name: self.plugin_requested.emit(name)
        )

        return card