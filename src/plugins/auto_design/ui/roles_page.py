"""Auto Design - step 3: type of every frame (Column, Beam, Horizontal / Vertical Brace).

The types are decided ONCE, here, for the reference model, and the whole
run uses them (the GA never classifies again). The page:

* connects to the model (the live SAP2000 connection of step 2): in a
  worker thread it opens the reference file and reads the section of
  every frame, the frame connectivity and the joint coordinates,
* classifies every frame with `classify_frames` (rule in
  `services/population.py`) using the tolerance typed on this page (cm),
* shows the result in a table: Frame, the coordinate differences between
  its two joints (to check the result by eye) and the Type. The Type is
  a combo box: click it to change the type of that frame. Changed
  frames are marked "edited",
* "Classify" applies a new tolerance (it asks first when the user has
  already changed some types by hand, because those changes are lost).

Next emits the dictionary frame -> role (the table content).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import (
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from src.plugins.auto_design.services.population import (
    ROLE_LABELS,
    ROLES,
    classify_frames,
)
from src.plugins.auto_design.ui.fields import FORM_STYLE, Field, parse_float
from src.plugins.auto_design.ui.sections_page import compile_name_filter
from src.ui.theme import (
    AMBER,
    CYAN,
    DANGER,
    INK_DEEP,
    INK_HI,
    INK_RAISED,
    PAPER,
    RULE,
    RULE_HI,
    STEEL,
    STEEL_DIM,
)
from src.ui.widgets import arrow_icon

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE_CM = "1"

ROLE_COLORS = {
    "column": CYAN,
    "beam": "#3DDC97",
    "horizontalBrace": "#B48CFF",
    "verticalBrace": "#FF8F6B",
}

DONE_COLOR = "#3DDC97"  # green: the blink and the "Done" button after Classify

HEADERS = ["Frame", "ΔX (m)", "ΔY (m)", "ΔZ (m)", "Type"]
TYPE_COLUMN = 4

# Starting column widths (px). The Delta columns are fixed at DELTA_WIDTH,
# Type is trimmed down to MIN_TYPE_WIDTH when the window is small so that
# Frame (which gets all the rest) stays readable; the user can drag any
# column border, after which the automatic widths are no longer applied.
DELTA_WIDTH = 90
PREFERRED_TYPE_WIDTH = 250
MIN_TYPE_WIDTH = 205
MIN_FRAME_WIDTH = 170
ROLE_DATA = Qt.ItemDataRole.UserRole  # the role chosen now
AUTO_ROLE = Qt.ItemDataRole.UserRole + 1  # the role found by the program

PAGE_STYLE = f"""
    QFrame#tableCard {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-radius: 12px;
    }}
    QTableWidget#rolesTable {{
        background: transparent;
        border: none;
        outline: none;
        color: {PAPER};
    }}
    QTableWidget#rolesTable::item {{
        padding: 0 12px;
        border-bottom: 1px solid {RULE};
    }}
    QTableWidget#rolesTable::item:hover {{
        background: {INK_HI};
    }}
    QTableWidget#rolesTable::item:selected {{
        background: {INK_HI};
        color: {PAPER};
    }}
    QTableWidget#rolesTable QHeaderView::section {{
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
    QPushButton[done="true"] {{
        color: {DONE_COLOR};
        border: 1px solid {DONE_COLOR};
    }}
    QLabel#toolLabel {{
        font-weight: 600;
    }}
    QLabel#statusError {{
        background: transparent;
        color: {DANGER};
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
"""


# ---------------------------------------------------------------------
# Table card that blinks, table that reports its width
# ---------------------------------------------------------------------


class _FlashFrame(QFrame):
    """The card around the table. `flash()` makes it blink green twice:
    the answer to "did the calculation finish?" after Classify."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._level = 0.0

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(1100)
        self._animation.setStartValue(0.0)
        self._animation.setKeyValueAt(0.18, 1.0)
        self._animation.setKeyValueAt(0.42, 0.15)
        self._animation.setKeyValueAt(0.62, 1.0)
        self._animation.setEndValue(0.0)
        self._animation.valueChanged.connect(self._set_level)

    def flash(self) -> None:
        self._animation.stop()
        self._animation.start()

    def _set_level(self, value) -> None:
        self._level = float(value)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._level <= 0.001:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill = QColor(DONE_COLOR)
        fill.setAlphaF(0.16 * self._level)
        edge = QColor(DONE_COLOR)
        edge.setAlphaF(self._level)

        painter.setBrush(fill)
        painter.setPen(QPen(edge, 2.0))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)


