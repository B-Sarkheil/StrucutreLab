"""Form widgets shared by the Auto Design pages (Field, parsing helpers)."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from src.ui.theme import DANGER, INK_RAISED, RULE

FORM_STYLE = f"""
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
    """Label + line edit + inline error message.

    The error label is always present with a fixed height, so showing or
    clearing an error never moves the fields.
    """

    ERROR_HEIGHT = 18

    def __init__(self, label: str, placeholder: str, parent: QWidget | None = None):
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

        # Reserved space: the text is only emptied or filled.
        self.error = QLabel("")
        self.error.setObjectName("fieldError")
        self.error.setFixedHeight(self.ERROR_HEIGHT)

        layout.addWidget(self.label)
        layout.addWidget(self.edit)
        layout.addWidget(self.error)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_error(self, message: str) -> None:
        self.error.setText(message)
        self._set_invalid(True)

    def clear_error(self) -> None:
        self.error.setText("")
        self._set_invalid(False)

    def _set_invalid(self, invalid: bool) -> None:
        self.edit.setProperty("invalid", invalid)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)


def parse_int(field: Field) -> int | None:
    """Positive integer from `field`, or None (with an inline error)."""

    text = field.text()

    if not text.isdigit() or int(text) <= 0:
        field.set_error("Enter a positive integer.")
        return None

    return int(text)


def parse_float(
    field: Field, *, minimum_exclusive: float = 0.0, maximum: float | None = None
) -> float | None:
    """Number from `field`, or None (with an inline error).

    With `maximum` the accepted range is 0..maximum; otherwise the value
    must be greater than `minimum_exclusive`.
    """

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
