"""Auto Design - step 10 (last page): typing of the final member.

Top: four tiles about the best member (weight, mean DCR, max DCR, change
of weight against the reference file; the tiles are the `StatTile` of the
run page). Below: the table, drawn as one framed group per type, in the
order Column, Beam, Vertical Brace, Horizontal Brace:

    Type | Section (one section per row) | No. (frames) | Number of types

The last column is one input per type (it spans the rows of the group):
how many types (distinct sections) the user wants for that kind of frame.
It accepts whole numbers from 1 up to the number of different sections the
member uses in that group (more types than sections makes no sense); it can
be typed or changed with the arrows / Up / Down keys.

The button "Typify Sections" (bottom centre) can be pressed any number
of times: every press reads the numbers of types from the last column,
standardizes the sections of the member (`services/typify_sections.py`),
shows the result, asks where to save the file and writes it. The final
member is opened in SAP2000 ONCE (first press, together with the reading
of the section areas); after that nothing is ever opened again: the new
sections are assigned to the open model and it is saved with Save As under
the chosen name. The final member's own file and the reference file are
never changed. Later presses assign only the differences from the model
that is open (the previous typified one). If a save fails the state is
unknown, so the next press opens the final member again. The model is NOT
analyzed again.

`typeCounts` gives role -> number of types.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, QThread, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QIntValidator,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.fitness import Fitness, is_feasible
from src.plugins.auto_design.services.ga_run import GAContext
from src.plugins.auto_design.services.section_areas import read_section_areas
from src.plugins.auto_design.services.typify_sections import TypifyOutcome, typify_member
from src.plugins.auto_design.services.population import ROLE_LABELS, Individual
from src.plugins.auto_design.services.typing_summary import (
    TYPING_ORDER,
    sections_by_role,
    weight_change_percent,
)
from src.plugins.auto_design.ui.roles_page import ROLE_COLORS
from src.plugins.auto_design.ui.run_page import GREEN, PAGE_STYLE as RUN_STYLE, StatTile
from src.ui.theme import (
    AMBER,
    BLUE,
    CYAN,
    DANGER,
    FONT_TITLE,
    ICONS_DIR,
    INK_DEEP,
    INK_HI,
    PAPER,
    RULE,
    RULE_HI,
    STEEL,
    STEEL_DIM,
)
from src.ui.widgets import arrow_icon

logger = logging.getLogger(__name__)

# Column stretches shared by the header and every group card, so they line up.
COLUMN_STRETCH = (3, 5, 2, 3)
ROW_HEIGHT = 36
# src/ui/assets/icons/typify.png (icon of the Typify Sections button)
TYPIFY_ICON_PNG = ICONS_DIR / "typify.png"

PAGE_STYLE = f"""
    QLabel#typeHeader {{
        background: transparent;
        color: {STEEL_DIM};
        font-size: 8.5pt;
        font-weight: 700;
    }}
    QPushButton#typifyButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {BLUE}, stop:1 #2A9BD8);
        color: #FFFFFF;
        border: 2px solid {CYAN};
        border-radius: 14px;
        font-family: "{FONT_TITLE}";
        font-size: 15pt;
        font-weight: 700;
        padding: 4px 18px;
    }}
    QPushButton#typifyButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #2A7DC8, stop:1 #46B6EE);
        border-color: {AMBER};
    }}
    QPushButton#typifyButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #185C99, stop:1 #2A9BD8);
        border-color: {AMBER};
    }}
    QPushButton#typifyButton:disabled {{
        background: {INK_HI};
        color: {STEEL_DIM};
        border-color: {RULE};
    }}
    QLabel#typeWarning {{
        background: transparent;
        color: {DANGER};
        font-size: 9.5pt;
    }}
    QPushButton#stepButton {{
        background: {INK_DEEP};
        color: {STEEL};
        border: 1px solid {RULE_HI};
        border-radius: 4px;
        padding: 0;
        font-size: 7pt;
    }}
    QPushButton#stepButton:hover:enabled {{
        background: {INK_HI};
        color: {AMBER};
        border-color: {AMBER};
    }}
    QPushButton#stepButton:disabled {{
        color: {STEEL_DIM};
        border-color: {RULE};
    }}
