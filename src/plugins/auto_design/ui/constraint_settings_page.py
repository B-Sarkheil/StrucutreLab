"""Auto Design - step 4.1: Constraint settings (after the Frame types page, step 3;
the GA settings page, step 4.2, follows).

Collects the constraint settings of the run:

* DCR Goal (positive real number, default 1),
* Deflection Goal: the user types only the number n of "L / n" (positive
  integer, default 300); the page shows the meaning live ("L / 300"),
* Element Constraint Coefficient (DCR and Deflection) (positive real, default 1),
* General Constraint Coefficient (Drift) (positive real, default 1),
* Deflection Combination: one of the load combinations of the reference
  model (combo box; `SapClient.load_combination_names` is called in a
  worker thread; this page makes no SAP2000 call of its own),
* the option "Update Seismic Loads for Each Offspring" (moved here from the
  GA settings page).

Values are validated when Next is pressed; on success the page emits
`next_requested` with a `ConstraintParams`. Back returns to the frame types
page. The page is created once per reference file, so typed values survive
Back / Next.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.sap_client import SapClient
from src.plugins.auto_design.params import ConstraintParams
from src.plugins.auto_design.ui.fields import (
    FORM_STYLE,
    FancyCheckBox,
    Field,
    parse_float,
    parse_int,
)
from src.ui.theme import CYAN, DANGER, INK_HI, PAPER, STEEL
from src.ui.widgets import arrow_icon

logger = logging.getLogger(__name__)

DEFAULT_DEFLECTION_DIVISOR = "300"

PAGE_STYLE = f"""
    QLabel#statusText {{
        background: transparent;
        color: {STEEL};
    }}
    QLabel#statusError {{
        background: transparent;
        color: {DANGER};
    }}
    QLabel#deflectionPreview {{
        background: transparent;
        color: {CYAN};
        font-weight: 600;
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


class _ComboLoader(QThread):
    """Opens the reference model and reads its load combinations (off the UI thread)."""

    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, client: SapClient, sap_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._client = client
        self._sap_path = sap_path

    def run(self) -> None:
        try:
            self._client.open_model(self._sap_path)
            names = self._client.load_combination_names()
        except Exception as exc:
            logger.exception("Could not read the load combinations from SAP2000")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.loaded.emit(names)


