"""Auto Design - step 4.1: linked frames (frames that must always get the same section).

Between the Frame types page (step 3) and the Constraint settings page (step 4.2).
The user can say that two or more frames must always have the SAME section:
the frames of a group become ONE gene of the algorithm (see
`services/gene_groups.py`). The constraint is optional: Next with no group
is fine.

The page:

* in a worker thread opens the reference model and reads the section and the
  position of every frame (the frame list and the types come from step 3,
  `set_roles`),
* shows a table (Frame, Type, Section, X / Y / Z of the middle of the frame,
  Link group). Click a header to sort (to find the frames of one axis or one
  level); the filters are the frame name (`*`, `?`, comma), the type and the
  link state,
* **Link selected** (Ctrl+L) makes a group from the selected rows (Ctrl / Shift
  + click, or drag). A frame that is already in a group: the user decides
  between *Merge groups* and *Move frames*. **Unlink selected** (Ctrl+U) takes
  the selected frames out of their groups (a group left with one frame
  disappears),
* every group has a colored chip, in the table and in the side panel; the
  panel lists the groups (click = select its frames), can rename and dissolve
  them and draws how much shorter the DNA of the algorithm became.

Next emits the list of groups (`list[tuple[str, ...]]`, frames in SAP order).
The page is created once per reference file, so the groups survive Back / Next.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from PySide6.QtCore import (
    QItemSelectionModel,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QThread,
    QVariantAnimation,
    QEasingCurve,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.frame_assignments import read_frame_sections
from src.plugins.auto_design.services.model_geometry import (
    read_frame_connectivity,
    read_joint_coordinates,
)
from src.plugins.auto_design.services.population import ROLE_LABELS, ROLES
from src.plugins.auto_design.ui.fields import FORM_STYLE
from src.plugins.auto_design.ui.roles_page import DONE_COLOR, ROLE_COLORS, _FlashFrame
from src.plugins.auto_design.ui.sections_page import compile_name_filter
from src.ui.theme import (
    AMBER,
    BLUE,
    CYAN,
    DANGER,
    FONT_TITLE,
    INK_DEEP,
    INK_HI,
    INK_RAISED,
    PAPER,
    RULE,
    RULE_HI,
    STEEL,
    STEEL_DIM,
)
from src.ui.widgets import arrow_icon, with_alpha

logger = logging.getLogger(__name__)

HEADERS = ["Frame", "Type", "Section", "X (m)", "Y (m)", "Z (m)", "Link group"]
COL_FRAME, COL_TYPE, COL_SECTION, COL_X, COL_Y, COL_Z, COL_LINK = range(7)

ROLE_KEY = Qt.ItemDataRole.UserRole  # role of the frame (Type column) / group number (Link column)
SORT_KEY = Qt.ItemDataRole.UserRole + 1  # value used to sort the column

# One color per group (they repeat after 12 groups).
GROUP_COLORS = (
    "#3DDC97", "#B48CFF", "#FF8F6B", "#4FD1FF", "#FFC24D", "#FF6FA5",
    "#7BE06B", "#6C8CFF", "#F0E05A", "#E36BFF", "#4DE0D2", "#FF7A7A",
)

PAGE_STYLE = f"""
    QFrame#tableCard {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-radius: 12px;
    }}
    QFrame#linkPanel {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-left: 3px solid {CYAN};
        border-radius: 12px;
    }}
    QTableWidget#linksTable {{
        background: transparent;
        border: none;
        outline: none;
        color: {PAPER};
    }}
    QTableWidget#linksTable::item {{
        padding: 0 10px;
        border-bottom: 1px solid {RULE};
    }}
    QTableWidget#linksTable::item:hover {{
        background: {INK_HI};
    }}
    QTableWidget#linksTable QHeaderView::section {{
        background: {INK_DEEP};
        color: {STEEL};
        border: none;
        border-bottom: 1px solid {RULE_HI};
        border-right: 1px solid {RULE};
        padding: 6px 10px;
        font-weight: 600;
    }}
    QLabel#statusText, QLabel#summaryText, QLabel#toolLabel {{
        background: transparent;
        color: {STEEL};
    }}
    QLabel#statusText[result="true"] {{
        color: {CYAN};
        font-size: 10.5pt;
        font-weight: 600;
    }}
    QLabel#statusText[warn="true"] {{
        color: {AMBER};
        font-weight: 600;
    }}
    QLabel#toolLabel {{
        font-weight: 600;
    }}
    QLabel#statusError {{
        background: transparent;
        color: {DANGER};
    }}
    QLabel#panelTitle {{
        background: transparent;
        color: {CYAN};
        font-family: "{FONT_TITLE}";
        font-size: 11.5pt;
        font-weight: 700;
        letter-spacing: 2px;
    }}
    QLabel#panelHint {{
        background: transparent;
        color: {STEEL_DIM};
        font-size: 9.5pt;
    }}
    QListWidget#groupList {{
        background: transparent;
        border: none;
        outline: none;
    }}
    QListWidget#groupList QWidget#qt_scrollarea_viewport {{
        background: transparent;
    }}
    QProgressBar#loadingBar {{
        background: {INK_HI};
        border: none;
        border-radius: 2px;
        max-height: 4px;
    }}
    QProgressBar#loadingBar::chunk {{
        background: {CYAN};
        border-radius: 2px;
    }}
    QPushButton#linkButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {BLUE}, stop:1 #2A9BD8);
        color: #FFFFFF;
        border: 2px solid {CYAN};
        border-radius: 10px;
        font-weight: 700;
        padding: 4px 16px;
    }}
    QPushButton#linkButton:hover:enabled {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #2A7DC8, stop:1 #46B6EE);
        border-color: {AMBER};
    }}
    QPushButton#linkButton:pressed:enabled {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #185C99, stop:1 #2A9BD8);
        border-color: {AMBER};
    }}
    QPushButton#linkButton:disabled {{
        background: {INK_HI};
        color: {STEEL_DIM};
        border-color: {RULE};
    }}