"""


# ---------------------------------------------------------------------
# Input: number of types
# ---------------------------------------------------------------------


class _CountLineEdit(QLineEdit):
    """Line edit where the Up / Down keys ask for a step."""

    step_requested = Signal(int)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Up:
            self.step_requested.emit(1)
            return

        if event.key() == Qt.Key.Key_Down:
            self.step_requested.emit(-1)
            return

        super().keyPressEvent(event)


class TypeCountEdit(QWidget):
    """Whole number from 1 to `maximum`: text box with up / down arrows."""

    value_changed = Signal(int)

    def __init__(self, maximum: int, parent: QWidget | None = None):
        super().__init__(parent)

        self._maximum = max(1, int(maximum))
        self._value = 1

        self.edit = _CountLineEdit("1")
        self.edit.setValidator(QIntValidator(1, self._maximum, self.edit))
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setFixedSize(72, 34)
        self.edit.setToolTip(f"Number of types: a whole number from 1 to {self._maximum}")
        self.edit.textEdited.connect(self._on_text_edited)
        self.edit.editingFinished.connect(self._restore)
        self.edit.step_requested.connect(self._step)

        self.up_button = self._arrow_button("▲", 1)
        self.down_button = self._arrow_button("▼", -1)

        arrows = QVBoxLayout()
        arrows.setContentsMargins(0, 0, 0, 0)
        arrows.setSpacing(2)
        arrows.addWidget(self.up_button)
        arrows.addWidget(self.down_button)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(self.edit)
        row.addLayout(arrows)

        self._sync_buttons()

    def _arrow_button(self, text: str, delta: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("stepButton")
        button.setFixedSize(24, 16)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoRepeat(True)
        button.clicked.connect(lambda _checked=False, d=delta: self._step(d))

        return button

    def value(self) -> int:
        return self._value

    def maximum(self) -> int:
        return self._maximum

    def set_value(self, value: int) -> None:
        value = max(1, min(self._maximum, int(value)))
        changed = value != self._value

        self._value = value
        self.edit.setText(str(value))
        self._sync_buttons()

        if changed:
            self.value_changed.emit(value)

    def _step(self, delta: int) -> None:
        self.set_value(self._value + delta)

    def _on_text_edited(self, text: str) -> None:
        # The validator already refuses everything but digits; a number that
        # is not in range yet (empty, 0, too big) is fixed when editing ends.
        if text.isdigit() and 1 <= int(text) <= self._maximum:
            value = int(text)

            if value != self._value:
                self._value = value
                self._sync_buttons()
                self.value_changed.emit(value)

    def _restore(self) -> None:
        self.edit.setText(str(self._value))

    def _sync_buttons(self) -> None:
        self.up_button.setEnabled(self._value < self._maximum)
        self.down_button.setEnabled(self._value > 1)


# ---------------------------------------------------------------------
# One group (one type) of the table
# ---------------------------------------------------------------------


def _label(text: str, color: str, bold: bool = False, align=Qt.AlignmentFlag.AlignLeft) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"background: transparent; color: {color};" + (" font-weight: 600;" if bold else "")
    )
    label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    label.setMinimumHeight(ROW_HEIGHT)

    return label


def _grid(parent: QWidget, left: int) -> QGridLayout:
    grid = QGridLayout(parent)
    grid.setContentsMargins(left, 4, 16, 4)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(0)

    for column, stretch in enumerate(COLUMN_STRETCH):
        grid.setColumnStretch(column, stretch)

    return grid


class _GroupCard(QFrame):
    """Framed card of one type: its sections, their numbers and the input."""

    def __init__(self, role: str, rows: list[tuple[str, int]], parent: QWidget | None = None):
        super().__init__(parent)

        color = ROLE_COLORS[role]
        self.role = role
        self.counter: TypeCountEdit | None = None

        self.setObjectName("typeCard")
        self.setStyleSheet(
            f"QFrame#typeCard {{ background: {INK_DEEP}; border: 1px solid {RULE_HI};"
            f" border-left: 4px solid {color}; border-radius: 10px; }}"
        )

        grid = _grid(self, 16)
        frames = sum(count for _section, count in rows)
        span = max(1, 2 * len(rows) - 1)

        title = QLabel(
            f"<span style='color:{color}; font-weight:700; font-size:11pt'>"
            f"● {ROLE_LABELS[role]}</span><br>"
            f"<span style='color:{STEEL_DIM}; font-size:8.5pt'>"
            f"{frames} frame{'s' if frames != 1 else ''} · "
            f"{len(rows)} section{'s' if len(rows) != 1 else ''}</span>"
        )
        title.setStyleSheet("background: transparent;")
        title.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(title, 0, 0, span, 1, Qt.AlignmentFlag.AlignVCenter)

        if not rows:
            grid.addWidget(_label("— not used in the final member", STEEL_DIM), 0, 1, 1, 2)
            grid.addWidget(
                _label("—", STEEL_DIM, align=Qt.AlignmentFlag.AlignCenter),
                0, 3, 1, 1, Qt.AlignmentFlag.AlignCenter,
            )
            return

        for index, (section, count) in enumerate(rows):
            row = 2 * index
            grid.addWidget(_label(section, PAPER), row, 1)
            grid.addWidget(
                _label(str(count), CYAN, True, Qt.AlignmentFlag.AlignHCenter), row, 2
            )

            if index < len(rows) - 1:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background: {RULE};")
                grid.addWidget(line, row + 1, 1, 1, 2)

        self.counter = TypeCountEdit(maximum=len(rows))
        grid.addWidget(self.counter, 0, 3, span, 1, Qt.AlignmentFlag.AlignCenter)


# ---------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------

def _trimmed_pixmap(pixmap: QPixmap) -> QPixmap:
    """The pixmap without its transparent margin, so the icon fills its box."""

    bounds = QRegion(pixmap.mask()).boundingRect()

    if bounds.isEmpty():
        return pixmap

    return pixmap.copy(bounds)

def _i_section_icon(size: int = 44, color: str = "#FFFFFF") -> QIcon:
    """Steel I / H section (wide flanges, thin web), drawn in code."""

    scale = 2  # draw at 2x so it stays sharp on high-DPI screens
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(scale)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    flange_w, flange_t, web_t = 0.80 * s, 0.17 * s, 0.15 * s
    left, top, bottom, cx = (s - flange_w) / 2, 0.08 * s, 0.92 * s, s / 2

    points = [
        (left, top), (left + flange_w, top),
        (left + flange_w, top + flange_t), (cx + web_t / 2, top + flange_t),
        (cx + web_t / 2, bottom - flange_t), (left + flange_w, bottom - flange_t),
        (left + flange_w, bottom), (left, bottom),
        (left, bottom - flange_t), (cx - web_t / 2, bottom - flange_t),
        (cx - web_t / 2, top + flange_t), (left, top + flange_t),
    ]
    path = QPainterPath(QPointF(*points[0]))

    for point in points[1:]:
        path.lineTo(QPointF(*point))

    path.closeSubpath()

    pen = QPen(QColor(color), 1.2)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QColor(color))
    painter.drawPath(path)
    painter.end()

    return QIcon(pixmap)


class _ResultCard(QFrame):
    """The report of one Typify press: a big framed card with the weight
    increase, one small tile per type, and a status line (save, errors)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("resultCard")
        self.setStyleSheet(
            f"QFrame#resultCard {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 {INK_HI}, stop:1 {INK_DEEP}); border: 1.5px solid {CYAN};"
            f" border-radius: 14px; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 16)
        root.setSpacing(12)

        # -- numbers ------------------------------------------------------
        self.stats = QWidget()
        self.stats.setStyleSheet("background: transparent;")
        stats = QHBoxLayout(self.stats)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(0)
        caption = QLabel("FRAME WEIGHT INCREASE")
        caption.setStyleSheet(f"color: {STEEL_DIM}; font-size: 9pt; font-weight: 700;")
        self.big = QLabel("–")
        self.big.setStyleSheet(
            f"color: {AMBER}; font-family: '{FONT_TITLE}'; font-size: 34pt; font-weight: 700;"
        )
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color: {STEEL}; font-size: 10pt;")
        left.addWidget(caption)
        left.addWidget(self.big)
        left.addWidget(self.sub)
        stats.addLayout(left)

        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet(f"background: {RULE_HI};")
        stats.addWidget(divider)

        self.tiles = QHBoxLayout()
        self.tiles.setSpacing(10)
        stats.addLayout(self.tiles, 1)

        root.addWidget(self.stats)

        # -- status line --------------------------------------------------
        self.status = QLabel("")
        self.status.setStyleSheet(f"background: transparent; color: {PAPER}; font-size: 11pt;")
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status)

    def show_message(self, html: str) -> None:
        """Only a message (busy / error): no numbers."""

        self.stats.setVisible(False)
        self.status.setText(html)
        self.setVisible(True)

    def set_status(self, html: str) -> None:
        self.status.setText(html)
        self.setVisible(True)

    def show_outcome(self, outcome: TypifyOutcome, status_html: str) -> None:
        self.big.setText(f"{outcome.increasePercent:+.2f} %")
        self.sub.setText(f"{outcome.changedFrames} frame(s) changed")

        while self.tiles.count():
            item = self.tiles.takeAt(0)

            if item.widget() is not None:
                item.widget().deleteLater()

        for role in TYPING_ORDER:
            result = outcome.byRole.get(role)

            if result is not None:
                self.tiles.addWidget(self._role_tile(role, result), 1)

        self.stats.setVisible(True)
        self.status.setText(status_html)
        self.setVisible(True)

    @staticmethod
    def _role_tile(role: str, result: dict) -> QFrame:
        color = ROLE_COLORS[role]
        tile = QFrame()
        tile.setStyleSheet(
            f"QFrame {{ background: {INK_DEEP}; border: 1px solid {RULE_HI};"
            f" border-left: 4px solid {color}; border-radius: 9px; }}"
            " QLabel { background: transparent; border: none; }"
        )

        box = QVBoxLayout(tile)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(1)

        name = QLabel(ROLE_LABELS[role])
        name.setStyleSheet(f"color: {color}; font-size: 10pt; font-weight: 700;")
        types = len(result["groups"])
        count = QLabel(f"{types} type{'s' if types != 1 else ''}")
        count.setStyleSheet(f"color: {STEEL}; font-size: 9.5pt;")
        percent = QLabel(f"{result['increase_percent']:+.2f} %")
        percent.setStyleSheet(
            f"color: {PAPER}; font-family: '{FONT_TITLE}'; font-size: 15pt; font-weight: 700;"
        )

        for label in (name, count, percent):
            box.addWidget(label)

        return tile


