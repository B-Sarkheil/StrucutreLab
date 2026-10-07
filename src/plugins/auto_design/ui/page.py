"""Auto Design - step 1: GA settings form.

Collects the genetic-algorithm parameters and the SAP2000 reference
file. Values are validated when the user presses Next; on success the
page emits `next_requested` with an `AutoDesignParams`.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.plugins.auto_design.params import AutoDesignParams
from src.ui.theme import DANGER, INK_RAISED, RULE

PAGE_STYLE = f"""
    QFrame#formCard {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-radius: 12px;
    }}
    QLabel#fieldLabel {{
        background: transparent;
        font-weight: 600;
    }}
    QLabel#fieldError {{
        background: transparent;
        color: {DANGER};
        font-size: 8.5pt;
    }}
    QLineEdit[invalid="true"] {{
        border: 1px solid {DANGER};
    }}
"""


class Field(QWidget):
    """Label + line edit + inline error message."""

    def __init__(
        self,
        label: str,
        placeholder: str,
        browse: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.label = QLabel(label)
        self.label.setObjectName("fieldLabel")
        self.label.setWordWrap(True)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setProperty("invalid", False)
        self.edit.textChanged.connect(self.clear_error)

        self.error = QLabel("")
        self.error.setObjectName("fieldError")
        self.error.setVisible(False)

        layout.addWidget(self.label)

        if browse is None:
            layout.addWidget(self.edit)
        else:
            button = QPushButton("Browse…")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(browse)

            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(self.edit, 1)
            row.addWidget(button)
            layout.addLayout(row)

        layout.addWidget(self.error)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(True)
        self._set_invalid(True)

    def clear_error(self) -> None:
        self.error.setVisible(False)
        self._set_invalid(False)

    def _set_invalid(self, invalid: bool) -> None:
        self.edit.setProperty("invalid", invalid)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)


class AutoDesignPage(QWidget):
    """Parameter form of the Auto Design plugin."""

    next_requested = Signal(object)  # AutoDesignParams

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")
        self.setStyleSheet(PAGE_STYLE)

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
        subtitle = QLabel("Genetic algorithm settings and SAP2000 reference model.")
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

        grid.addWidget(self.popSize, 0, 0)
        grid.addWidget(self.tournamentSize, 0, 1)
        grid.addWidget(self.genSize, 1, 0)
        grid.addWidget(self.mutationPercent, 1, 1)
        grid.addWidget(self.penalizeLevel, 2, 0)
        grid.addWidget(self.tolerance, 2, 1)

        card_layout.addLayout(grid)

        # SAP2000 reference file (full width)
        self.sapPath = Field(
            "SAP2000 Reference File", "Select a .sdb file", browse=self._browse
        )

        card_layout.addWidget(self.sapPath)

        layout.addWidget(card)
        layout.addSpacing(18)

        # -------------------------------------------------------------
        # Next
        # -------------------------------------------------------------

        self.next_button = QPushButton("Next  →")
        self.next_button.setObjectName("primaryButton")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setMinimumSize(150, 42)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._on_next)

        footer = QHBoxLayout()
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
            self.sapPath,
        ):
            field.edit.returnPressed.connect(self._on_next)

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    def _browse(self) -> None:
        start = self.sapPath.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SAP2000 reference file",
            start,
            "SAP2000 files (*.sdb);;All files (*)",
        )

        if path:
            self.sapPath.edit.setText(str(Path(path)))

    @staticmethod
    def _parse_int(field: Field) -> int | None:
        text = field.text()

        if not text.isdigit() or int(text) <= 0:
            field.set_error("Enter a positive integer.")
            return None

        return int(text)

    @staticmethod
    def _parse_float(
        field: Field, *, minimum_exclusive: float = 0.0, maximum: float | None = None
    ) -> float | None:
        text = field.text().replace(",", ".")

        try:
            value = float(text)
        except ValueError:
            field.set_error("Enter a number.")
            return None

        if value != value or value in (float("inf"), float("-inf")):
            field.set_error("Enter a finite number.")
            return None

        if maximum is not None:
            if not 0.0 <= value <= maximum:
                field.set_error(f"Enter a value between 0 and {maximum:g}.")
                return None
        elif value <= minimum_exclusive:
            field.set_error("Enter a positive number.")
            return None

        return value

    def _on_next(self) -> None:
        pop_size = self._parse_int(self.popSize)
        tournament_size = self._parse_int(self.tournamentSize)
        gen_size = self._parse_int(self.genSize)
        mutaion_percent = self._parse_float(self.mutationPercent, maximum=100.0)
        penalize_level = self._parse_float(self.penalizeLevel)
        tolerance = self._parse_float(self.tolerance)

        sap_path = self.sapPath.text()
        sap_ok = True

        if not sap_path:
            self.sapPath.set_error("Select the SAP2000 reference file.")
            sap_ok = False
        elif not Path(sap_path).is_file():
            self.sapPath.set_error("File not found.")
            sap_ok = False

        if (
            None in (
                pop_size,
                tournament_size,
                gen_size,
                mutaion_percent,
                penalize_level,
                tolerance,
            )
            or not sap_ok
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
                mutationPercent=mutaion_percent,
                penalizeLevel=penalize_level,
                tolerance=tolerance,
                sapPath=sap_path,
            )
        )
