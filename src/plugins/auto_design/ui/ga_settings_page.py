"""Auto Design - step 4.2: genetic-algorithm settings and the Simulate Evolution button (it starts the run, steps 5 and on).

Collects the GA parameters, the
database folder where the models of every generation are saved. Values
are validated when the user presses "Simulate Evolution"; on success the
page emits `run_requested` with an `AutoDesignParams`. Back returns to
the frame types page.

The database folder defaults to a folder named "SAP Models" next to the
SAP2000 reference file chosen in step 1 (see `set_sap_path`). The folder
is only checked here, not created.

(The tolerance to detect beams / columns is not asked here any more: it
belongs to the "Frame types" page, `ui/roles_page.py`.)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.plugins.auto_design.params import AutoDesignParams
from src.plugins.auto_design.ui.fields import (
    FORM_STYLE,
    Field,
    parse_float,
    parse_int,
)
from src.plugins.auto_design.ui.icons import evolution_run_icon
from src.plugins.sld_to_sap.ui.icons import folder_icon
from src.ui.theme import AMBER, BLUE, CYAN, FONT_TITLE, ICONS_DIR, PAPER
from src.ui.widgets import arrow_icon
from PySide6.QtGui import QColor, QIcon, QPixmap, QRegion

DEFAULT_FOLDER_NAME = "SAP Models"

# src/ui/assets/icons/Run-Genetic.png (icon of the Simulate Evolution button)
RUN_ICON_PNG = ICONS_DIR / "Run-Genetic.png"

RUN_STYLE = f"""
    QPushButton#runButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {BLUE}, stop:1 #2A9BD8);
        color: #FFFFFF;
        border: 2px solid {CYAN};
        border-radius: 14px;
        font-family: "{FONT_TITLE}";
        font-size: 14pt;
        font-weight: 700;
        padding: 4px 30px;
    }}
    QPushButton#runButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #2A7DC8, stop:1 #46B6EE);
        border-color: {AMBER};
    }}
    QPushButton#runButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #185C99, stop:1 #2A9BD8);
        border-color: {AMBER};
    }}
    QPushButton#runButton:focus {{
        border-color: {AMBER};
    }}