"""


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------


def group_color(group_id: int) -> str:
    return GROUP_COLORS[(group_id - 1) % len(GROUP_COLORS)]


def _natural_key(text: str) -> str:
    """Text that sorts "2" before "10" (digits padded)."""

    return re.sub(r"\d+", lambda m: m.group().zfill(10), text.lower())


def _chain_icon(size: int = 24, broken: bool = False, color: str = "#FFFFFF") -> QIcon:
    """Two chain links (joined, or apart when `broken`), drawn in code."""

    icon = QIcon()
    scale = 2  # draw at 2x so it stays sharp on high-DPI screens

    for mode, tone in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, STEEL_DIM)):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(scale)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(tone), size * 0.11)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.translate(size / 2, size / 2)
        painter.rotate(-45)

        width, height = size * 0.52, size * 0.28
        shift = size * 0.16 if broken else 0.0
        painter.drawRoundedRect(
            QRectF(-width * 0.95 - shift, -height / 2, width, height), height / 2, height / 2
        )
        painter.drawRoundedRect(
            QRectF(-width * 0.05 + shift, -height / 2, width, height), height / 2, height / 2
        )
        painter.end()
        icon.addPixmap(pixmap, mode)

    return icon


class _SortItem(QTableWidgetItem):
    """Item that sorts by the value stored in SORT_KEY."""

    def __lt__(self, other) -> bool:
        mine, theirs = self.data(SORT_KEY), other.data(SORT_KEY)

        if mine is None or theirs is None:
            return super().__lt__(other)

        try:
            return mine < theirs
        except TypeError:
            return str(mine) < str(theirs)


def _item(text: str, sort_key, align=None) -> _SortItem:
    item = _SortItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    item.setData(SORT_KEY, sort_key)

    if align is not None:
        item.setTextAlignment(align)

    return item


@dataclass
class _Group:
    gid: int
    name: str
    frames: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------


class _LinksLoader(QThread):
    """Opens the reference model and reads what the table shows (off the UI thread)."""

    loaded = Signal(object, object, object)  # frameSections, connectivity, coordinates
    failed = Signal(str)

    def __init__(self, client: SapClient, sap_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._client = client
        self._sap_path = sap_path

    def run(self) -> None:
        try:
            self._client.open_model(self._sap_path)
            frame_sections = read_frame_sections(self._client)
            connectivity = read_frame_connectivity(self._client)
            coordinates = read_joint_coordinates(self._client)
        except Exception as exc:
            logger.exception("Could not read the frames from SAP2000")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.loaded.emit(frame_sections, connectivity, coordinates)


# ---------------------------------------------------------------------
# Delegates
# ---------------------------------------------------------------------


class _TableDelegate(QStyledItemDelegate):
    """Type cells: colored dot + name. Link cells: a colored chip with the
    name of the group. Selected rows get a cyan tint."""

    def paint(self, painter, option, index):
        column = index.column()

        if column in (COL_TYPE, COL_LINK):
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""

            widget = opt.widget
            style = widget.style() if widget is not None else QApplication.style()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            if column == COL_TYPE:
                self._paint_type(painter, opt, index)
            else:
                self._paint_chip(painter, opt, index)

            painter.restore()
        else:
            super().paint(painter, option, index)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.fillRect(option.rect, with_alpha(CYAN, 30))
            painter.restore()

    @staticmethod
    def _paint_type(painter: QPainter, opt, index) -> None:
        role = index.data(ROLE_KEY)
        rect = QRectF(opt.rect)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ROLE_COLORS.get(role, STEEL)))
        painter.drawEllipse(QPointF(rect.left() + 16, rect.center().y()), 4.5, 4.5)

        painter.setFont(opt.font)
        painter.setPen(QColor(PAPER))
        painter.drawText(
            QRectF(rect.left() + 30, rect.top(), rect.width() - 34, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            ROLE_LABELS.get(role, ""),
        )

    @staticmethod
    def _paint_chip(painter: QPainter, opt, index) -> None:
        group_id = index.data(ROLE_KEY) or 0
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        rect = QRectF(opt.rect)

        if not group_id:
            painter.setFont(opt.font)
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                rect.adjusted(14, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "—",
            )
            return

        color = QColor(group_color(group_id))
        font = QFont(opt.font)
        font.setBold(True)
        painter.setFont(font)

        width = min(QFontMetrics(font).horizontalAdvance(text) + 34, rect.width() - 14)
        chip = QRectF(rect.left() + 8, rect.center().y() - 11, width, 22)

        shape = QPainterPath()
        shape.addRoundedRect(chip, 11, 11)
        painter.fillPath(shape, QBrush(with_alpha(color, 55)))
        painter.setPen(QPen(color, 1.4))
        painter.drawPath(shape)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(chip.left() + 11, chip.center().y()), 3.6, 3.6)

        painter.setPen(QColor(PAPER))
        painter.drawText(
            QRectF(chip.left() + 21, chip.top(), chip.width() - 24, chip.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )


class _GroupDelegate(QStyledItemDelegate):
    """One group in the side panel: color bar, name, number of frames."""

    ROW = 52

    def sizeHint(self, option, index):
        return QSize(0, self.ROW)

    def paint(self, painter, option, index):
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        color = QColor(group_color(index.data(ROLE_KEY) or 1))
        hot = bool(option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        shape = QPainterPath()
        shape.addRoundedRect(rect, 9, 9)
        painter.fillPath(shape, QBrush(QColor(INK_HI if hot else INK_DEEP)))
        painter.setPen(QPen(with_alpha(color, 170) if hot else QColor(RULE_HI), 1.2))
        painter.drawPath(shape)

        bar = QPainterPath()
        bar.addRoundedRect(QRectF(rect.left() + 8, rect.top() + 9, 5, rect.height() - 18), 2.5, 2.5)
        painter.fillPath(bar, QBrush(color))

        name_font = QFont(option.font)
        name_font.setBold(True)
        name_font.setPointSizeF(10.5)
        painter.setFont(name_font)
        painter.setPen(QColor(PAPER))
        painter.drawText(
            QRectF(rect.left() + 22, rect.top() + 5, rect.width() - 30, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data(Qt.ItemDataRole.DisplayRole) or "",
        )

        sub_font = QFont(option.font)
        sub_font.setPointSizeF(8.5)
        painter.setFont(sub_font)
        painter.setPen(QColor(STEEL_DIM))
        sub = QFontMetrics(sub_font).elidedText(
            index.data(SORT_KEY) or "", Qt.TextElideMode.ElideRight, int(rect.width() - 30)
        )
        painter.drawText(
            QRectF(rect.left() + 22, rect.top() + 26, rect.width() - 30, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            sub,
        )
        painter.restore()


# ---------------------------------------------------------------------
# DNA bar
# ---------------------------------------------------------------------


class GeneBar(QWidget):
    """Two bars that show how much shorter the DNA of the algorithm is:
    one gene per frame (full) against one gene per unit (animated)."""

    HEIGHT = 120

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setFixedHeight(self.HEIGHT)

        self._total = 0
        self._genes = 0
        self._shown = 1.0

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(550)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_value)

    def set_values(self, total: int, genes: int) -> None:
        self._total = total
        self._genes = genes
        target = genes / total if total else 1.0

        self._animation.stop()

        if not self.isVisible():
            self._shown = target
            self.update()
            return

        self._animation.setStartValue(self._shown)
        self._animation.setEndValue(target)
        self._animation.start()

    def _on_value(self, value) -> None:
        self._shown = float(value)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._shown = self._genes / self._total if self._total else 1.0

    def _bar(self, painter: QPainter, y: float, width: float, fraction: float, strong: bool) -> None:
        track = QRectF(0, y, width, 12)
        shape = QPainterPath()
        shape.addRoundedRect(track, 6, 6)
        painter.fillPath(shape, QBrush(QColor(INK_DEEP)))

        fill_width = max(track.width() * fraction, 0.0)

        if fill_width > 1.0:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(0, y, fill_width, 12), 6, 6)
            gradient = QLinearGradient(0, 0, width, 0)

            if strong:
                gradient.setColorAt(0.0, QColor(BLUE))
                gradient.setColorAt(0.6, QColor(CYAN))
                gradient.setColorAt(1.0, QColor(DONE_COLOR))
            else:
                gradient.setColorAt(0.0, QColor(RULE_HI))
                gradient.setColorAt(1.0, QColor(STEEL_DIM))

            painter.fillPath(fill, QBrush(gradient))

            if strong and fraction < 0.999:
                head = QPen(QColor(AMBER), 2.2)
                head.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(head)
                painter.drawLine(QPointF(fill_width, y - 2), QPointF(fill_width, y + 14))

        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = float(self.width())
        small = QFont(self.font())
        small.setPointSizeF(8.5)
        bold = QFont(small)
        bold.setBold(True)

        def line(y: float, left: str, right: str) -> None:
            painter.setFont(small)
            painter.setPen(QColor(STEEL))
            painter.drawText(
                QRectF(0, y, width, 16),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                left,
            )
            painter.setFont(bold)
            painter.setPen(QColor(PAPER))
            painter.drawText(
                QRectF(0, y, width, 16),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                right,
            )

        line(0, "One gene per frame", f"{self._total} genes")
        self._bar(painter, 20, width, 1.0, False)
        line(42, "With the links", f"{self._genes} genes")
        self._bar(painter, 62, width, self._shown, True)

        reduction = (1.0 - self._genes / self._total) * 100.0 if self._total else 0.0
        big = QFont(FONT_TITLE)
        big.setPointSizeF(17)
        big.setBold(True)
        painter.setFont(big)

        if reduction > 0.0:
            painter.setPen(QColor(DONE_COLOR))
            painter.drawText(
                QRectF(0, 84, width, 32),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"−{reduction:.1f} %",
            )
            painter.setFont(small)
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                QRectF(84, 84, width - 84, 32),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "shorter DNA, smaller search space",
            )
        else:
            painter.setFont(small)
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                QRectF(0, 84, width, 32),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "No links: every frame is a gene of its own.",
            )


# ---------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------


class FrameLinksPage(QWidget):
    """Linked frames (see the module docstring)."""

    back_requested = Signal()
    next_requested = Signal(object)  # list of tuples of frame names

    def __init__(self, sap_path: str, client: SapClient, parent: QWidget | None = None):
        super().__init__(parent)

        self.sap_path = sap_path
        self.client = client

        self._loader: _LinksLoader | None = None
        self._loading = False
        self._loaded = False

        self._roles: dict[str, str] = {}
        self._frame_sections: dict[str, str] = {}
        self._connectivity: dict[str, tuple[str, str]] = {}
        self._coordinates: dict[str, tuple[float, float, float]] = {}
        self._order: dict[str, int] = {}  # frame -> position in the SAP table

        self._groups: dict[int, _Group] = {}
        self._group_of: dict[str, int] = {}
        self._next_id = 1

        self._sort_col: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder

        self.setObjectName("page")
        self.setStyleSheet(FORM_STYLE + PAGE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Link the frames that must always get the same section: "
            "the frames of a group behave as one gene of the algorithm. This is optional."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        # Status line + progress + error
        self.status = QLabel("")
        self.status.setObjectName("statusText")
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setObjectName("loadingBar")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)

        self.message = QLabel("")
        self.message.setObjectName("statusError")
        self.message.setWordWrap(True)
        self.message.setVisible(False)

        layout.addWidget(self.status)
        layout.addSpacing(6)
        layout.addWidget(self.progress)
        layout.addWidget(self.message)
        layout.addSpacing(8)

        # Filters and the two actions
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by frame name:   1*    *5    10, 25*")
        self.filter_edit.setToolTip(
            "Plain text matches anywhere in the name.\n"
            "* = any characters, ? = one character.\n"
            "Use a comma to list several patterns."
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumHeight(36)
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.show_combo = QComboBox()
        self.show_combo.setMinimumHeight(36)
        self.show_combo.setMinimumWidth(150)
        self.show_combo.addItem("All types", None)

        for role in ROLES:
            self.show_combo.addItem(ROLE_LABELS[role], role)

        self.show_combo.currentIndexChanged.connect(self._apply_filter)

        self.link_combo = QComboBox()
        self.link_combo.setMinimumHeight(36)
        self.link_combo.setMinimumWidth(140)
        self.link_combo.addItem("All frames", None)
        self.link_combo.addItem("Linked only", "linked")
        self.link_combo.addItem("Not linked", "free")
        self.link_combo.currentIndexChanged.connect(self._apply_filter)

        self.link_button = QPushButton("Link selected")
        self.link_button.setObjectName("linkButton")
        self.link_button.setIcon(_chain_icon(24))
        self.link_button.setIconSize(QSize(24, 24))
        self.link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_button.setMinimumSize(170, 36)
        self.link_button.setToolTip("Make one group of the selected frames (Ctrl+L)")
        self.link_button.clicked.connect(self._link_selected)

        self.unlink_button = QPushButton("Unlink selected")
        self.unlink_button.setIcon(_chain_icon(22, broken=True, color=PAPER))
        self.unlink_button.setIconSize(QSize(22, 22))
        self.unlink_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlink_button.setMinimumHeight(36)
        self.unlink_button.setToolTip("Take the selected frames out of their groups (Ctrl+U)")
        self.unlink_button.clicked.connect(self._unlink_selected)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(self.filter_edit, 1)
        tools.addWidget(self.show_combo)
        tools.addWidget(self.link_combo)
        tools.addSpacing(8)
        tools.addWidget(self.link_button)
        tools.addWidget(self.unlink_button)
        layout.addLayout(tools)
        layout.addSpacing(10)

        # Table (left) and panel (right)
        body = QHBoxLayout()
        body.setSpacing(14)

        self.card = _FlashFrame()
        self.card.setObjectName("tableCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(6, 6, 6, 6)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setObjectName("linksTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setItemDelegate(_TableDelegate(self.table))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setFixedHeight(40)
        header.setMinimumSectionSize(60)
        header.setSectionsClickable(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_SECTION, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

        for column, width in (
            (COL_FRAME, 110), (COL_TYPE, 180), (COL_X, 84), (COL_Y, 84), (COL_Z, 84), (COL_LINK, 150),
        ):
            header.resizeSection(column, width)

        for column in (COL_X, COL_Y, COL_Z):
            self.table.horizontalHeaderItem(column).setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        header.sectionClicked.connect(self._on_header_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        card_layout.addWidget(self.table)
        body.addWidget(self.card, 1)
        body.addWidget(self._build_panel())
        layout.addLayout(body, 1)
        layout.addSpacing(8)

        # Counters
        self.summary = QLabel("")
        self.summary.setObjectName("summaryText")
        self.summary.setTextFormat(Qt.TextFormat.RichText)

        self.shown_label = QLabel("")
        self.shown_label.setObjectName("summaryText")
        self.shown_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        summary_row = QHBoxLayout()
        summary_row.addWidget(self.summary)
        summary_row.addStretch()
        summary_row.addWidget(self.shown_label)
        layout.addLayout(summary_row)
        layout.addSpacing(12)

        # Footer
        self.back_button = QPushButton("Back")
        self.back_button.setIcon(arrow_icon("left", color=PAPER))
        self.back_button.setIconSize(QSize(32, 24))
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setMinimumSize(110, 42)
        self.back_button.clicked.connect(self.back_requested.emit)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setMinimumSize(110, 42)
        self.retry_button.clicked.connect(self.start_loading)
        self.retry_button.setVisible(False)

        self.next_button = QPushButton("Next")
        self.next_button.setIcon(arrow_icon("right"))
        self.next_button.setIconSize(QSize(32, 24))
        # Right-to-left layout puts the icon after the text.
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_button.setObjectName("primaryButton")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setMinimumSize(150, 42)
        self.next_button.clicked.connect(self._on_next)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addWidget(self.back_button)
        footer.addWidget(self.retry_button)
        footer.addStretch()
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        for keys, slot in (("Ctrl+L", self._link_selected), ("Ctrl+U", self._unlink_selected)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        self._set_loading(False)
        self._update_summary()

    def _build_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("linkPanel")
        panel.setFixedWidth(320)

        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(10)

        title = QLabel("GENE LINKS")
        title.setObjectName("panelTitle")
        box.addWidget(title)

        self.gene_bar = GeneBar()
        box.addWidget(self.gene_bar)

        list_title = QLabel("Linked groups")
        list_title.setObjectName("toolLabel")
        box.addWidget(list_title)

        self.group_list = QListWidget()
        self.group_list.setObjectName("groupList")
        self.group_list.setItemDelegate(_GroupDelegate(self.group_list))
        self.group_list.setFrameShape(QFrame.Shape.NoFrame)
        self.group_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.group_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.group_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.group_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.group_list.itemClicked.connect(self._on_group_clicked)
        self.group_list.itemSelectionChanged.connect(self._sync_panel_buttons)
        box.addWidget(self.group_list, 1)

        self.empty_hint = QLabel(
            "No group yet.\nSelect two or more frames in the table\n"
            "(Ctrl / Shift + click) and press Link selected."
        )
        self.empty_hint.setObjectName("panelHint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        box.addWidget(self.empty_hint, 1)

        self.rename_button = QPushButton("Rename…")
        self.rename_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rename_button.setMinimumHeight(34)
        self.rename_button.clicked.connect(self._rename_group)

        self.dissolve_button = QPushButton("Dissolve")
        self.dissolve_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dissolve_button.setMinimumHeight(34)
        self.dissolve_button.setToolTip("Delete the group: its frames become free genes again")
        self.dissolve_button.clicked.connect(self._dissolve_group)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.dissolve_button)
        box.addLayout(buttons)

        return panel

    # -----------------------------------------------------------------
    # Result and data from the wizard
    # -----------------------------------------------------------------

    @property
    def links(self) -> list[tuple[str, ...]]:
        """The groups: tuples of frame names (SAP order), ordered by their first frame."""

        def position(frame: str) -> int:
            return self._order.get(frame, 0)

        groups = [
            tuple(sorted(group.frames, key=position))
            for group in self._groups.values()
            if len(group.frames) >= 2
        ]
        groups.sort(key=lambda frames: position(frames[0]))

        return groups

    def set_roles(self, roles: dict[str, str]) -> None:
        """The type of every frame (step 3). Called every time the page is
        reached, so a type edited on the previous page shows up here."""

        self._roles = dict(roles)

        if not self._loaded:
            return

        if set(self._roles) == set(self._order):
            self._refresh_types()
        else:
            self._fill_table()

    # -----------------------------------------------------------------
    # Loading
    # -----------------------------------------------------------------

    def start_loading(self) -> None:
        """Open the reference model and read the frames."""

        if self._loader is not None and self._loader.isRunning():
            return

        self._set_loading(True)

        self._loader = _LinksLoader(self.client, self.sap_path, self)
        self._loader.loaded.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._loader.finished.connect(self._loader.deleteLater)
        self._loader.start()

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.progress.setVisible(loading)
        self.table.setEnabled(not loading)
        self.back_button.setEnabled(not loading)
        self.retry_button.setVisible(False)
        self.message.setVisible(False)

        if loading:
            self._set_status("Reading the frames of the model…")

        self._sync_controls()

    def _on_loaded(self, frame_sections, connectivity, coordinates) -> None:
        self._frame_sections = dict(frame_sections)
        self._connectivity = dict(connectivity)
        self._coordinates = dict(coordinates)
        self._loaded = True
        self._set_loading(False)
        self._fill_table()

        self._set_status(
            f"<span style='color:{AMBER}; font-weight:700'>{len(self._order)}</span> frames. "
            "Select two or more rows (Ctrl / Shift + click) and press Link selected.",
            result=True,
        )

    def _on_failed(self, error: str) -> None:
        self._loaded = False
        self._set_loading(False)
        self._set_status("")
        self.message.setText(f"Could not read the model from SAP2000: {error}")
        self.message.setVisible(True)
        self.retry_button.setVisible(True)

    # -----------------------------------------------------------------
    # Table
    # -----------------------------------------------------------------

    def _fill_table(self) -> None:
        frames = list(self._roles)
        self._order = {frame: index for index, frame in enumerate(frames)}

        # Groups can only hold frames that exist.
        for group in list(self._groups.values()):
            gone = [f for f in group.frames if f not in self._order]

            if gone:
                self._remove_from_groups(gone)

        self.table.clearSelection()
        self.table.setRowCount(len(frames))

        center = Qt.AlignmentFlag.AlignCenter

        for row, frame in enumerate(frames):
            role = self._roles[frame]
            section = self._frame_sections.get(frame, "")

            self.table.setItem(row, COL_FRAME, _item(frame, _natural_key(frame)))

            type_item = _item(ROLE_LABELS[role], ROLE_LABELS[role].lower())
            type_item.setData(ROLE_KEY, role)
            self.table.setItem(row, COL_TYPE, type_item)

            self.table.setItem(row, COL_SECTION, _item(section, _natural_key(section)))

            middle = self._middle(frame)

            for offset, column in enumerate((COL_X, COL_Y, COL_Z)):
                value = middle[offset] if middle else None
                self.table.setItem(
                    row,
                    column,
                    _item("–" if value is None else f"{value:.2f}", float("-inf") if value is None else value, center),
                )

            link_item = _item("", 10**9)
            self.table.setItem(row, COL_LINK, link_item)

        self._sort_col = None
        self.table.horizontalHeader().setSortIndicatorShown(False)

        self._refresh_link_cells()
        self._refresh_group_list()
        self._apply_filter()
        self._sync_controls()

    def _middle(self, frame: str) -> tuple[float, float, float] | None:
        pair = self._connectivity.get(frame)

        if pair is None or pair[0] not in self._coordinates or pair[1] not in self._coordinates:
            return None

        a, b = self._coordinates[pair[0]], self._coordinates[pair[1]]

        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)

    def _refresh_types(self) -> None:
        for row in range(self.table.rowCount()):
            frame = self.table.item(row, COL_FRAME).text()
            role = self._roles[frame]
            item = self.table.item(row, COL_TYPE)
            item.setText(ROLE_LABELS[role])
            item.setData(ROLE_KEY, role)
            item.setData(SORT_KEY, ROLE_LABELS[role].lower())

        self.table.viewport().update()
        self._apply_filter()

    def _refresh_link_cells(self) -> None:
        for row in range(self.table.rowCount()):
            frame = self.table.item(row, COL_FRAME).text()
            group_id = self._group_of.get(frame, 0)
            item = self.table.item(row, COL_LINK)
            item.setText(self._groups[group_id].name if group_id else "")
            item.setData(ROLE_KEY, group_id)
            item.setData(SORT_KEY, group_id if group_id else 10**9)

        if self._sort_col == COL_LINK:
            self.table.sortItems(COL_LINK, self._sort_order)

        self.table.viewport().update()

    def _on_header_clicked(self, column: int) -> None:
        if self._sort_col == column:
            order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder

        self._sort_col, self._sort_order = column, order

        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(column, order)

        self.table.sortItems(column, order)
        self._apply_filter()  # the hidden state belongs to the row numbers, not to the items

    # -----------------------------------------------------------------
    # Selection and actions
    # -----------------------------------------------------------------

    def _selected_frames(self) -> list[str]:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}

        return [
            self.table.item(row, COL_FRAME).text()
            for row in sorted(rows)
            if not self.table.isRowHidden(row)
        ]

    def _on_selection_changed(self) -> None:
        self._sync_controls()

    def _link_selected(self) -> None:
        if self._loading or not self._loaded:
            return

        frames = self._selected_frames()

        if len(frames) < 2:
            self._set_status("Select two or more frames first (Ctrl / Shift + click).", warn=True)
            return

        touched = sorted({self._group_of[f] for f in frames if f in self._group_of})

        if len(touched) == 1 and all(self._group_of.get(f) == touched[0] for f in frames):
            self._set_status(
                f"These frames are already linked together in {self._groups[touched[0]].name}."
            )
            return

        mode = "new"

        if touched:
            mode = self._ask_merge_or_move(
                len(touched), sum(f in self._group_of for f in frames)
            )

            if mode is None:
                return

        if mode == "merge":
            keep = touched[0]
            members = list(frames)

            for group_id in touched:
                members.extend(self._groups[group_id].frames)

            for group_id in touched[1:]:
                self._drop_group(group_id)

            self._set_members(keep, list(dict.fromkeys(members)))
            group_id = keep
        else:
            if mode == "move":
                self._remove_from_groups(frames)

            group_id = self._create_group(frames)

        group = self._groups[group_id]
        self._after_change(
            f"<span style='color:{group_color(group_id)}; font-weight:700'>{group.name}</span> "
            f"now has {len(group.frames)} frames: they always get the same section.",
            select_group=group_id,
        )

    def _ask_merge_or_move(self, group_count: int, frame_count: int) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle("Link frames")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"{frame_count} of the selected frames already belong to "
            f"{group_count} group{'s' if group_count != 1 else ''}."
        )
        box.setInformativeText(
            "Merge groups: the new group holds the selected frames and ALL the frames "
            "of those groups.\n"
            "Move frames: only the selected frames form the new group; the old groups "
            "keep their other frames."
        )
        merge = box.addButton("Merge groups", QMessageBox.ButtonRole.ActionRole)
        move = box.addButton("Move frames", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()

        if clicked is merge:
            return "merge"

        if clicked is move:
            return "move"

        return None

    def _unlink_selected(self) -> None:
        if self._loading or not self._loaded:
            return

        linked = [f for f in self._selected_frames() if f in self._group_of]

        if not linked:
            self._set_status("None of the selected frames is in a group.", warn=True)
            return

        self._remove_from_groups(linked)
        self._after_change(f"{len(linked)} frame(s) are free again.")

    # -- groups -----------------------------------------------------------

    def _create_group(self, frames: list[str]) -> int:
        group_id = self._next_id
        self._next_id += 1
        self._groups[group_id] = _Group(group_id, f"G{group_id}")
        self._set_members(group_id, frames)

        return group_id

    def _set_members(self, group_id: int, frames: list[str]) -> None:
        self._groups[group_id].frames = sorted(
            dict.fromkeys(frames), key=lambda f: self._order.get(f, 0)
        )

        for frame in frames:
            self._group_of[frame] = group_id

    def _drop_group(self, group_id: int) -> None:
        group = self._groups.pop(group_id, None)

        if group is None:
            return

        for frame in group.frames:
            if self._group_of.get(frame) == group_id:
                del self._group_of[frame]

    def _remove_from_groups(self, frames: list[str]) -> None:
        """Take the frames out of their groups; a group left with fewer than
        two frames disappears."""

        affected: set[int] = set()

        for frame in frames:
            group_id = self._group_of.pop(frame, None)

            if group_id is None:
                continue

            self._groups[group_id].frames.remove(frame)
            affected.add(group_id)

        for group_id in affected:
            if len(self._groups[group_id].frames) < 2:
                self._drop_group(group_id)

    def _after_change(self, html: str, select_group: int | None = None) -> None:
        self._refresh_link_cells()
        self._refresh_group_list(select_group)
        self._apply_filter()
        self._sync_controls()
        self._set_status(html, result=True)
        self.card.flash()

        logger.info(
            "Linked frames: %d groups, %d linked frames",
            len(self._groups), len(self._group_of),
        )

    # -- panel ------------------------------------------------------------

    def _refresh_group_list(self, select_group: int | None = None) -> None:
        self.group_list.blockSignals(True)
        self.group_list.clear()

        for group in sorted(self._groups.values(), key=lambda g: g.gid):
            first = ", ".join(group.frames[:3]) + (" …" if len(group.frames) > 3 else "")
            item = QListWidgetItem(group.name)
            item.setData(ROLE_KEY, group.gid)
            item.setData(SORT_KEY, f"{len(group.frames)} frames  ·  {first}")
            self.group_list.addItem(item)

            if group.gid == select_group:
                self.group_list.setCurrentItem(item)

        self.group_list.blockSignals(False)

        has_groups = bool(self._groups)
        self.group_list.setVisible(has_groups)
        self.empty_hint.setVisible(not has_groups)
        self._sync_panel_buttons()

    def _current_group(self) -> int | None:
        item = self.group_list.currentItem()

        return int(item.data(ROLE_KEY)) if item is not None else None

    def _sync_panel_buttons(self) -> None:
        has_current = self._current_group() is not None
        self.rename_button.setEnabled(has_current)
        self.dissolve_button.setEnabled(has_current)

    def _on_group_clicked(self, item: QListWidgetItem) -> None:
        group = self._groups.get(int(item.data(ROLE_KEY)))

        if group is None:
            return

        members = set(group.frames)
        selection = self.table.selectionModel()
        selection.clearSelection()
        first = None
        hidden = 0

        for row in range(self.table.rowCount()):
            if self.table.item(row, COL_FRAME).text() not in members:
                continue

            if self.table.isRowHidden(row):
                hidden += 1
                continue

            index = self.table.model().index(row, 0)
            selection.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )

            if first is None:
                first = index

        if first is not None:
            self.table.scrollTo(first, QAbstractItemView.ScrollHint.PositionAtTop)

        if hidden:
            self._set_status(f"{hidden} frame(s) of {group.name} are hidden by the filter.", warn=True)

    def _rename_group(self) -> None:
        group_id = self._current_group()

        if group_id is None:
            return

        group = self._groups[group_id]
        name, accepted = QInputDialog.getText(self, "Rename group", "Name of the group:", text=group.name)
        name = name.strip()

        if not accepted or not name:
            return

        group.name = name[:24]
        self._refresh_link_cells()
        self._refresh_group_list(group_id)

    def _dissolve_group(self) -> None:
        group_id = self._current_group()

        if group_id is None:
            return

        name = self._groups[group_id].name
        self._drop_group(group_id)
        self._after_change(f"{name} was dissolved: its frames are free genes again.")

    # -----------------------------------------------------------------
    # Filter, counters, enabled state
    # -----------------------------------------------------------------

    def _apply_filter(self, *_args) -> None:
        patterns = compile_name_filter(self.filter_edit.text())
        wanted = self.show_combo.currentData()
        link_mode = self.link_combo.currentData()

        for row in range(self.table.rowCount()):
            name = self.table.item(row, COL_FRAME).text()
            role = self.table.item(row, COL_TYPE).data(ROLE_KEY)
            linked = name in self._group_of

            hidden = (
                (bool(patterns) and not any(p.fullmatch(name) for p in patterns))
                or (wanted is not None and role != wanted)
                or (link_mode == "linked" and not linked)
                or (link_mode == "free" and linked)
            )
            self.table.setRowHidden(row, hidden)

        self._update_summary()

    def _update_summary(self) -> None:
        total = self.table.rowCount()
        groups = len(self._groups)
        linked = len(self._group_of)
        genes = total - linked + groups

        def number(value, color=CYAN) -> str:
            return f"<span style='color:{color}; font-weight:600'>{value}</span>"

        self.summary.setText(
            f"Groups {number(groups)}&nbsp;&nbsp;|&nbsp;&nbsp; Linked frames {number(linked)}"
            f"&nbsp;&nbsp;|&nbsp;&nbsp; Genes of the algorithm {number(total, STEEL)} → {number(genes, DONE_COLOR)}"
        )
        self.gene_bar.set_values(total, genes)

        shown = sum(not self.table.isRowHidden(row) for row in range(total))
        self.shown_label.setText(f"Showing {shown} of {total}")

    def _sync_controls(self) -> None:
        ready = self._loaded and not self._loading and self.table.rowCount() > 0
        selected = self._selected_frames() if ready else []
        in_group = sum(f in self._group_of for f in selected)

        for widget in (self.filter_edit, self.show_combo, self.link_combo):
            widget.setEnabled(ready)

        self.link_button.setText(f"Link selected ({len(selected)})")
        self.link_button.setEnabled(ready and len(selected) >= 2)
        self.unlink_button.setEnabled(ready and in_group > 0)
        self.next_button.setEnabled(ready)

    def _set_status(self, html: str, result: bool = False, warn: bool = False) -> None:
        self.status.setProperty("result", result)
        self.status.setProperty("warn", warn)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(html)

    # -----------------------------------------------------------------
    # Next
    # -----------------------------------------------------------------

    def _on_next(self) -> None:
        if not self._loaded:
            return

        links = self.links
        logger.info("Linked frames accepted: %d groups, %d frames", len(links), sum(len(g) for g in links))
        self.next_requested.emit(links)