class ConstraintSettingsPage(QWidget):
    """Constraint settings form (see the module docstring)."""

    back_requested = Signal()
    next_requested = Signal(object)  # ConstraintParams

    def __init__(self, sap_path: str, client: SapClient, parent: QWidget | None = None):
        super().__init__(parent)

        self.sap_path = sap_path
        self.client = client

        self._loader: _ComboLoader | None = None
        self._loading = False
        self._loaded = False

        self.setObjectName("page")
        self.setStyleSheet(FORM_STYLE + PAGE_STYLE)

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
        subtitle = QLabel("Constraint settings")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        # Status line + progress + error (loading of the load combinations)
        self.status = QLabel("")
        self.status.setObjectName("statusText")
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
        layout.addSpacing(10)

        # -------------------------------------------------------------
        # Form card
        # -------------------------------------------------------------

        card = QFrame()
        card.setObjectName("formCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 22)
        card_layout.setSpacing(0)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.dcrGoal = Field("DCR Goal", "Positive number")
        self.deflectionDivisor = Field(
            "Deflection Goal (L / n): enter n", "Positive integer"
        )
        self.elementCoefficient = Field(
            "Element Constraint Coefficient (DCR and Deflection)", "Positive number"
        )
        self.generalCoefficient = Field(
            "General Constraint Coefficient (Drift)", "Positive number"
        )

        self.dcrGoal.edit.setText("1")
        self.deflectionDivisor.edit.setText(DEFAULT_DEFLECTION_DIVISOR)
        self.elementCoefficient.edit.setText("1")
        self.generalCoefficient.edit.setText("1")

        # live meaning of the number typed for the deflection goal
        self.deflection_preview = QLabel("")
        self.deflection_preview.setObjectName("deflectionPreview")
        self.deflection_preview.setMinimumWidth(80)
        self.deflectionDivisor.add_side_widget(self.deflection_preview)
        self.deflectionDivisor.edit.textChanged.connect(self._update_deflection_preview)
        self._update_deflection_preview()

        grid.addWidget(self.dcrGoal, 0, 0)
        grid.addWidget(self.deflectionDivisor, 0, 1)
        grid.addWidget(self.elementCoefficient, 1, 0)
        grid.addWidget(self.generalCoefficient, 1, 1)

        card_layout.addLayout(grid)
        card_layout.addSpacing(8)

        # Deflection combination (combo box + Retry when the reading failed)
        combo_label = QLabel("Deflection Combination")
        combo_label.setObjectName("fieldLabel")

        self.combo = QComboBox()
        self.combo.setMinimumHeight(34)
        self.combo.setMaxVisibleItems(15)
        self.combo.currentIndexChanged.connect(self._clear_combo_error)

        self.retry_button = QPushButton("Reload")
        self.retry_button.setToolTip("Read the load combinations of the model again")
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setMinimumHeight(34)
        self.retry_button.clicked.connect(self.start_loading)

        combo_row = QHBoxLayout()
        combo_row.setSpacing(8)
        combo_row.addWidget(self.combo, 1)
        combo_row.addWidget(self.retry_button)

        self.combo_error = QLabel("")
        self.combo_error.setObjectName("fieldError")
        self.combo_error.setFixedHeight(Field.ERROR_HEIGHT)

        card_layout.addWidget(combo_label)
        card_layout.addSpacing(4)
        card_layout.addLayout(combo_row)
        card_layout.addWidget(self.combo_error)
        card_layout.addSpacing(16)

        # Option moved here from the GA settings page
        self.updateSeismicLoads = FancyCheckBox("Update Seismic Loads for Each Offspring")
        self.updateSeismicLoads.setChecked(False)
        card_layout.addWidget(self.updateSeismicLoads, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card)
        layout.addSpacing(28)

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
        footer.addStretch(1)
        footer.addWidget(self.next_button)
        layout.addLayout(footer)
        layout.addStretch()

        for field in (
            self.dcrGoal,
            self.deflectionDivisor,
            self.elementCoefficient,
            self.generalCoefficient,
        ):
            field.edit.returnPressed.connect(self._on_next)

        self._set_loading(False)

    # -----------------------------------------------------------------
    # Deflection preview
    # -----------------------------------------------------------------

    def _update_deflection_preview(self, *_args) -> None:
        text = self.deflectionDivisor.text()
        shown = text if text.isdigit() and int(text) > 0 else "n"
        self.deflection_preview.setText(f"= L / {shown}")

    # -----------------------------------------------------------------
    # Loading of the load combinations
    # -----------------------------------------------------------------

    def start_loading(self) -> None:
        """Open the reference model and read its load combinations."""

        if self._loader is not None and self._loader.isRunning():
            return

        self._set_loading(True)

        self._loader = _ComboLoader(self.client, self.sap_path, self)
        self._loader.loaded.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._loader.finished.connect(self._loader.deleteLater)
        self._loader.start()

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.progress.setVisible(loading)
        self.message.setVisible(False)

        if loading:
            self.status.setText("Reading the load combinations of the model…")

        self._sync_controls()

    def _on_loaded(self, names: list) -> None:
        previous = self.combo.currentData()

        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("Select a combination…", None)

        for name in names:
            self.combo.addItem(name, name)

        position = self.combo.findData(previous) if previous else -1
        self.combo.setCurrentIndex(max(0, position))  # keeps the old choice when it still exists
        self.combo.blockSignals(False)

        self._loaded = bool(names)
        self._set_loading(False)

        if names:
            self.status.setText(f"{len(names)} load combinations found in the model.")
        else:
            self.status.setText("")
            self.message.setText("The model has no load combinations.")
            self.message.setVisible(True)

    def _on_failed(self, error: str) -> None:
        self._loaded = False
        self._set_loading(False)
        self.status.setText("")
        self.message.setText(f"Could not read the load combinations from SAP2000: {error}")
        self.message.setVisible(True)

    def _sync_controls(self) -> None:
        self.combo.setEnabled(not self._loading and self._loaded)
        self.retry_button.setEnabled(not self._loading)
        self.back_button.setEnabled(not self._loading)
        self.next_button.setEnabled(not self._loading)

    def _clear_combo_error(self, *_args) -> None:
        self.combo_error.setText("")

    # -----------------------------------------------------------------
    # Next
    # -----------------------------------------------------------------

    def _on_next(self) -> None:
        if self._loading:
            return

        # all fields are parsed (not only the first wrong one) so every error shows
        dcr_goal = parse_float(self.dcrGoal)
        divisor = parse_int(self.deflectionDivisor)
        element = parse_float(self.elementCoefficient)
        general = parse_float(self.generalCoefficient)
        combo = self.combo.currentData()

        if combo is None:
            self.combo_error.setText("Choose the deflection combination.")

        if None in (dcr_goal, divisor, element, general, combo):
            return

        self.next_requested.emit(
            ConstraintParams(
                dcrGoal=dcr_goal,
                deflectionDivisor=divisor,
                elementCoefficient=element,
                generalCoefficient=general,
                deflectionCombo=str(combo),
                updateSeismicLoads=self.updateSeismicLoads.isChecked(),
            )
        )
