"""Auto Design - step 2: choose which sections may be used where.

Connects to SAP2000, opens the reference file chosen in step 1, reads
the frame sections defined in it and shows them in a table. Every cell
of the four "Is Allowed for ..." columns is a Yes / No toggle
(default No). Next emits the table as a list of `SectionPermission`.

Editing helpers for long section lists:

* name filter with wildcards (`IPE*`, `*300`, `?` for one character;
  plain text matches anywhere in the name; `,` separates alternatives),
* "apply to the shown sections": set one role to Yes / No for every row
  that passes the filter,
* Undo / Redo (every click, bulk action and import is one step),
* live counters of allowed sections per role,
* Excel import / export (`services/sections_excel.py`).

Only rows hidden by the filter are skipped by the bulk action; Next,
Export and the counters always use all rows.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.sap_client import SapClient
from src.plugins.auto_design.params import SectionPermission
from src.plugins.auto_design.services.sections_excel import (
    HEADERS,
    SectionsExcelError,
    export_sections,
    import_sections,
)
from src.ui.theme import (
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

# (label, table column, SectionPermission field) of the four roles. The
# table columns / Excel columns follow this order (see HEADERS).
ROLES = (
    ("Column", 1, "allowedForColumn"),
    ("Beam", 2, "allowedForBeam"),
    ("Horizontal Brace", 3, "allowedForHorizontalBrace"),
    ("Vertical Brace", 4, "allowedForVerticalBrace"),
)

PAGE_STYLE = f"""
    QFrame#tableCard {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-radius: 12px;
    }}
    QTableWidget#sectionsTable {{
        background: transparent;
        border: none;
        outline: none;
        color: {PAPER};
    }}
    QTableWidget#sectionsTable::item {{
        padding: 0 12px;
        border-bottom: 1px solid {RULE};
    }}
    QTableWidget#sectionsTable::item:hover {{
        background: {INK_HI};
    }}
    QTableWidget#sectionsTable QHeaderView::section {{
        background: {INK_DEEP};
        color: {STEEL};
        border: none;
        border-bottom: 1px solid {RULE_HI};
        padding: 9px 12px;
        font-weight: 600;
    }}
    QLabel#statusText {{
        background: transparent;
        color: {STEEL};
    }}
    QLabel#statusError {{
        background: transparent;
        color: {DANGER};
    }}
    QLabel#toolLabel {{
        background: transparent;
        color: {STEEL};
        font-weight: 600;
    }}
    QLabel#summaryText {{
        background: transparent;
        color: {STEEL};
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
# Name filter
# ---------------------------------------------------------------------


def compile_name_filter(text: str) -> list[re.Pattern]:
    """Patterns for the filter box (empty list = show everything).

    Text with `*` or `?` must match the whole name (`IPE*` = starts with
    IPE); text without them matches anywhere in the name. Alternatives
    are separated by `,` or `;`. Case is ignored.
    """

    patterns = []

    for part in re.split(r"[,;]", text):
        part = part.strip()

        if not part:
            continue

        if "*" in part or "?" in part:
            regex = "".join(
                ".*" if ch == "*" else "." if ch == "?" else re.escape(ch)
                for ch in part
            )
        else:
            regex = ".*" + re.escape(part) + ".*"

        patterns.append(re.compile(regex, re.IGNORECASE | re.DOTALL))

    return patterns


# ---------------------------------------------------------------------
# Worker and table
# ---------------------------------------------------------------------