class _AreaLoader(QThread):
    """Opens the final member and reads the area of every section (off the UI thread)."""

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, client: SapClient, path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._client = client
        self._path = path

    def run(self) -> None:
        try:
            self._client.open_model(self._path)
            areas = read_section_areas(self._client)
        except Exception as exc:
            logger.exception("Could not read the section areas")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.loaded.emit(areas)


class _ModelWriter(QThread):
    """Writes the standardized model. The final member is ALREADY open in
    SAP2000 (opened once by `_AreaLoader`), so nothing is opened here: the
    new sections are assigned to the open model and it is saved under a new
    name (Save As). The final member's own file is never touched."""

    done = Signal()
    failed = Signal(str)

    def __init__(
        self,
        client: SapClient,
        target: str,
        changes: dict[str, str],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._client = client
        self._target = target
        self._changes = changes

    def run(self) -> None:
        try:
            self._client.unlock_model()

            for frame, section in self._changes.items():
                self._client.assign_frame_section(frame, section)

            self._client.save_model_as(self._target)
        except Exception as exc:
            logger.exception("Could not write the standardized model")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.done.emit()


class TypingPage(QWidget):
    """Typing of the final member (see the module docstring)."""

    back_requested = Signal()

    # Text of the button (one place, in case a better word is found).
    BUTTON_TEXT = "Typify Sections"

    def __init__(self, ctx: GAContext, best: Individual, parent: QWidget | None = None):
        super().__init__(parent)

        reference = ctx.referenceFitness
        frameRoles = ctx.frameRoles

        self.best = best
        self._ctx = ctx
        self._cards: dict[str, _GroupCard] = {}
        self._areas: dict[str, float] | None = None  # read once, on the first press
        # Genes of the model that is open in SAP2000 right now (None = unknown:
        # the final member must be opened again before the next typify).
        self._model_genes: dict[str, str] | None = None
        self._worker: QThread | None = None
        self._materials = {s.name: s.materialType for s in ctx.sections}
        self._lengths = self._frame_lengths(ctx)

        self.setObjectName("page")
        self.setStyleSheet(RUN_STYLE + PAGE_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(34, 28, 34, 12)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            f"Typing of the final member {best.name}: choose how many types you want "
            "for every kind of frame."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(16)

        layout.addLayout(self._build_tiles(best, reference))

        fitness = best.fitness

        if isinstance(fitness, Fitness) and not is_feasible(fitness):
            warning = QLabel(
                "This member still violates the constraints "
                f"(CV = {fitness.cv:.4g}); its maximum DCR is above 1.0."
            )
            warning.setObjectName("typeWarning")
            warning.setWordWrap(True)
            layout.addSpacing(10)
            layout.addWidget(warning)

        layout.addSpacing(16)
        layout.addWidget(self._build_header())
        layout.addSpacing(6)

        groups = sections_by_role(best.genes, frameRoles)

        for role in TYPING_ORDER:
            card = _GroupCard(role, groups[role])
            self._cards[role] = card
            layout.addWidget(card)
            layout.addSpacing(10)

        layout.addSpacing(6)

        self._has_outcome = False
        self.result_card = _ResultCard()
        self.result_card.setVisible(False)
        layout.addWidget(self.result_card)

        layout.addStretch(1)

        self.back_button = QPushButton("Back")
        self.back_button.setIcon(arrow_icon("left", color=PAPER))
        self.back_button.setIconSize(QSize(32, 24))
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setMinimumSize(110, 42)
        self.back_button.clicked.connect(self.back_requested.emit)

        self.typify_button = QPushButton("  " + self.BUTTON_TEXT)
        self.typify_button.setObjectName("typifyButton")
        typify_pixmap = QPixmap(str(TYPIFY_ICON_PNG))
        if typify_pixmap.isNull():
            # icon file missing: use the icon drawn in code
            self.typify_button.setIcon(_i_section_icon(44))
            self.typify_button.setIconSize(QSize(44, 44))
        else:
            self.typify_button.setIcon(QIcon(_trimmed_pixmap(typify_pixmap)))
            self.typify_button.setIconSize(QSize(48, 48))
        self.typify_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.typify_button.setMinimumSize(290, 68)
        self.typify_button.setDefault(True)

        glow = QGraphicsDropShadowEffect(self.typify_button)
        glow.setBlurRadius(30)
        glow.setOffset(0, 0)
        glow.setColor(QColor(CYAN).darker(120))
        self.typify_button.setGraphicsEffect(glow)
        self.typify_button.setToolTip(
            "Replace the sections of every type by the chosen number of types "
            "(least weight increase) and save the new SAP2000 file"
        )
        self.typify_button.clicked.connect(self._on_typify)

        footer = QHBoxLayout()
        footer.setContentsMargins(34, 8, 34, 20)
        footer.addWidget(self.back_button)
        footer.addStretch(1)
        footer.addWidget(self.typify_button)
        footer.addStretch(1)
        footer.addSpacing(self.back_button.minimumWidth())  # keeps the button centered
        outer.addLayout(footer)

    # -- standardizing ----------------------------------------------------

    @staticmethod
    def _frame_lengths(ctx: GAContext) -> dict[str, float]:
        """Frame -> length (m) from the joint coordinates (frames without
        geometry are left out; `typify_member` reports them)."""

        lengths: dict[str, float] = {}

        for frame, (joint_i, joint_j) in ctx.frameConnectivity.items():
            if joint_i in ctx.jointCoordinates and joint_j in ctx.jointCoordinates:
                lengths[frame] = math.dist(
                    ctx.jointCoordinates[joint_i], ctx.jointCoordinates[joint_j]
                )

        return lengths

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.typify_button.setEnabled(not busy)
        self.back_button.setEnabled(not busy)

        for card in self._cards.values():
            card.setEnabled(not busy)

        if busy:
            html = f"<span style='color:{STEEL}'>{text}</span>"

            if self._has_outcome:
                self.result_card.set_status(html)
            else:
                self.result_card.show_message(html)

    def _show_error(self, text: str) -> None:
        html = f"<span style='color:{DANGER}; font-weight:600'>{text}</span>"

        if self._has_outcome:
            self.result_card.set_status(html)
        else:
            self.result_card.show_message(html)

    def _on_typify(self) -> None:
        if self._worker is not None:
            return

        if self._areas is None or self._model_genes is None:
            # First press (or after a failed save): open the final member once.
            self._set_busy(True, "Opening the final member in SAP2000…")
            worker = _AreaLoader(self._ctx.sap, str(self.best.path), self)
            worker.loaded.connect(self._on_areas_loaded)
            worker.failed.connect(self._on_worker_failed)
            worker.finished.connect(self._worker_finished)
            self._worker = worker
            worker.start()
            return

        self._run_typify()

    def _on_areas_loaded(self, areas: dict) -> None:
        self._areas = dict(areas)
        self._model_genes = dict(self.best.genes)  # the open model is the final member
        self._worker = None
        self._set_busy(False)
        self._run_typify()

    def _run_typify(self) -> None:
        counts = self.typeCounts

        try:
            outcome = typify_member(
                self.best.genes,
                self._ctx.frameRoles,
                counts,
                self._areas or {},
                self._materials,
                self._lengths,
            )
        except ValueError as exc:
            self._has_outcome = False
            self._show_error(str(exc))
            return

        logger.info(
            "Step 10 - typified %s with %s: +%.3f %% frame weight, %d frames changed",
            self.best.name, counts, outcome.increasePercent, outcome.changedFrames,
        )

        self._has_outcome = True
        self.result_card.show_outcome(outcome, f"<span style='color:{STEEL}'>Choose where to save the new file…</span>")

        target = self._ask_target()

        if not target:
            self.result_card.set_status(
                f"<span style='color:{AMBER}'>Not saved: no file was chosen. "
                "Press the button again to save.</span>"
            )
            return

        # Only the differences from the model that is open now (the final
        # member the first time; the previous typified model on later presses).
        current = self._model_genes or self.best.genes
        changes = {
            frame: section
            for frame, section in outcome.genes.items()
            if section != current[frame]
        }
        new_genes = dict(outcome.genes)

        self._set_busy(True, "Saving the typified SAP2000 file…")
        worker = _ModelWriter(self._ctx.sap, target, changes, self)
        worker.done.connect(lambda: self._on_saved(target, new_genes))
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        worker.start()

    def _ask_target(self) -> str:
        """File dialog; the reference file and the final member are protected."""

        reference = Path(self._ctx.sapPath)
        start = reference.with_name(f"{reference.stem}_Typified.sdb")
        forbidden = {reference.resolve(), Path(self.best.path).resolve()}

        while True:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save the standardized SAP2000 file",
                str(start),
                "SAP2000 files (*.sdb)",
            )

            if not path:
                return ""

            if not path.lower().endswith(".sdb"):
                path += ".sdb"

            path = str(Path(path))  # D:/x.sdb -> D:\x.sdb (SAP2000 needs backslashes)

            if Path(path).resolve() in forbidden:
                QMessageBox.warning(
                    self,
                    "Save file",
                    "The reference file and the final member cannot be overwritten. "
                    "Choose another file name.",
                )
                start = Path(path).with_name(f"{Path(path).stem}_Typified.sdb")
                continue

            return path

    def _on_saved(self, target: str, new_genes: dict[str, str]) -> None:
        self._model_genes = new_genes  # SAP2000 now holds the typified file
        self._worker = None
        self._set_busy(False)
        self.result_card.set_status(
            f"<span style='color:{GREEN}; font-weight:700'>✓ Saved:</span> {target}"
            f"<br><span style='color:{STEEL_DIM}; font-size:9.5pt'>The model has not been "
            "analyzed again: run the analysis and design in SAP2000 to see the new ratios.</span>"
        )

    def _on_worker_failed(self, error: str) -> None:
        self._model_genes = None  # unknown state: reopen the final member next time
        self._worker = None
        self._set_busy(False)
        self._show_error(f"Failed: {error}")

    def _worker_finished(self) -> None:
        worker = self.sender()

        if worker is not None:
            worker.deleteLater()

    # -- building ---------------------------------------------------------

    def _build_tiles(self, best: Individual, reference: Fitness | None) -> QHBoxLayout:
        tiles = QHBoxLayout()
        tiles.setSpacing(12)

        weight = StatTile("Weight")
        mean_dcr = StatTile("Mean DCR")
        max_dcr = StatTile("Max DCR")
        change = StatTile("Weight vs reference")

        fitness = best.fitness

        if isinstance(fitness, Fitness):
            weight.set_value(f"{fitness.weight:,.1f}", "kg")
            mean_dcr.set_value(f"{fitness.meanRatio:.3f}", f"{fitness.elementCount} elements")
            max_dcr.set_value(
                f"{fitness.maxRatio:.3f}",
                "limit 1.0",
                GREEN if fitness.maxRatio <= 1.0 else DANGER,
            )

            percent = (
                weight_change_percent(fitness.weight, reference.weight)
                if isinstance(reference, Fitness)
                else None
            )

            if percent is None:
                change.set_value("–", "no reference weight")
            else:
                color = GREEN if percent < -1e-9 else (DANGER if percent > 1e-9 else None)
                change.set_value(
                    f"{percent:+.2f} %", f"reference {reference.weight:,.1f} kg", color
                )
        else:
            for tile in (weight, mean_dcr, max_dcr, change):
                tile.set_value("–")

        for tile in (weight, mean_dcr, max_dcr, change):
            tiles.addWidget(tile, 1)

        return tiles

    @staticmethod
    def _build_header() -> QWidget:
        header = QWidget()
        grid = _grid(header, 20)

        for column, (text, align) in enumerate(
            (
                ("TYPE", Qt.AlignmentFlag.AlignLeft),
                ("SECTION", Qt.AlignmentFlag.AlignLeft),
                ("NO. OF FRAMES", Qt.AlignmentFlag.AlignHCenter),
                ("NUMBER OF TYPES", Qt.AlignmentFlag.AlignHCenter),
            )
        ):
            label = QLabel(text)
            label.setObjectName("typeHeader")
            label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(label, 0, column)

        return header

    # -- result -----------------------------------------------------------

    @property
    def typeCounts(self) -> dict[str, int]:
        """role -> number of types wanted by the user (0 when the role is
        not used in the final member)."""

        return {
            role: (card.counter.value() if card.counter is not None else 0)
            for role, card in self._cards.items()
        }
