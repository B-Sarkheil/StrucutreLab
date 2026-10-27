"""Update window: shown by the launcher before it downloads a new version.

Flow (see `__main__.ask_update` and `bootstrap/launcher.py`):
  1. The user sees "installed version -> new version" and the question, and
     chooses *Update now* or *Later*. For a mandatory update the choices are
     *Update now* or *Exit*. The release notes are NOT shown here: they are
     shown once, after the update, in the "What's new" window.
  2. On *Update now* the same window switches to a busy view ("Updating...")
     and stays open while the launcher downloads the new version; the
     launcher closes it when it is done.

The window only reports the choice through the `chosen` signal; it does not
touch files. Look and building blocks: `sheet_dialog.py`.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .sheet_dialog import BusyBar, SheetDialog, make_required_pill
from .theme import AMBER, CYAN, FONT_TITLE, INK_DEEP


class FlowArrow(QWidget):
    """Arrow from the installed version to the new one: a line that fades
    from the warm color to the cyan, a round tail dot and a chevron head."""

    WIDTH = 52
    HEIGHT = 22

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setFixedSize(self.WIDTH, self.HEIGHT)

    def sizeHint(self) -> QSize:
        return QSize(self.WIDTH, self.HEIGHT)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cy = self.height() / 2
        tail = 5.0
        tip = self.width() - 4.0

        gradient = QLinearGradient(QPointF(tail, cy), QPointF(tip, cy))
        gradient.setColorAt(0.0, QColor(AMBER))
        gradient.setColorAt(1.0, QColor(CYAN))

        pen = QPen(QBrush(gradient), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        # tail dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(AMBER))
        painter.drawEllipse(QPointF(tail, cy), 2.8, 2.8)

        # shaft and chevron head
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(tail + 4, cy), QPointF(tip, cy))
        painter.drawPolyline(
            [
                QPointF(tip - 7, cy - 6.5),
                QPointF(tip, cy),
                QPointF(tip - 7, cy + 6.5),
            ]
        )


def make_version_chip(text: str, color: str) -> QLabel:
    """Rounded version box; every chip has the same width."""

    chip = QLabel(text)
    chip.setFixedWidth(170)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chip.setStyleSheet(
        f"QLabel {{ color: {color}; background: {INK_DEEP};"
        f" border: 1px solid {color}; border-radius: 11px;"
        f' padding: 3px 0px; font-family: "{FONT_TITLE}";'
        f" font-size: 10pt; font-weight: 600; }}"
    )

    return chip


class UpdatePromptDialog(SheetDialog):
    """Modal "Update available" window."""

    chosen = Signal(str)  # "update", "later" or "exit"

    def __init__(
        self,
        current: str,
        new: str,
        mandatory: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(
            "STRUCTURE LAB  ·  UPDATE", f"REV {new}", parent, on_top=True
        )

        self.setWindowTitle("Update available")

        self._new = new
        self._mandatory = mandatory
        self._answered = False

        self._title, self._subtitle = self.make_heading(
            "Update available",
            "A new version of Structure Lab has been released.",
        )

        self.body.addWidget(self._title)
        self.body.addWidget(self._subtitle)
        self.body.addSpacing(14)
        self.body.addWidget(self.make_divider())
        self.body.addSpacing(16)

        self._prompt_box = self._build_prompt(current, new, mandatory)
        self._busy_box = self._build_busy()
        self._busy_box.hide()

        self.body.addWidget(self._prompt_box)
        self.body.addWidget(self._busy_box)

    # -----------------------------------------------------------------
    # Views
    # -----------------------------------------------------------------

    def _build_prompt(
        self, current: str, new: str, mandatory: bool
    ) -> QWidget:
        box = QWidget()
        box.setObjectName("page")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        versions = QHBoxLayout()
        versions.setSpacing(10)

        # installed = warm, new = cyan
        versions.addWidget(make_version_chip(f"Installed  {current}", AMBER))
        versions.addWidget(FlowArrow())
        versions.addWidget(make_version_chip(f"New  {new}", CYAN))
        versions.addStretch(1)

        if mandatory:
            versions.addWidget(make_required_pill())

        layout.addLayout(versions)
        layout.addSpacing(18)

        question = QLabel(
            "This update is required to continue using Structure Lab."
            if mandatory
            else "Do you want to update now?"
        )
        question.setObjectName("sdQuestion")
        question.setWordWrap(True)
        layout.addWidget(question)

        layout.addSpacing(16)
        layout.addWidget(self.make_divider())
        layout.addSpacing(16)

        secondary = self.make_button("Exit" if mandatory else "Later")
        secondary.clicked.connect(self._on_secondary)

        update = self.make_button("Update now", primary=True)
        update.clicked.connect(self._on_update)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        buttons.addWidget(secondary)
        buttons.addWidget(update)
        layout.addLayout(buttons)

        update.setFocus()

        return box

    def _build_busy(self) -> QWidget:
        box = QWidget()
        box.setObjectName("page")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 8, 0, 22)
        layout.addWidget(BusyBar())

        return box

    def _show_busy(self) -> None:
        self._title.setText("Updating…")
        self._subtitle.setText(
            f"Downloading and checking version {self._new}. "
            "Structure Lab will start automatically."
        )

        self._prompt_box.hide()
        self._busy_box.show()

        # shrink around the same center
        center = self.geometry().center()
        self.adjustSize()
        frame = self.frameGeometry()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    # -----------------------------------------------------------------
    # Answers
    # -----------------------------------------------------------------

    def _answer(self, choice: str) -> bool:
        if self._answered:
            return False

        self._answered = True
        self.chosen.emit(choice)

        return True

    def _on_update(self) -> None:
        if self._answer("update"):
            self._show_busy()

    def _on_secondary(self) -> None:
        self._answer("exit" if self._mandatory else "later")
        self.accept()

    def reject(self) -> None:
        """Esc / Alt+F4: same as "Later". Ignored for a mandatory update and
        while the update is running."""

        if self._mandatory or self._answered:
            return

        self._answer("later")
        super().reject()
