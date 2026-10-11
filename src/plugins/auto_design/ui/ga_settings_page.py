"""Auto Design - step 3: genetic-algorithm settings.

Collects the GA parameters (they used to be on the first page). Values
are validated when the user presses Next; on success the page emits
`next_requested` with an `AutoDesignParams`. Back returns to step 2.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.plugins.auto_design.params import AutoDesignParams
from src.plugins.auto_design.ui.fields import FORM_STYLE, Field, parse_float, parse_int
from src.ui.theme import PAPER
from src.ui.widgets import arrow_icon


class GASettingsPage(QWidget):
    """Parameter form of the genetic algorithm."""

    back_requested = Signal()
    next_requested = Signal(object)  # AutoDesignParams

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")
        self.setStyleSheet(FORM_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Genetic algorithm settings.")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(20)

        # -------------------------------------------------------------
        # Form card
        # -------------------------------------------------------------

        card = QFrame()
        card.setObjectName("formCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 22)
        card_layout.setSpacing(16)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.popSize = Field("Population Size", "Positive integer")
        self.tournamentSize = Field("Tournament Size", "Positive integer")
        self.genSize = Field("Number of Generations", "Positive integer")
        self.mutationPercent = Field("Mutation Percent (%)", "0 to 100")
        self.penalizeLevel = Field("Penalize Level Coefficient", "Positive number")
        self.tolerance = Field(
            "Tolerance to Detect Member as Beam or Column (cm)", "Positive number"
        )

        # Default values
        self.popSize.edit.setText("100")
        self.tournamentSize.edit.setText("4")
        self.genSize.edit.setText("10")
        self.mutationPercent.edit.setText("0")
        self.penalizeLevel.edit.setText("1")
        self.tolerance.edit.setText("1")

        grid.addWidget(self.popSize, 0, 0)
        grid.addWidget(self.tournamentSize, 0, 1)
        grid.addWidget(self.genSize, 1, 0)
        grid.addWidget(self.mutationPercent, 1, 1)
        grid.addWidget(self.penalizeLevel, 2, 0)
        grid.addWidget(self.tolerance, 2, 1)

        card_layout.addLayout(grid)

        layout.addWidget(card)
        layout.addSpacing(18)

        # -------------------------------------------------------------
        # Footer
        # -------------------------------------------------------------

        self.back_button = QPushButton("Back")
        self.back_button.setIcon(arrow_icon("left", color=PAPER))
        self.back_button.setIconSize(QSize(32, 24))
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setMinimumSize(110, 42)
        self.back_button.clicked.connect(self.back_requested.emit)

        self.next_button = QPushButton("Next")
        self.next_button.setIcon(arrow_icon("right"))
        self.next_button.setIconSize(QSize(32, 24))
        # Right-to-left layout puts the icon after the text.
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_button.setObjectName("primaryButton")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setMinimumSize(150, 42)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._on_next)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addWidget(self.back_button)
        footer.addStretch()
        footer.addWidget(self.next_button)

        layout.addLayout(footer)
        layout.addStretch()

        for field in (
            self.popSize,
            self.tournamentSize,
            self.genSize,
            self.mutationPercent,
            self.penalizeLevel,
            self.tolerance,
        ):
            field.edit.returnPressed.connect(self._on_next)

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    def _on_next(self) -> None:
        pop_size = parse_int(self.popSize)
        tournament_size = parse_int(self.tournamentSize)
        gen_size = parse_int(self.genSize)
        mutation_percent = parse_float(self.mutationPercent, maximum=100.0)
        penalize_level = parse_float(self.penalizeLevel)
        tolerance = parse_float(self.tolerance)

        if None in (
            pop_size,
            tournament_size,
            gen_size,
            mutation_percent,
            penalize_level,
            tolerance,
        ):
            return

        if tournament_size > pop_size:
            self.tournamentSize.set_error("Must not exceed the population size.")
            return

        self.next_requested.emit(
            AutoDesignParams(
                popSize=pop_size,
                tournamentSize=tournament_size,
                genSize=gen_size,
                mutationPercent=mutation_percent,
                penalizeLevel=penalize_level,
                tolerance=tolerance,
            )
        )
