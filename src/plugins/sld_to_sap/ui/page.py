"""SLD to SAP page: inputs, run, and the list of collected issues."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHeaderView,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.plugins.sld_to_sap.params import SldParams
from src.plugins.sld_to_sap.services.exporter import write_outputs
from src.plugins.sld_to_sap.services.issues import ERROR
from src.plugins.sld_to_sap.services.pipeline import ConversionResult, check_structure, convert
from src.plugins.sld_to_sap.ui.icons import convert_icon, document_icon, message_pixmap

logger = logging.getLogger(__name__)

# Files offered for download at the top of the page (must exist in this folder).
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
LISP_FILE = "SLD2SAP.lsp"
PDF_FILE = "Rules of SLD2SAP.pdf"

# Message panel: accent color per message level.
_LEVEL_ACCENT = {"info": "#48B8FF", "ok": "#3FCF8E", "error": "#FF6B6B"}
_LEVEL_TITLE = {"info": "Messages", "ok": "All good", "error": "Needs attention"}


def _panel_style(accent: str) -> str:
    return f"""
        QWidget#messagesPanel {{
            background-color: #0B1728;
            border: 1px solid {accent};
            border-left: 5px solid {accent};
            border-radius: 10px;
        }}
        QLabel#assistantIcon {{
            background: transparent;
            border: none;
        }}
        QLabel#assistantTitle {{
            color: {accent};
            font-size: 15pt;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel#assistantMessage {{
            color: #F2F8FF;
            font-size: 12pt;
            background: transparent;
            border: none;
            padding: 2px 0;
        }}
    """


_DOWNLOAD_STYLE = """
    QPushButton#downloadButton {
        background-color: #101C30;
        color: #E9F0F8;
        border: 1px solid #31496E;
        border-radius: 9px;
        padding: 8px 16px 8px 12px;
        font-size: 10pt;
        font-weight: 600;
        text-align: left;
    }
    QPushButton#downloadButton:hover {
        background-color: #16263F;
        border-color: #5CC8F0;
        color: #FFFFFF;
    }
    QPushButton#downloadButton:pressed {
        background-color: #1F3352;
    }
    QPushButton#downloadButton:focus {
        border-color: #FFB224;
    }
"""

_CONVERT_STYLE = """
    QPushButton#convertButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #2F8FE0, stop:1 #1F6FB5);
        color: #FFFFFF;
        border: 1px solid #4BA3EC;
        border-radius: 12px;
        padding: 0 30px;
        font-size: 13pt;
        font-weight: 700;
    }
    QPushButton#convertButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #3D9CEE, stop:1 #2A7DC8);
        border-color: #7CC0F5;
    }
    QPushButton#convertButton:pressed {
        background-color: #185C99;
    }
    QPushButton#convertButton:focus {
        border-color: #FFB224;
    }
    QPushButton#convertButton:disabled {
        background-color: #252F3A;
        color: #8794A2;
        border: 1px solid #3A4653;
    }
"""


class _NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Prevent accidental value changes when the mouse wheel passes over a field."""

    def wheelEvent(self, event):
        event.ignore()


def _spin(value: float, lo: float, hi: float, decimals: int = 3) -> QDoubleSpinBox:
    box = _NoWheelDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setValue(value)
    # Keep numeric inputs visibly distinct from the dark Conversion parameters panel.
    box.setStyleSheet("""
        QDoubleSpinBox {
            background-color: #111E30;
            color: #E6EDF7;
            border: 1px solid #344B68;
            border-radius: 5px;
            padding: 5px 8px;
            min-height: 20px;
            selection-background-color: #1976D2;
        }
        QDoubleSpinBox:hover {
            border-color: #4B6B91;
        }
        QDoubleSpinBox:focus {
            border: 1px solid #4DB3FF;
        }
    """)
    return box


class SldToSapPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._out_files: list[Path] = []
        self._result: ConversionResult | None = None

        # Checks re-run automatically (debounced) whenever an input changes.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._validate)

        # Keep the complete page inside a scroll area so controls remain
        # reachable when the main window is not maximized or has limited height.
        from PySide6.QtWidgets import QScrollArea

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("sldPageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer_layout.addWidget(scroll_area)

        content = QWidget()
        content.setObjectName("sldPageContent")
        scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)

        # --- header: title on the left, download buttons on the right ----
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = QLabel("SLD to SAP")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Convert the CSV files of the piping SLD into SAP2000 joint and distributed load tables."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col, 1)

        downloads = QHBoxLayout()
        downloads.setSpacing(10)
        self.lisp_button = self._download_button(
            "Download LISP",
            document_icon("LSP"),
            "AutoCAD LISP that exports the TAGGED_LOADS layer to the CSV files (SLD2SAP.lsp).",
            lambda: self._download(LISP_FILE, "Save the AutoCAD LISP file", "AutoLISP (*.lsp)"),
        )
        self.pdf_button = self._download_button(
            "Open Rules",
            document_icon("PDF", "#FFB224"),
            "Open the piping SLD rules which is contracted with the piping department.",
            self._open_pdf,
        )
        downloads.addWidget(self.lisp_button)
        downloads.addWidget(self.pdf_button)
        header_row.addLayout(downloads, 0)
        root.addLayout(header_row)

        # --- parameters -------------------------------------------------
        # Visible field hints replace tooltip-only explanations and wrap on narrow windows.
        params_box = QGroupBox("Conversion parameters")
        params_grid = QGridLayout(params_box)
        params_grid.setHorizontalSpacing(16)
        params_grid.setVerticalSpacing(8)
        self.z0 = _spin(0.0, -1e6, 1e6)
        self.tolerance = _spin(10.0, 0.0, 1e4, 1)
        self.end_tolerance = _spin(5.0, 0.0, 1e4, 1)
        self.eqz = _spin(0.2, 0.0, 10.0)
        self.friction = _spin(0.15, 0.0, 10.0)
        fields = [
            ("Z value of the origin of the coordinates in framing elevations (m)", self.z0, "Level of the origin point in XZ or YZ views in SAP2000."),
            ("Tolerance to find beams for distributed loads (mm)", self.tolerance, "A beam within this distance of the load line counts as on it."),
            ("Tolerance to accept out of beam distributed load (mm)", self.end_tolerance, "How far a load may stick out of the beam ends and still belong to that beam."),
            ("The vertical seismic coefficient", self.eqz, "EQ.Z coefficient, 0.2 x Sds (ASCE7-10)."),
            ("Friction coefficient", self.friction, "Pipe on beam friction"),
        ]
        for index, (caption, widget, help_text) in enumerate(fields):
            cell = QWidget()
            # Keep each field container visually integrated with its parent group.
            cell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            cell.setStyleSheet("background-color: transparent; border: none;")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            label = QLabel(caption)
            label.setWordWrap(True)
            hint = QLabel(help_text)
            hint.setObjectName("fieldHint")
            hint.setWordWrap(True)
            widget.setToolTip(help_text)
            cell_layout.addWidget(label)
            cell_layout.addWidget(widget)
            cell_layout.addWidget(hint)
            params_grid.addWidget(cell, index // 2, index % 2)
        params_grid.setColumnStretch(0, 1)
        params_grid.setColumnStretch(1, 1)
        root.addWidget(params_box)

        # --- files ------------------------------------------------------
        files_box = QGroupBox("SLD CSV Files")
        files_layout = QVBoxLayout(files_box)
        files_layout.setContentsMargins(12, 16, 12, 12)
        files_layout.setSpacing(8)
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setMinimumHeight(64)
        self.files.setMaximumHeight(110)
        buttons = QHBoxLayout()
        for text, slot in (
            ("+ Add CSV", self._add_files),
            ("+ Add folder", self._add_folder),
            ("− Remove selected", self._remove_files),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch()
        files_layout.addWidget(self.files)
        files_layout.addLayout(buttons)
        root.addWidget(files_box)

        self.connectivity = self._path_row(root, "SAP2000 Connectivity File", self._browse_model)

        # --- messages: the page talking to the user ---------------------
        self.assistant_box = QWidget()
        self.assistant_box.setObjectName("messagesPanel")
        self.assistant_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        assistant_layout = QVBoxLayout(self.assistant_box)
        assistant_layout.setContentsMargins(16, 12, 16, 14)
        assistant_layout.setSpacing(8)

        assistant_heading = QHBoxLayout()
        assistant_heading.setSpacing(10)
        self.assistant_icon = QLabel()
        self.assistant_icon.setObjectName("assistantIcon")
        self.assistant_icon.setFixedSize(30, 30)
        self.assistant_title = QLabel("Messages")
        self.assistant_title.setObjectName("assistantTitle")
        assistant_heading.addWidget(self.assistant_icon)
        assistant_heading.addWidget(self.assistant_title)
        assistant_heading.addStretch(1)
        assistant_layout.addLayout(assistant_heading)

        self.status = QLabel()
        self.status.setObjectName("assistantMessage")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(48)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        assistant_layout.addWidget(self.status)
        root.addWidget(self.assistant_box)
        self._say(
            "Add the SLD CSV files to begin. Detected issues and conversion status will appear here."
        )

        # --- run --------------------------------------------------------
        run_row = QHBoxLayout()
        run_row.setSpacing(12)
        self.run_button = QPushButton("Convert")
        self.run_button.setObjectName("convertButton")
        self.run_button.setIcon(convert_icon())
        self.run_button.setIconSize(QSize(28, 28))
        self.run_button.setMinimumSize(260, 52)
        self.run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_button.setStyleSheet(_CONVERT_STYLE)
        self.run_button.clicked.connect(self._run)
        self.open_button = QPushButton("Open output folder")
        self.open_button.setMinimumHeight(52)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_out)
        run_row.addStretch(1)
        run_row.addWidget(self.open_button)
        run_row.addWidget(self.run_button)
        root.addLayout(run_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Type", "Code", "File", "Index", "Message"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # Restore predictable initial column widths; users may still resize them.
        for column, width in enumerate((78, 78, 190, 72, 420)):
            self.table.setColumnWidth(column, width)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self._copy_cad)
        self.table.setToolTip("Double-click a row to copy its CAD coordinates.")
        self.table.setMinimumHeight(180)
        root.addWidget(self.table, 1)

        for box in (self.z0, self.tolerance, self.end_tolerance, self.eqz, self.friction):
            box.valueChanged.connect(self._schedule)
        self.connectivity.textChanged.connect(self._schedule)
        self.run_button.setEnabled(False)

    # ------------------------------------------------------------------
    def _say(self, text: str, level: str = "info") -> None:
        """Show a message in the Messages panel. level: info | ok | error."""
        accent = _LEVEL_ACCENT.get(level, _LEVEL_ACCENT["info"])
        self.assistant_box.setStyleSheet(_panel_style(accent))
        self.assistant_icon.setPixmap(message_pixmap(accent, 30))
        self.assistant_title.setText(_LEVEL_TITLE.get(level, "Messages"))
        self.status.setText(text)

    def _download_button(self, text: str, icon, tooltip: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("downloadButton")
        button.setIcon(icon)
        button.setIconSize(QSize(22, 22))
        button.setToolTip(tooltip)
        button.setMinimumHeight(42)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(_DOWNLOAD_STYLE)
        button.clicked.connect(slot)
        return button

    def _download(self, filename: str, caption: str, file_filter: str) -> None:
        """Copy a bundled file to a place the user chooses."""
        source = ASSETS_DIR / filename
        if not source.is_file():
            self._say(
                f"{filename} is not included in this installation (expected in {ASSETS_DIR}). "
                "Please report it to the developer.",
                "error",
            )
            return
        target, _ = QFileDialog.getSaveFileName(
            self, caption, str(Path.home() / "Downloads" / filename), file_filter
        )
        if not target:
            return
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            logger.exception("Could not save %s", filename)
            self._say(f"Could not save {filename}: {exc}", "error")
            return
        self._say(f"{filename} was saved to {target}.", "ok")

    def _open_pdf(self) -> None:
        """Open the bundled rules PDF in the user's PDF viewer.

        A copy in the temp folder is opened, so a viewer never locks a file
        inside the app folder (which would block auto-updates).
        """
        source = ASSETS_DIR / PDF_FILE
        if not source.is_file():
            self._say(
                f"{PDF_FILE} is not included in this installation (expected in {ASSETS_DIR}). "
                "Please report it to the developer.",
                "error",
            )
            return
        try:
            folder = Path(tempfile.gettempdir()) / "StructureLab"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / PDF_FILE
            shutil.copyfile(source, target)
        except OSError as exc:
            # e.g. an older copy is still open in the viewer: open that one
            logger.warning("Could not refresh the temporary PDF copy: %s", exc)
            target = Path(tempfile.gettempdir()) / "StructureLab" / PDF_FILE
            if not target.is_file():
                self._say(f"Could not open {PDF_FILE}: {exc}", "error")
                return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            self._say(f"No program was found to open {PDF_FILE}.", "error")

    # ------------------------------------------------------------------
    def _path_row(self, layout: QVBoxLayout, caption: str, slot) -> QLineEdit:
        layout.addWidget(QLabel(caption))
        row = QHBoxLayout()
        edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(slot)
        row.addWidget(edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        return edit

    def _add_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "SLD CSV files", "", "CSV (*.csv)")
        for n in names:
            self._add_path(n)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder with SLD CSV files")
        if folder:
            self._add_path(folder)

    def _add_path(self, path: str) -> None:
        if not self.files.findItems(path, Qt.MatchFlag.MatchExactly):
            self.files.addItem(path)
            self._schedule()

    def _remove_files(self) -> None:
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self._schedule()

    def _browse_model(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "SAP2000 Excel file", "", "Excel (*.xlsx)")
        if name:
            self.connectivity.setText(name)

    def _open_out(self) -> None:
        if self._out_files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._out_files[0].parent)))

    # ------------------------------------------------------------------
    def _schedule(self, *_args) -> None:
        self._timer.start()

    def _inputs(self):
        paths = [self.files.item(i).text() for i in range(self.files.count())]
        model = self.connectivity.text().strip()
        params = SldParams(
            z0=self.z0.value(),
            tolerance_mm=self.tolerance.value(),
            end_tolerance_mm=self.end_tolerance.value(),
            eqz_coef=self.eqz.value(),
            friction_coef=self.friction.value(),
        )
        return paths, (model if model and Path(model).is_file() else None), params

    def _validate(self) -> None:
        """Stage 1 (CSV only) always; stage 2 (with the Excel model) once it is given."""
        paths, model, params = self._inputs()
        self._result = None
        self.run_button.setEnabled(False)
        if not paths:
            self.table.setRowCount(0)
            self._say("Add the SLD CSV files.")
            return
        try:
            if model is None:
                result = check_structure(paths)
                stage = "Structure check (CSV files only). Select the SAP2000 Excel file to match frames."
            else:
                result = convert(params, paths, model)
                stage = "Full check."
        except Exception as exc:
            logger.exception("SLD to SAP check failed")
            self._say(f"Unexpected failure: {exc}", "error")
            return

        self._show_issues(result.issues)
        n_err = len(result.errors)
        if n_err:
            self._say(
                f"{stage} {n_err} error(s) in {len({i.file for i in result.errors})} file(s).",
                "error",
            )
        elif model is None:
            self._say(f"{stage} No structural errors.", "ok")
        else:
            self._result = result
            self.run_button.setEnabled(True)
            self._say(
                f"{stage} No errors: {len(result.joints)} joint(s), "
                f"{len(result.loads)} load record(s) ready.",
                "ok",
            )

    def _run(self) -> None:
        paths, model, params = self._inputs()
        if model is None:
            return
        self._out_files = []
        self.open_button.setEnabled(False)
        try:
            result = convert(params, paths, model)
            self._show_issues(result.issues)
            if not result.ok:  # inputs changed since the last check
                self._say(f"{len(result.errors)} error(s). No output was written.", "error")
                self.run_button.setEnabled(False)
                return
            # Ask for the output folder after validation succeeds.
            default_out = str(Path(model).parent)
            out = QFileDialog.getExistingDirectory(
                self,
                "Select output folder",
                default_out,
            )
            if not out:
                self._say("Conversion cancelled. No output was written.")
                return

            self._out_files = write_outputs(result, out)
        except Exception as exc:
            logger.exception("SLD to SAP failed")
            self._say(f"Unexpected failure: {exc}", "error")
            return

        self.open_button.setEnabled(True)
        self._say(
            f"Done: {len(result.joints)} joint(s), {len(result.loads)} load record(s) in {out}.",
            "ok",
        )

    def _show_issues(self, issues) -> None:
        # Grouped by file, then by Index; errors before warnings inside the same file.
        issues = sorted(
            issues,
            key=lambda i: (i.file.casefold(), i.severity != ERROR, i.index if i.index is not None else -1),
        )
        self.table.setRowCount(len(issues))
        for r, i in enumerate(issues):
            kind = "Error" if i.severity == ERROR else "Warning"
            cells = [kind, i.code, i.file, "" if i.index is None else str(i.index), i.message]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if i.cad:
                    item.setData(Qt.ItemDataRole.UserRole, f"{i.cad[0]:.3f}, {i.cad[1]:.3f}")
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # Restore predictable initial column widths; users may still resize them.
        for column, width in enumerate((78, 78, 190, 72, 420)):
            self.table.setColumnWidth(column, width)

    def _copy_cad(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        cad = item.data(Qt.ItemDataRole.UserRole) if item else None
        if cad:
            QGuiApplication.clipboard().setText(cad)
            self._say(f"Copied CAD coordinates: {cad}")