"""SLD to SAP page: inputs, run, and the list of collected issues."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
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

logger = logging.getLogger(__name__)


def _spin(value: float, lo: float, hi: float, decimals: int = 3) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setValue(value)
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

        root = QVBoxLayout(self)
        root.setContentsMargins(34, 24, 34, 24)
        root.setSpacing(10)

        title = QLabel("SLD to SAP")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Convert the CSV files of the piping SLD into SAP2000 joint and distributed loads"
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        # --- parameters -------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.z0 = _spin(0.0, -1e6, 1e6)
        self.tolerance = _spin(10.0, 0.0, 1e4, 1)
        self.end_tolerance = _spin(5.0, 0.0, 1e4, 1)
        self.eqz = _spin(0.2, 0.0, 10.0)
        self.friction = _spin(0.15, 0.0, 10.0)
        fields = [
            ("Z value of the origin of the coordinates in framing elevations (m)", self.z0, "Real level of the origin point in X / Y elevation files."),
            ("Tolerance to find beams for distributed loads (mm)", self.tolerance, "A beam within this distance of the load line counts as on it."),
            ("Tolerance to accept an out of the beam distributed load (mm)", self.end_tolerance, "How far a load may stick out of the beam ends and still belong to that beam."),
            ("The vertical seismic coefficient (0.2*Sds in ASCE7-10)", self.eqz, "Vertical earthquake coefficient, 0.2 x Sds (ASCE 7-10)."),
            ("Pipe on beam Friction coefficient", self.friction, "Steel to steel friction."),
        ]
        for row, (text, widget, tip) in enumerate(fields):
            label = QLabel(text)
            label.setToolTip(tip)
            widget.setToolTip(tip)
            grid.addWidget(label, row, 0)
            grid.addWidget(widget, row, 1)
        grid.setColumnStretch(2, 1)
        root.addLayout(grid)

        # --- files ------------------------------------------------------
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setMaximumHeight(110)
        buttons = QHBoxLayout()
        for text, slot in (
            ("Add CSV files…", self._add_files),
            ("Add folder…", self._add_folder),
            ("Remove", self._remove_files),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch()
        root.addWidget(QLabel("SLD CSV files"))
        root.addWidget(self.files)
        root.addLayout(buttons)

        self.connectivity = self._path_row(root, "SAP2000 Excel file (Connectivity)", self._browse_model)
        self.out_dir = self._path_row(root, "Output folder (default: next to the Excel file)", self._browse_out)

        # --- run --------------------------------------------------------
        run_row = QHBoxLayout()
        self.run_button = QPushButton("Convert")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._run)
        self.open_button = QPushButton("Open output folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_out)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        run_row.addWidget(self.run_button)
        run_row.addWidget(self.open_button)
        run_row.addWidget(self.status, 1)
        root.addLayout(run_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Type", "Code", "File", "Index", "Message"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self._copy_cad)
        self.table.setToolTip("Double-click a row to copy its CAD coordinates.")
        root.addWidget(self.table, 1)

        for box in (self.z0, self.tolerance, self.end_tolerance, self.eqz, self.friction):
            box.valueChanged.connect(self._schedule)
        self.connectivity.textChanged.connect(self._schedule)
        self.run_button.setEnabled(False)
        self.status.setText("Add the SLD CSV files; problems are listed here as soon as they are found.")

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

    def _browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder")
        if folder:
            self.out_dir.setText(folder)

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
            self.status.setText("Add the SLD CSV files.")
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
            self.status.setText(f"Unexpected failure: {exc}")
            return

        self._show_issues(result.issues)
        n_err = len(result.errors)
        if n_err:
            self.status.setText(f"{stage} {n_err} error(s) in {len({i.file for i in result.errors})} file(s).")
        elif model is None:
            self.status.setText(f"{stage} No structural errors.")
        else:
            self._result = result
            self.run_button.setEnabled(True)
            self.status.setText(
                f"{stage} No errors: {len(result.joints)} joint(s), {len(result.loads)} load record(s) ready."
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
                self.status.setText(f"{len(result.errors)} error(s). No output was written.")
                self.run_button.setEnabled(False)
                return
            out = self.out_dir.text().strip() or str(Path(model).parent)
            self._out_files = write_outputs(result, out)
        except Exception as exc:
            logger.exception("SLD to SAP failed")
            self.status.setText(f"Unexpected failure: {exc}")
            return

        self.open_button.setEnabled(True)
        self.status.setText(
            f"Done: {len(result.joints)} joint(s), {len(result.loads)} load record(s) in {out}."
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
        self.table.horizontalHeader().setStretchLastSection(True)

    def _copy_cad(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        cad = item.data(Qt.ItemDataRole.UserRole) if item else None
        if cad:
            QGuiApplication.clipboard().setText(cad)
            self.status.setText(f"Copied CAD coordinates: {cad}")
