"""Auto Design - step 2: choose which sections may be used where.

Connects to SAP2000, opens the reference file chosen in step 1, reads
the frame sections defined in it and shows them in a table. Every cell
of the three "Is Allowed for ..." columns is a Yes / No toggle
(default No). Next emits the table as a list of `SectionPermission`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.sap_client import SapClient
from src.plugins.auto_design.params import SectionPermission
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

logger = logging.getLogger(__name__)

HEADERS = (
    "Section",
    "Is Allowed for Column",
    "Is Allowed for Beam",
    "Is Allowed for Brace",
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

        self.setObjectName("page")
        self.setStyleSheet(PAGE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Choose which sections are allowed to be used as column, beam or brace."
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

        for column in range(1, len(HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, 175)

        header.setHighlightSections(False)

        self.table.cellClicked.connect(self._toggle)
        self.table.toggle_requested.connect(self._toggle)

        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)
        layout.addSpacing(16)

        # Footer
        self.back_button = QPushButton("←  Back")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setMinimumSize(110, 42)
        self.back_button.clicked.connect(self.back_requested.emit)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setMinimumSize(110, 42)
        self.retry_button.clicked.connect(self.start_loading)
        self.retry_button.setVisible(False)

        self.next_button = QPushButton("Next  →")
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
        self.progress.setVisible(loading)
        self.table.setEnabled(not loading)
        self.back_button.setEnabled(not loading)
        self.next_button.setEnabled(not loading and self.table.rowCount() > 0)
        self.retry_button.setVisible(False)
        self.message.setVisible(False)

        if loading:
            self.status.setText(
                "Connecting to SAP2000 and opening the reference file…"
            )

    def _on_loaded(self, client: SapClient, names: list[str]) -> None:
        self.client = client
        self.section_names = list(names)
        self._fill_table(self.section_names)
        self._set_loading(False)

        file_name = Path(self.sap_path).name
        self.status.setText(f"{len(names)} sections found in {file_name}.")

    def _on_failed(self, error: str) -> None:
        self._set_loading(False)
        self.status.setText("")
        self.message.setText(f"Could not read the sections from SAP2000: {error}")
        self.message.setVisible(True)
        self.retry_button.setVisible(True)
        self.next_button.setEnabled(False)

    # -----------------------------------------------------------------
    # Table
    # -----------------------------------------------------------------

    def _fill_table(self, names: list[str]) -> None:
        self.table.setRowCount(len(names))

        for row, name in enumerate(names):
            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, name_item)

            for column in range(1, len(HEADERS)):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._set_allowed(item, False)
                self.table.setItem(row, column, item)

    @staticmethod
    def _set_allowed(item: QTableWidgetItem, allowed: bool) -> None:
        item.setData(Qt.ItemDataRole.UserRole, allowed)
        item.setText("Yes" if allowed else "No")
        item.setForeground(QBrush(QColor(CYAN if allowed else STEEL_DIM)))

        font = item.font()
        font.setBold(allowed)
        item.setFont(font)

    def _toggle(self, row: int, column: int) -> None:
        if column < 1:
            return

        item = self.table.item(row, column)

        if item is not None:
            self._set_allowed(item, not bool(item.data(Qt.ItemDataRole.UserRole)))
            self.message.setVisible(False)

    def _allowed(self, row: int, column: int) -> bool:
        return bool(self.table.item(row, column).data(Qt.ItemDataRole.UserRole))

    @property
    def sections(self) -> list[SectionPermission]:
        """Current content of the table."""

        return [
            SectionPermission(
                name=self.table.item(row, 0).text(),
                allowedForColumn=self._allowed(row, 1),
                allowedForBeam=self._allowed(row, 2),
                allowedForBrace=self._allowed(row, 3),
            )
            for row in range(self.table.rowCount())
        ]

    # -----------------------------------------------------------------
    # Next
    # -----------------------------------------------------------------

    def _on_next(self) -> None:
        sections = self.sections

        if not any(
            s.allowedForColumn or s.allowedForBeam or s.allowedForBrace
            for s in sections
        ):
            self.message.setText("Allow at least one section before continuing.")
            self.message.setVisible(True)
            return

        self.next_requested.emit(sections)