class _SectionsLoader(QThread):
    """Connects to SAP2000 and reads the section names (off the UI thread)."""

    loaded = Signal(object, list)  # SapClient, section names
    failed = Signal(str)

    def __init__(self, sap_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._sap_path = sap_path

    def run(self) -> None:
        try:
            client = SapClient.connect()
            client.open_model(self._sap_path)
            names = client.frame_section_names()
        except Exception as exc:
            logger.exception("Could not read sections from SAP2000")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.loaded.emit(client, names)


class _ToggleTable(QTableWidget):
    """Table that asks for a toggle when Space / Enter is pressed."""

    toggle_requested = Signal(int, int)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            row, column = self.currentRow(), self.currentColumn()

            if row >= 0 and column >= 1:
                self.toggle_requested.emit(row, column)
                event.accept()
                return

        super().keyPressEvent(event)


# One undoable step: [(row, column, old value, new value), ...]
_Step = list[tuple[int, int, bool, bool]]


class SectionsPage(QWidget):
    """Table of SAP2000 sections with Yes / No permissions."""

    back_requested = Signal()
    next_requested = Signal(list)  # list[SectionPermission]

    def __init__(self, sap_path: str, parent: QWidget | None = None):
        super().__init__(parent)

        self.sap_path = sap_path
        self.client: SapClient | None = None
        self.section_names: list[str] = []
        self._loader: _SectionsLoader | None = None
        self._loading = False
        self._undo: list[_Step] = []
        self._redo: list[_Step] = []

        self.setObjectName("page")
        self.setStyleSheet(PAGE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Choose which sections are allowed to be used as column, beam, "
            "horizontal brace or vertical brace."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        # Status line + progress
        self.status = QLabel("")
        self.status.setObjectName("statusText")
        self.status.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setObjectName("loadingBar")
        self.progress.setRange(0, 0)  # indeterminate
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

        # Row 1: name filter, undo, redo
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name:   IPE*    *300    HEA*, IPE*")
        self.filter_edit.setToolTip(
            "Plain text matches anywhere in the name.\n"
            "* = any characters, ? = one character (IPE* starts with IPE, *300 ends with 300).\n"
            "Use a comma to list several patterns."
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumHeight(34)
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.undo_button = self._tool_button("Undo", self.undo, "Undo (Ctrl+Z)")
        self.redo_button = self._tool_button("Redo", self.redo, "Redo (Ctrl+Y)")

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(self.filter_edit, 1)
        filter_row.addWidget(self.undo_button)
        filter_row.addWidget(self.redo_button)
        layout.addLayout(filter_row)
        layout.addSpacing(8)

        # Row 2: apply one role to every shown row
        apply_label = QLabel("Apply to the shown sections:")
        apply_label.setObjectName("toolLabel")

        self.role_combo = QComboBox()
        self.role_combo.setMinimumHeight(34)
        self.role_combo.setMinimumWidth(170)

        for label, column, _field in ROLES:
            self.role_combo.addItem(label, column)

        self.yes_button = self._tool_button(
            "Set Yes", lambda: self._bulk_set(True), "Set the chosen role to Yes"
        )
        self.no_button = self._tool_button(
            "Set No", lambda: self._bulk_set(False), "Set the chosen role to No"
        )

        bulk_row = QHBoxLayout()
        bulk_row.setSpacing(8)
        bulk_row.addWidget(apply_label)
        bulk_row.addWidget(self.role_combo)
        bulk_row.addWidget(self.yes_button)
        bulk_row.addWidget(self.no_button)
        bulk_row.addStretch()
        layout.addLayout(bulk_row)
        layout.addSpacing(10)

        # Table
        card = QFrame()
        card.setObjectName("tableCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)

        self.table = _ToggleTable(0, len(HEADERS))
        self.table.setObjectName("sectionsTable")
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # Role columns are as wide as their (long) titles; the name takes the rest.
        for column in range(1, len(HEADERS)):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

        header.setHighlightSections(False)

        self.table.cellClicked.connect(self._toggle)
        self.table.toggle_requested.connect(self._toggle)

        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)
        layout.addSpacing(8)

        # Live counters
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

        self.import_button = QPushButton("Import…")
        self.import_button.setToolTip(
            "Read Yes / No values from an Excel file (matched by section name)"
        )
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.setMinimumSize(110, 42)
        self.import_button.clicked.connect(self._import_excel)

        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip("Save all sections and their Yes / No to Excel")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.setMinimumSize(110, 42)
        self.export_button.clicked.connect(self._export_excel)

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
        footer.addWidget(self.import_button)
        footer.addWidget(self.export_button)
        footer.addWidget(self.retry_button)
        footer.addStretch()
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        # Ctrl+Z / Ctrl+Y. When the filter box has focus it keeps its own
        # text undo (Qt gives the focused editor the key first).
        for keys, slot in (
            ("Ctrl+Z", self.undo),
            ("Ctrl+Y", self.redo),
            ("Ctrl+Shift+Z", self.redo),
        ):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        self._set_loading(False)

    @staticmethod
    def _tool_button(text: str, slot, tooltip: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(34)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)

        return button

    # -----------------------------------------------------------------
    # Loading
    # -----------------------------------------------------------------

    def start_loading(self) -> None:
        """Connect to SAP2000, open the file and read the sections."""

        if self._loader is not None and self._loader.isRunning():
            return

        self._set_loading(True)

        self._loader = _SectionsLoader(self.sap_path, self)
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
            self.status.setText(
                "Connecting to SAP2000 and opening the reference file…"
            )

        self._sync_controls()

    def _on_loaded(self, client: SapClient, names: list[str]) -> None:
        self.client = client
        self.section_names = list(names)
        self._fill_table(self.section_names)
        self._set_loading(False)

        file_name = Path(self.sap_path).name
        self.status.setText(f"{len(names)} sections found in {file_name}.")

    def _on_failed(self, error: str) -> None:
        self._fill_table([])
        self._set_loading(False)
        self.status.setText("")
        self.message.setText(f"Could not read the sections from SAP2000: {error}")
        self.message.setVisible(True)
        self.retry_button.setVisible(True)

    # -----------------------------------------------------------------
    # Table
    # -----------------------------------------------------------------

    def _fill_table(self, names: list[str]) -> None:
        self._undo.clear()
        self._redo.clear()
        self.filter_edit.clear()

        self.table.setRowCount(len(names))

        for row, name in enumerate(names):
            self.table.setRowHidden(row, False)

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, name_item)

            for column in range(1, len(HEADERS)):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._set_allowed(item, False)
                self.table.setItem(row, column, item)

        self._update_summary()
        self._sync_controls()

    @staticmethod
    def _set_allowed(item: QTableWidgetItem, allowed: bool) -> None:
        item.setData(Qt.ItemDataRole.UserRole, allowed)
        item.setText("Yes" if allowed else "No")
        item.setForeground(QBrush(QColor(CYAN if allowed else STEEL_DIM)))

        font = item.font()
        font.setBold(allowed)
        item.setFont(font)

    def _allowed(self, row: int, column: int) -> bool:
        return bool(self.table.item(row, column).data(Qt.ItemDataRole.UserRole))

    def _visible_rows(self) -> list[int]:
        return [
            row
            for row in range(self.table.rowCount())
            if not self.table.isRowHidden(row)
        ]

    @property
    def sections(self) -> list[SectionPermission]:
        """Current content of the table (all rows, shown or hidden)."""

        return [
            SectionPermission(
                name=self.table.item(row, 0).text(),
                **{field: self._allowed(row, column) for _l, column, field in ROLES},
            )
            for row in range(self.table.rowCount())
        ]

    # -----------------------------------------------------------------
    # Editing (every edit goes through _apply_changes, so it is undoable)
    # -----------------------------------------------------------------

    def _apply_changes(self, changes: list[tuple[int, int, bool]]) -> int:
        """Set cells as ONE undoable step; returns how many really changed."""

        step: _Step = []

        for row, column, value in changes:
            item = self.table.item(row, column)
            old = bool(item.data(Qt.ItemDataRole.UserRole))

            if old != value:
                self._set_allowed(item, value)
                step.append((row, column, old, value))

        if step:
            self._undo.append(step)
            self._redo.clear()
            self._after_edit()

        return len(step)

    def _toggle(self, row: int, column: int) -> None:
        if column < 1 or self._loading:
            return

        self._apply_changes([(row, column, not self._allowed(row, column))])
        self.message.setVisible(False)

    def _bulk_set(self, allowed: bool) -> None:
        if self._loading:
            return

        column = int(self.role_combo.currentData())
        role = self.role_combo.currentText()
        rows = self._visible_rows()

        changed = self._apply_changes([(row, column, allowed) for row in rows])

        self._notice(
            f"{role} set to {'Yes' if allowed else 'No'} for {len(rows)} shown "
            f"sections ({changed} changed)."
        )

    def undo(self) -> None:
        if self._loading or not self._undo:
            return

        step = self._undo.pop()

        for row, column, old, _new in step:
            self._set_allowed(self.table.item(row, column), old)

        self._redo.append(step)
        self._after_edit()
        self._notice(f"Undone ({len(step)} cells).")

    def redo(self) -> None:
        if self._loading or not self._redo:
            return

        step = self._redo.pop()

        for row, column, _old, new in step:
            self._set_allowed(self.table.item(row, column), new)

        self._undo.append(step)
        self._after_edit()
        self._notice(f"Redone ({len(step)} cells).")

    def _after_edit(self) -> None:
        self._update_summary()
        self._sync_controls()

    # -----------------------------------------------------------------
    # Filter, counters, enabled state
    # -----------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        patterns = compile_name_filter(text)

        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text()
            hidden = bool(patterns) and not any(p.fullmatch(name) for p in patterns)
            self.table.setRowHidden(row, hidden)

        self._update_summary()
        self._sync_controls()

    @staticmethod
    def _number(value: int) -> str:
        return f"<span style='color:{CYAN}; font-weight:600'>{value}</span>"

    def _update_summary(self) -> None:
        total = self.table.rowCount()
        counts = [
            sum(self._allowed(row, column) for row in range(total))
            for _label, column, _field in ROLES
        ]

        parts = [
            f"{label} {self._number(count)}"
            for (label, _column, _field), count in zip(ROLES, counts)
        ]
        self.summary.setText("Allowed:&nbsp;&nbsp; " + "&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts))
        self.shown_label.setText(f"Showing {len(self._visible_rows())} of {total}")

    def _sync_controls(self) -> None:
        ready = not self._loading and self.table.rowCount() > 0
        shown = len(self._visible_rows()) if ready else 0

        for widget in (
            self.filter_edit,
            self.role_combo,
            self.import_button,
            self.export_button,
        ):
            widget.setEnabled(ready)

        self.yes_button.setText(f"Set Yes ({shown})")
        self.no_button.setText(f"Set No ({shown})")
        self.yes_button.setEnabled(shown > 0)
        self.no_button.setEnabled(shown > 0)

        self.undo_button.setEnabled(ready and bool(self._undo))
        self.redo_button.setEnabled(ready and bool(self._redo))
        self.next_button.setEnabled(ready)

    def _notice(self, text: str) -> None:
        self.message.setVisible(False)
        self.status.setText(text)

    def _show_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(True)

    # -----------------------------------------------------------------
    # Excel
    # -----------------------------------------------------------------

    def _export_excel(self) -> None:
        sdb = Path(self.sap_path)
        default = sdb.with_name(f"{sdb.stem}_sections.xlsx")

        path, _ = QFileDialog.getSaveFileName(
            self, "Export sections to Excel", str(default), "Excel files (*.xlsx)"
        )

        if not path:
            return

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        sections = self.sections

        try:
            export_sections(path, sections)
        except SectionsExcelError as exc:
            self._show_error(str(exc))
            return

        self._notice(f"Exported {len(sections)} sections to {Path(path).name}.")

    def _import_excel(self) -> None:
        start = str(Path(self.sap_path).parent)

        path, _ = QFileDialog.getOpenFileName(
            self, "Import sections from Excel", start, "Excel files (*.xlsx)"
        )

        if not path:
            return

        try:
            data = import_sections(path)
        except SectionsExcelError as exc:
            self._show_error(str(exc))
            return

        changes: list[tuple[int, int, bool]] = []
        matched = 0

        for row in range(self.table.rowCount()):
            flags = data.get(self.table.item(row, 0).text())

            if flags is None:
                continue

            matched += 1
            changes.extend(
                (row, column, flag)
                for (_label, column, _field), flag in zip(ROLES, flags)
            )

        if matched == 0:
            self._show_error(
                "None of the section names in the file exist in this model."
            )
            return

        changed = self._apply_changes(changes)

        text = (
            f"Imported {Path(path).name}: {matched} sections matched, "
            f"{changed} cells changed."
        )
        not_in_model = len(data) - matched
        not_in_file = self.table.rowCount() - matched

        if not_in_model:
            text += f" {not_in_model} in the file are not in the model."

        if not_in_file:
            text += f" {not_in_file} in the model are not in the file (unchanged)."

        self._notice(text)

    # -----------------------------------------------------------------
    # Next
    # -----------------------------------------------------------------

    def _on_next(self) -> None:
        sections = self.sections

        if not any(
            getattr(s, field) for s in sections for _l, _c, field in ROLES
        ):
            self._show_error("Allow at least one section before continuing.")
            return

        self.next_requested.emit(sections)