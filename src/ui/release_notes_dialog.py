"""Release notes window, shown once after the app was updated.

The user reads the notes and presses "Got it"; the caller then remembers the
version as seen. Pure display: it knows nothing about where the notes come
from (see `core/release_notes.py`). Look and building blocks: `sheet_dialog.py`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ..core.release_notes import ReleaseNote
from .sheet_dialog import SheetDialog


class ReleaseNotesDialog(SheetDialog):
    """Modal "What's new" window with a single "Got it" button."""

    def __init__(
        self,
        notes: list[ReleaseNote],
        version: str,
        parent: QWidget | None = None,
    ):
        super().__init__("STRUCTURE LAB  ·  WHAT'S NEW", f"REV {version}", parent)

        self.setWindowTitle("What's new")

        title, subtitle = self.make_heading(
            "What's new", f"Structure Lab was updated to version {version}."
        )

        button = self.make_button("Got it", primary=True)
        button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button)

        self.body.addWidget(title)
        self.body.addWidget(subtitle)
        self.body.addSpacing(14)
        self.body.addWidget(self.make_divider())
        self.body.addSpacing(12)
        self.body.addWidget(self.make_notes_area(notes))
        self.body.addSpacing(12)
        self.body.addWidget(self.make_divider())
        self.body.addSpacing(16)
        self.body.addLayout(buttons)

        button.setFocus()
