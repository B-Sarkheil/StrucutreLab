"""Form widgets shared by the Auto Design pages (Field, check box, parsing helpers)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import AMBER, BLUE, CYAN, DANGER, INK_DEEP, INK_RAISED, PAPER, RULE, RULE_HI

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
    clearing an error never moves the fields. `add_side_widget` puts a
    widget (for example a Browse button) to the right of the line edit.
    """

    ERROR_HEIGHT = 15

    def __init__(self, label: str, placeholder: str, parent: QWidget | None = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel(label)
        self.label.setObjectName("fieldLabel")
        self.label.setWordWrap(True)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setProperty("invalid", False)
        self.edit.textChanged.connect(self.clear_error)

        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        self._row.addWidget(self.edit, 1)

        # Reserved space: the text is only emptied or filled.
        self.error = QLabel("")
        self.error.setObjectName("fieldError")
        self.error.setFixedHeight(self.ERROR_HEIGHT)

        layout.addWidget(self.label)
        layout.addLayout(self._row)
        layout.addWidget(self.error)

    def add_side_widget(self, widget: QWidget) -> None:
        """Add `widget` to the right of the line edit."""

        self._row.addWidget(widget)

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


class FancyCheckBox(QCheckBox):
    """Check box drawn in the app's look: dark rounded box, blue when checked
    with a white tick, amber border on hover / keyboard focus."""

    BOX = 22
    GAP = 12

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)

        font = self.font()
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        width = self.BOX + self.GAP + metrics.horizontalAdvance(self.text()) + 4
        height = max(self.BOX, metrics.height()) + 8

        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = float(self.BOX)
        box = QRectF(1.0, (self.height() - size) / 2 + 0.5, size - 1, size - 1)
        checked = self.isChecked()
        hot = self.underMouse() or self.hasFocus()

        shape = QPainterPath()
        shape.addRoundedRect(box, 6, 6)
        painter.fillPath(shape, QColor(BLUE if checked else INK_DEEP))

        if hot:
            border = QColor(AMBER)
        elif checked:
            border = QColor(CYAN)
        else:
            border = QColor(RULE_HI)

        painter.setPen(QPen(border, 1.5))
        painter.drawPath(shape)

        if checked:
            tick = QPen(QColor("#FFFFFF"), 2.5)
            tick.setCapStyle(Qt.PenCapStyle.RoundCap)
            tick.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(tick)
            painter.drawPolyline(
                [
                    QPointF(box.left() + box.width() * 0.24, box.top() + box.height() * 0.54),
                    QPointF(box.left() + box.width() * 0.43, box.top() + box.height() * 0.72),
                    QPointF(box.left() + box.width() * 0.77, box.top() + box.height() * 0.30),
                ]
            )

        painter.setFont(self.font())
        painter.setPen(QColor(PAPER))
        painter.drawText(
            QRectF(self.BOX + self.GAP, 0, self.width() - self.BOX - self.GAP, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )


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