class _Table(QTableWidget):
    """Table that reports when its visible area changes size."""

    viewport_resized = Signal()

    def viewportEvent(self, event):
        result = super().viewportEvent(event)

        if event.type() == QEvent.Type.Resize:
            self.viewport_resized.emit()

        return result


# ---------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------


class _GeometryLoader(QThread):
    """Opens the reference model and reads what the classification needs
    (off the UI thread)."""

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
            logger.exception("Could not read the frame geometry from SAP2000")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.loaded.emit(frame_sections, connectivity, coordinates)


# ---------------------------------------------------------------------
# Type column: painted chip + combo box editor
# ---------------------------------------------------------------------


def _show_popup(combo: QComboBox) -> None:
    try:
        if combo.isVisible():
            combo.showPopup()
    except RuntimeError:  # the editor was already closed
        pass


class _RoleDelegate(QStyledItemDelegate):
    """Type cells: a colored dot, the type name, "edited" when the user
    changed it, and a small arrow that says "click to change"."""

    def paint(self, painter, option, index):
        if index.column() != TYPE_COLUMN:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""

        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        role = index.data(ROLE_DATA)
        auto = index.data(AUTO_ROLE)
        rect = QRectF(opt.rect)
        cy = rect.center().y()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ROLE_COLORS.get(role, STEEL)))
        painter.drawEllipse(QPointF(rect.left() + 18, cy), 4.5, 4.5)

        font = QFont(opt.font)
        edited = role != auto
        tag_width = 46.0 if edited else 0.0
        # dot (32 px) on the left, arrow (30 px) and the "edited" tag on the right
        label_width = max(rect.width() - 32 - 30 - tag_width, 20.0)
        label = QFontMetrics(font).elidedText(
            ROLE_LABELS.get(role, ""), Qt.TextElideMode.ElideRight, int(label_width)
        )

        painter.setFont(font)
        painter.setPen(QColor(PAPER))
        painter.drawText(
            QRectF(rect.left() + 32, rect.top(), label_width, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )

        if edited:
            small = QFont(font)
            small.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
            small.setBold(True)
            painter.setFont(small)
            painter.setPen(QColor(AMBER))
            painter.drawText(
                QRectF(rect.right() - 30 - tag_width, rect.top(), tag_width, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                "edited",
            )

        arrow = QPen(QColor(STEEL_DIM), 1.6)
        arrow.setCapStyle(Qt.PenCapStyle.RoundCap)
        arrow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(arrow)
        ax = rect.right() - 16
        painter.drawPolyline(
            [QPointF(ax - 4, cy - 2), QPointF(ax, cy + 2), QPointF(ax + 4, cy - 2)]
        )
        painter.restore()

    def createEditor(self, parent, option, index):
        if index.column() != TYPE_COLUMN:
            return None

        combo = QComboBox(parent)

        for role in ROLES:
            combo.addItem(ROLE_LABELS[role], role)

        def finish(_position: int = 0, editor: QComboBox = combo) -> None:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)

        combo.activated.connect(finish)
        QTimer.singleShot(0, lambda c=combo: _show_popup(c))

        return combo

    def setEditorData(self, editor, index):
        position = editor.findData(index.data(ROLE_DATA))
        editor.setCurrentIndex(max(0, position))

    def setModelData(self, editor, model, index):
        role = editor.currentData()

        if role is None:
            return

        model.setData(index, role, ROLE_DATA)
        model.setData(index, ROLE_LABELS[role], Qt.ItemDataRole.DisplayRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


# ---------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------


class FrameRolesPage(QWidget):
    """Frame types table (see the module docstring)."""

    back_requested = Signal()
    next_requested = Signal(object)  # dict: frame -> role

    def __init__(self, sap_path: str, client: SapClient, parent: QWidget | None = None):
        super().__init__(parent)

        self.sap_path = sap_path
        self.client = client

        self._loader: _GeometryLoader | None = None
        self._loading = False
        self._filling = False
        self._tolerance_dirty = False  # the text was changed but not applied
        self._auto_sizing = False  # True while the code itself resizes columns
        self._user_sized = False  # True once the user dragged a column border

        self._frame_sections: dict[str, str] = {}
        self._connectivity: dict[str, tuple[str, str]] = {}
        self._coordinates: dict[str, tuple[float, float, float]] = {}

        self.setObjectName("page")
        self.setStyleSheet(FORM_STYLE + PAGE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Check and edit the type of every frame (column, beam, horizontal brace or vertical brace)"
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
        self.status.setProperty("result", False)  # True: the bright result line
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

        # Tolerance + Classify
        self.tolerance = Field(
            "Tolerance to Detect Member as Beam or Column (cm)", "Positive number"
        )
        self.tolerance.edit.setText(DEFAULT_TOLERANCE_CM)
        self.tolerance.edit.setMaximumWidth(260)
        self.tolerance.edit.textEdited.connect(self._on_tolerance_edited)
        self.tolerance.edit.returnPressed.connect(self._on_classify)

        self.classify_button = QPushButton("Classify")
        self.classify_button.setToolTip(
            "Classify all frames again with this tolerance "
            "(types changed by hand are lost)"
        )
        self.classify_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.classify_button.setMinimumHeight(self.tolerance.edit.sizeHint().height())
        self.classify_button.setMinimumWidth(110)  # room for "✓  Done" without moving the row
        self.classify_button.setProperty("done", False)
        self.classify_button.clicked.connect(self._on_classify)
        self.tolerance.add_side_widget(self.classify_button)

        tolerance_row = QHBoxLayout()
        tolerance_row.addWidget(self.tolerance)
        tolerance_row.addStretch(1)
        layout.addLayout(tolerance_row)

        # Filters: name and type
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by frame name:   1*    *5    10, 25*")
        self.filter_edit.setToolTip(
            "Plain text matches anywhere in the name.\n"
            "* = any characters, ? = one character.\n"
            "Use a comma to list several patterns."
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumHeight(34)
        self.filter_edit.textChanged.connect(self._apply_filter)

        show_label = QLabel("Show:")
        show_label.setObjectName("toolLabel")

        self.show_combo = QComboBox()
        self.show_combo.setMinimumHeight(34)
        self.show_combo.setMinimumWidth(170)
        self.show_combo.addItem("All types", None)

        for role in ROLES:
            self.show_combo.addItem(ROLE_LABELS[role], role)

        self.show_combo.currentIndexChanged.connect(self._apply_filter)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(self.filter_edit, 1)
        filter_row.addWidget(show_label)
        filter_row.addWidget(self.show_combo)
        layout.addLayout(filter_row)
        layout.addSpacing(10)

        # Table
        card = _FlashFrame()
        card.setObjectName("tableCard")
        self.card = card
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)

        self.table = _Table(0, len(HEADERS))
        self.table.setObjectName("rolesTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setItemDelegate(_RoleDelegate(self.table))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.CurrentChanged
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Every column can be dragged by the user; the starting widths come
        # from _auto_layout_columns (Frame = all the free width).
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setFixedHeight(40)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)
        header.sectionResized.connect(self._on_section_resized)

        for column in (1, 2, 3):
            self.table.horizontalHeaderItem(column).setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

        self.table.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.viewport_resized.connect(self._auto_layout_columns)

        self.table.itemChanged.connect(self._on_item_changed)

        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)
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

        self._set_loading(False)

    # -----------------------------------------------------------------
    # Result
    # -----------------------------------------------------------------

    @property
    def roles(self) -> dict[str, str]:
        """frame -> role, as shown in the table (all rows, shown or hidden)."""

        return {
            self.table.item(row, 0).text(): self.table.item(row, TYPE_COLUMN).data(ROLE_DATA)
            for row in range(self.table.rowCount())
        }

    def _edited_count(self) -> int:
        return sum(
            1
            for row in range(self.table.rowCount())
            if self.table.item(row, TYPE_COLUMN).data(ROLE_DATA)
            != self.table.item(row, TYPE_COLUMN).data(AUTO_ROLE)
        )

    # -----------------------------------------------------------------
    # Loading
    # -----------------------------------------------------------------

    def start_loading(self) -> None:
        """Open the reference model and read the geometry, then classify."""

        if self._loader is not None and self._loader.isRunning():
            return

        self._set_loading(True)

        self._loader = _GeometryLoader(self.client, self.sap_path, self)
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
            self._set_status("Reading the frames and joints of the model…")

        self._sync_controls()

    def _on_loaded(self, frame_sections, connectivity, coordinates) -> None:
        self._frame_sections = dict(frame_sections)
        self._connectivity = dict(connectivity)
        self._coordinates = dict(coordinates)
        self._set_loading(False)

        self._classify_and_fill()

    def _on_failed(self, error: str) -> None:
        self._fill_table({})
        self._set_loading(False)
        self._set_status("")
        self.message.setText(f"Could not read the model from SAP2000: {error}")
        self.message.setVisible(True)
        self.retry_button.setVisible(True)

    # -----------------------------------------------------------------
    # Classification
    # -----------------------------------------------------------------

    def _classify_and_fill(self, announce: bool = False) -> bool:
        """Classify with the tolerance on the page and fill the table.
        Returns False (with a message) when that is not possible.
        With `announce` the table blinks and the button says "Done"."""

        tolerance = parse_float(self.tolerance)

        if tolerance is None:
            return False

        try:
            roles = classify_frames(
                self._frame_sections, self._connectivity, self._coordinates, tolerance
            )
        except ValueError as exc:
            self._fill_table({})
            self._set_status("")
            self.message.setText(f"{exc}\nChange the tolerance and press Classify.")
            self.message.setVisible(True)
            return False

        self._tolerance_dirty = False
        self.message.setVisible(False)
        self._fill_table(roles)

        if announce:
            self._announce_done()

        counts = ", ".join(
            f"{sum(r == role for r in roles.values())} {ROLE_LABELS[role].lower()}"
            for role in ROLES
        )
        # The result line has its own bright color; the two numbers are bold
        # and amber so they stand out from the sentence.
        number = "<span style='color:{}; font-weight:700'>{}</span>"
        self._set_status(
            f"{number.format(AMBER, len(roles))} frames classified with a tolerance of "
            f"{number.format(AMBER, format(tolerance, 'g'))} cm.",
            result=True,
        )
        logger.info("Frame types: %d frames, %s (tolerance %.3g cm)", len(roles), counts, tolerance)

        return True

    def _on_tolerance_edited(self, _text: str) -> None:
        self._tolerance_dirty = True
        self._sync_controls()

    def _on_classify(self) -> None:
        if self._loading or not self._frame_sections:
            return

        edited = self._edited_count()

        if edited:
            answer = QMessageBox.question(
                self,
                "Classify again",
                f"You changed the type of {edited} frame(s) by hand.\n\n"
                "Classifying again replaces all types with the automatic result "
                "and those changes are lost. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

        self._classify_and_fill(announce=True)

    def _announce_done(self) -> None:
        """Make it obvious that the calculation finished: the table card
        blinks green twice, the list jumps to the top and the button shows
        a green "Done" for a moment."""

        self.table.scrollToTop()
        self.card.flash()

        self.classify_button.setText("✓  Done")
        self._set_button_done(True)
        QTimer.singleShot(1600, self._reset_classify_button)

    def _reset_classify_button(self) -> None:
        self.classify_button.setText("Classify")
        self._set_button_done(False)

    def _set_button_done(self, done: bool) -> None:
        button = self.classify_button
        button.setProperty("done", done)
        button.style().unpolish(button)
        button.style().polish(button)

    def _set_status(self, text: str, result: bool = False) -> None:
        """Status line. `result=True` gives the bright result style
        (see PAGE_STYLE, `QLabel#statusText[result="true"]`)."""

        self.status.setProperty("result", result)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(text)

    # -----------------------------------------------------------------
    # Column widths
    # -----------------------------------------------------------------

    def _on_section_resized(self, *_args) -> None:
        """A drag of a column border by the user switches the automatic
        widths off (the left mouse button is down only during a drag)."""

        if self._auto_sizing:
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self._user_sized = True

    def _auto_layout_columns(self) -> None:
        """Delta columns fixed, Type as wide as it can be without starving
        Frame, Frame takes all the rest (never below MIN_FRAME_WIDTH: a
        horizontal scroll bar appears instead)."""

        if self._user_sized or self._auto_sizing:
            return

        available = self.table.viewport().width()

        if available <= 0:
            return

        deltas = 3 * DELTA_WIDTH
        type_width = PREFERRED_TYPE_WIDTH
        frame_width = available - deltas - type_width

        if frame_width < MIN_FRAME_WIDTH:
            # small window: take the missing width from Type first
            type_width = max(MIN_TYPE_WIDTH, type_width - (MIN_FRAME_WIDTH - frame_width))
            frame_width = max(available - deltas - type_width, MIN_FRAME_WIDTH)

        header = self.table.horizontalHeader()
        self._auto_sizing = True

        try:
            header.resizeSection(0, frame_width)

            for column in (1, 2, 3):
                header.resizeSection(column, DELTA_WIDTH)

            header.resizeSection(TYPE_COLUMN, type_width)
        finally:
            self._auto_sizing = False

    # -----------------------------------------------------------------
    # Table
    # -----------------------------------------------------------------

    def _fill_table(self, roles: dict[str, str]) -> None:
        self._filling = True
        self.table.blockSignals(True)

        self.table.setRowCount(len(roles))

        for row, (frame, role) in enumerate(roles.items()):
            self.table.setRowHidden(row, False)

            name_item = QTableWidgetItem(frame)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 0, name_item)

            joint_i, joint_j = self._connectivity[frame]
            xi, yi, zi = self._coordinates[joint_i]
            xj, yj, zj = self._coordinates[joint_j]

            for column, delta in enumerate((abs(xi - xj), abs(yi - yj), abs(zi - zj)), start=1):
                item = QTableWidgetItem(f"{delta:.3f}")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

            type_item = QTableWidgetItem(ROLE_LABELS[role])
            type_item.setData(ROLE_DATA, role)
            type_item.setData(AUTO_ROLE, role)
            type_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(row, TYPE_COLUMN, type_item)

        self.table.blockSignals(False)
        self._filling = False

        self._apply_filter()
        self._update_summary()
        self._sync_controls()
        self._auto_layout_columns()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != TYPE_COLUMN:
            return

        self.message.setVisible(False)
        self._update_summary()
        self.table.viewport().update()

    # -----------------------------------------------------------------
    # Filter, counters, enabled state
    # -----------------------------------------------------------------

    def _apply_filter(self, *_args) -> None:
        patterns = compile_name_filter(self.filter_edit.text())
        wanted = self.show_combo.currentData()

        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text()
            role = self.table.item(row, TYPE_COLUMN).data(ROLE_DATA)

            hidden = (
                bool(patterns) and not any(p.fullmatch(name) for p in patterns)
            ) or (wanted is not None and role != wanted)

            self.table.setRowHidden(row, hidden)

        self._update_summary()

    def _update_summary(self) -> None:
        total = self.table.rowCount()
        roles = [self.table.item(row, TYPE_COLUMN).data(ROLE_DATA) for row in range(total)]

        parts = [
            f"{ROLE_LABELS[role]} "
            f"<span style='color:{ROLE_COLORS[role]}; font-weight:600'>{roles.count(role)}</span>"
            for role in ROLES
        ]
        text = "Frames:&nbsp;&nbsp; " + "&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts)
        edited = self._edited_count() if total else 0

        if edited:
            text += (
                f"&nbsp;&nbsp;|&nbsp;&nbsp; Edited by you "
                f"<span style='color:{AMBER}; font-weight:600'>{edited}</span>"
            )

        shown = sum(not self.table.isRowHidden(row) for row in range(total))

        self.summary.setText(text)
        self.shown_label.setText(f"Showing {shown} of {total}")

    def _sync_controls(self) -> None:
        ready = not self._loading and self.table.rowCount() > 0
        loaded = not self._loading and bool(self._frame_sections)

        self.filter_edit.setEnabled(ready)
        self.show_combo.setEnabled(ready)
        self.tolerance.setEnabled(loaded)
        self.classify_button.setEnabled(loaded)
        self.next_button.setEnabled(ready)

    # -----------------------------------------------------------------
    # Next
    # -----------------------------------------------------------------

    def _on_next(self) -> None:
        if self.table.rowCount() == 0:
            return

        if self._tolerance_dirty:
            self.message.setText(
                "The tolerance was changed but not applied. Press Classify first "
                "(or set it back to the value used for this table)."
            )
            self.message.setVisible(True)
            return

        self.next_requested.emit(self.roles)