"""

def _trimmed_pixmap(pixmap: QPixmap) -> QPixmap:
    """The pixmap without its transparent margin, so the icon fills its box."""

    bounds = QRegion(pixmap.mask()).boundingRect()

    if bounds.isEmpty():
        return pixmap

    return pixmap.copy(bounds)

class GASettingsPage(QWidget):
    """Parameter form of the genetic algorithm."""

    back_requested = Signal()
    run_requested = Signal(object)  # AutoDesignParams

    def __init__(self, sap_path: str = "", parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")
        self.setStyleSheet(FORM_STYLE + RUN_STYLE)

        self._sap_path = sap_path
        self._folder_edited = False  # True once the user chose / typed a folder

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
        card_layout.setSpacing(0)  # gaps are set explicitly below

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.popSize = Field("Population Size", "Positive integer")
        self.tournamentSize = Field("Tournament Size", "Integer, 2 or more")
        self.genSize = Field("Number of Generations", "Positive integer")
        self.mutationPercent = Field("Mutation Percent (%)", "0 to 100")
        #self.penalizeLevel = Field("Penalize Level Coefficient", "Positive number")

        # Default values
        self.popSize.edit.setText("100")
        self.tournamentSize.edit.setText("4")
        self.genSize.edit.setText("10")
        self.mutationPercent.edit.setText("0")
        #self.penalizeLevel.edit.setText("1")

        grid.addWidget(self.popSize, 0, 0)
        grid.addWidget(self.tournamentSize, 0, 1)
        grid.addWidget(self.genSize, 1, 0)
        grid.addWidget(self.mutationPercent, 1, 1)
        #grid.addWidget(self.penalizeLevel, 2, 0)

        card_layout.addLayout(grid)

        # more air between the option and the folder field below it
        card_layout.addSpacing(24)

        # Database folder of the generation models
        self.modelsFolder = Field(
            "Database Folder for the Generation Models",
            "Folder where the models of every generation are saved",
        )
        self.modelsFolder.edit.textEdited.connect(self._on_folder_typed)

        self.browse_button = QPushButton("Browse…")
        self.browse_button.setIcon(folder_icon())  # same folder icon as SLD to SAP
        self.browse_button.setIconSize(QSize(20, 20))
        self.browse_button.setToolTip("Choose the database folder")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setMinimumHeight(self.modelsFolder.edit.sizeHint().height())
        self.browse_button.clicked.connect(self._browse_folder)
        self.modelsFolder.add_side_widget(self.browse_button)

        card_layout.addWidget(self.modelsFolder)

        layout.addWidget(card)
        layout.addSpacing(28)

        self.set_sap_path(sap_path)

        # -------------------------------------------------------------
        # Footer: Back on the left, the run button in the middle
        # -------------------------------------------------------------

        self.back_button = QPushButton("Back")
        self.back_button.setIcon(arrow_icon("left", color=PAPER))
        self.back_button.setIconSize(QSize(32, 24))
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setMinimumSize(110, 42)
        self.back_button.clicked.connect(self.back_requested.emit)

        self.run_button = QPushButton("  Simulate Evolution")
        self.run_button.setObjectName("runButton")
        run_icon = QPixmap(str(RUN_ICON_PNG))

        if run_icon.isNull():
            # icon file missing: use the icon drawn in code
            self.run_button.setIcon(evolution_run_icon(44))
            self.run_button.setIconSize(QSize(62, 44))
        else:
            self.run_button.setIcon(QIcon(_trimmed_pixmap(run_icon)))
            self.run_button.setIconSize(QSize(60, 60))
        self.run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_button.setMinimumSize(300, 60)
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self._on_run)

        glow = QGraphicsDropShadowEffect(self.run_button)
        glow.setBlurRadius(30)
        glow.setOffset(0, 0)
        glow.setColor(QColor(CYAN).darker(120))
        self.run_button.setGraphicsEffect(glow)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignVCenter)
        footer.addStretch(1)
        footer.addWidget(self.run_button)
        footer.addStretch(1)
        footer.addSpacing(self.back_button.minimumWidth())  # keeps the run button centered

        layout.addLayout(footer)
        layout.addStretch()

        for field in (
            self.popSize,
            self.tournamentSize,
            self.genSize,
            self.mutationPercent,
            #self.penalizeLevel,
            self.modelsFolder,
        ):
            field.edit.returnPressed.connect(self._on_run)

    # -----------------------------------------------------------------
    # Database folder
    # -----------------------------------------------------------------

    def set_sap_path(self, sap_path: str) -> None:
        """Remember the SAP2000 file chosen in step 1; unless the user has
        chosen a folder, the default becomes `<folder of the file>/SAP Models`."""

        self._sap_path = sap_path

        if not self._folder_edited:
            self.modelsFolder.edit.setText(self._default_folder())

    def _default_folder(self) -> str:
        if not self._sap_path:
            return ""

        return str(Path(self._sap_path).parent / DEFAULT_FOLDER_NAME)

    def _on_folder_typed(self, _text: str) -> None:
        self._folder_edited = True

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select the database folder for the generation models",
            self._browse_start(),
        )

        if folder:
            self._folder_edited = True
            self.modelsFolder.edit.setText(str(Path(folder)))

    def _browse_start(self) -> str:
        """Nearest existing folder of the current text (the default
        "SAP Models" folder may not exist yet)."""

        text = self.modelsFolder.text()
        candidates = [Path(text)] if text else []

        if self._sap_path:
            candidates.append(Path(self._sap_path).parent)

        for candidate in candidates:
            for path in (candidate, *candidate.parents):
                if path.is_dir():
                    return str(path)

        return str(Path.home())

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    def _check_folder(self) -> str | None:
        """The folder text if usable, else None (with an inline error)."""

        text = self.modelsFolder.text()

        if not text:
            self.modelsFolder.set_error("Choose the database folder.")
            return None

        path = Path(text)

        if path.exists() and not path.is_dir():
            self.modelsFolder.set_error("This path is a file, not a folder.")
            return None

        return str(path)

    def _on_run(self) -> None:
        pop_size = parse_int(self.popSize)
        tournament_size = parse_int(self.tournamentSize)
        gen_size = parse_int(self.genSize)
        mutation_percent = parse_float(self.mutationPercent, maximum=100.0)
        #penalize_level = parse_float(self.penalizeLevel)
        models_folder = self._check_folder()

        if None in (
            pop_size,
            tournament_size,
            gen_size,
            mutation_percent,
            #penalize_level,
            models_folder,
        ):
            return

        if tournament_size > pop_size:
            self.tournamentSize.set_error("Must not exceed the population size.")
            return

        if tournament_size < 2:
            self.tournamentSize.set_error("Must be at least 2 (two parents are needed).")
            return

        self.run_requested.emit(
            AutoDesignParams(
                popSize=pop_size,
                tournamentSize=tournament_size,
                genSize=gen_size,
                mutationPercent=mutation_percent,
                #penalizeLevel=penalize_level,
                modelsFolder=models_folder,
            )
        )
