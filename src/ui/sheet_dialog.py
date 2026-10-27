"""Shared base of the small modal windows of the shell ("What's new",
"Update available").

Same "structural drawing sheet" look as the About page: it reuses
`SheetCard` (blueprint grid, title-block labels, amber corner marks) and the
color tokens of `theme.py`. Part of the shell (not a plugin); pure display.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.release_notes import NoteItem, ReleaseNote
from .about_page import SheetCard
from .theme import (
    AMBER,
    CYAN,
    DANGER,
    FONT_TITLE,
    INK_DEEP,
    PAPER,
    RULE_HI,
    STEEL,
)

# Colors of the three kinds of release-note items (text, border and a
# tinted fill are derived from one color).
GREEN = "#3DDC97"
SKY = "#5AA9FF"

# tag -> (pill text, color)
TAG_STYLES: dict[str, tuple[str, str]] = {
    "new": ("NEW", GREEN),
    "improved": ("IMPROVED", SKY),
    "fixed": ("FIXED", AMBER),
}

DIALOG_STYLE = f"""
    QDialog#sheetDialog {{
        background: transparent;
    }}

    /* the scroll area must not paint the global window color over the sheet */
    QWidget#qt_scrollarea_viewport {{
        background: transparent;
    }}

    QLabel#sdTitle {{
        color: {PAPER};
        font-family: "{FONT_TITLE}";
        font-size: 20pt;
        font-weight: 600;
    }}

    QLabel#sdSubtitle {{
        color: {STEEL};
        font-size: 10pt;
    }}

    QLabel#sdText {{
        color: {PAPER};
        font-size: 10pt;
    }}

    QLabel#sdQuestion {{
        color: {PAPER};
        font-size: 12pt;
        font-weight: 700;
    }}

    QFrame#sdNoteCard {{
        background: rgba(6, 13, 25, 150);
        border: 1px solid {RULE_HI};
        border-radius: 12px;
    }}

    QLabel#sdNoteVersion {{
        color: {CYAN};
        font-family: "{FONT_TITLE}";
        font-size: 12pt;
        font-weight: 600;
    }}

    QLabel#sdNoteDate {{
        color: {STEEL};
        font-size: 9pt;
    }}

    QLabel#sdNoteTitle {{
        color: {PAPER};
        font-family: "{FONT_TITLE}";
        font-size: 11pt;
        font-weight: 600;
    }}
"""


def rgba(color: str, alpha: int) -> str:
    """'#RRGGBB' + alpha 0-255 -> 'rgba(r, g, b, a)' for a style sheet."""
    c = QColor(color)

    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def make_pill(text: str, color: str) -> QLabel:
    """Small rounded tag: colored text and border on a tint of the same color."""

    pill = QLabel(text)
    pill.setFixedSize(78, 20)
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill.setStyleSheet(
        f"QLabel {{ color: {color}; background: {rgba(color, 38)};"
        f" border: 1px solid {color}; border-radius: 9px;"
        f" font-size: 7.5pt; font-weight: 600; }}"
    )

    return pill


def make_required_pill() -> QLabel:
    return make_pill("REQUIRED", DANGER)


class BusyBar(QWidget):
    """Thin indeterminate progress bar: a cyan segment sliding along a track.

    Drawn in code because a QSS-styled QProgressBar loses its busy animation.
    """

    HEIGHT = 8
    CYCLE_MS = 1400

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setFixedHeight(self.HEIGHT)
        self._t = 0.0

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(self.CYCLE_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)
        self._animation.valueChanged.connect(self._on_tick)

    def _on_tick(self, value) -> None:
        self._t = float(value)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._animation.start()

    def hideEvent(self, event):
        self._animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2

        track = QPainterPath()
        track.addRoundedRect(rect, radius, radius)
        painter.fillPath(track, QBrush(QColor(INK_DEEP)))

        painter.setClipPath(track)

        segment = rect.width() * 0.3
        x = rect.left() - segment + (rect.width() + segment) * self._t
        head = QPainterPath()
        head.addRoundedRect(
            QRectF(x, rect.top(), segment, rect.height()), radius, radius
        )
        painter.fillPath(head, QBrush(QColor(CYAN)))

        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawPath(track)


class SheetDialog(QDialog):
    """Frameless modal window drawn as a drawing sheet.

    Subclasses fill ``self.body`` (a QVBoxLayout inside the card) using the
    ``make_*`` helpers."""

    WIDTH = 580
    MARGIN = 32
    MAX_NOTES_HEIGHT = 300
    SCROLLBAR_GUTTER = 14

    def __init__(
        self,
        label_left: str,
        label_right: str,
        parent: QWidget | None = None,
        on_top: bool = False,
    ):
        super().__init__(parent)

        flags = Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint

        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setObjectName("sheetDialog")
        self.setModal(True)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(self.WIDTH)

        self._notes_scroll: QScrollArea | None = None
        self._notes_layout: QVBoxLayout | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = SheetCard(label_left, label_right)
        outer.addWidget(self.card)

        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(self.MARGIN, 40, self.MARGIN, 24)
        self.body.setSpacing(0)

    # -----------------------------------------------------------------
    # Building blocks
    # -----------------------------------------------------------------

    @staticmethod
    def make_heading(title: str, subtitle: str) -> tuple[QLabel, QLabel]:
        title_label = QLabel(title)
        title_label.setObjectName("sdTitle")

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("sdSubtitle")
        subtitle_label.setWordWrap(True)

        return title_label, subtitle_label

    @staticmethod
    def make_divider() -> QFrame:
        divider = QFrame()
        divider.setObjectName("aboutDivider")
        divider.setFixedHeight(1)

        return divider

    @staticmethod
    def make_button(text: str, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumWidth(120)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

        if primary:
            button.setObjectName("primaryButton")
            button.setDefault(True)

        return button

    def make_notes_area(self, notes: list[ReleaseNote]) -> QScrollArea:
        """Scrollable list of release notes, one framed card per version;
        grows with the content up to MAX_NOTES_HEIGHT (the height is fitted
        when the window is shown)."""

        inner = QWidget()
        inner.setObjectName("page")

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(14)

        for note in notes:
            layout.addWidget(self._note_block(note))

        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidget(inner)
        scroll.setFixedHeight(self.MAX_NOTES_HEIGHT)

        self._notes_scroll = scroll
        self._notes_layout = layout

        return scroll

    def _note_block(self, note: ReleaseNote) -> QWidget:
        """One version: a framed region titled with its version and date."""

        card = QFrame()
        card.setObjectName("sdNoteCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)

        version = QLabel(f"Version {note.version}")
        version.setObjectName("sdNoteVersion")
        head.addWidget(version)
        head.addStretch(1)

        if note.date:
            date = QLabel(note.date)
            date.setObjectName("sdNoteDate")
            head.addWidget(date)

        layout.addLayout(head)
        layout.addWidget(self.make_divider())

        if note.title:
            title = QLabel(note.title)
            title.setObjectName("sdNoteTitle")
            title.setWordWrap(True)
            layout.addWidget(title)

        for item in note.items:
            layout.addLayout(self._item_row(item))

        return card

    @staticmethod
    def _item_row(item: NoteItem) -> QHBoxLayout:
        text, color = TAG_STYLES.get(item.tag, TAG_STYLES["improved"])

        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(item.text)
        label.setObjectName("sdText")
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        row.addWidget(make_pill(text, color), 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(label, 1)

        return row

    # -----------------------------------------------------------------
    # Sizing and dragging
    # -----------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_notes_area()

    def _fit_notes_area(self) -> None:
        if self._notes_scroll is None or self._notes_layout is None:
            return

        width = self.WIDTH - 2 * self.MARGIN - self.SCROLLBAR_GUTTER
        self._notes_layout.activate()

        wanted = (
            self._notes_layout.heightForWidth(width)
            if self._notes_layout.hasHeightForWidth()
            else -1
        )

        if wanted <= 0:
            wanted = self._notes_layout.sizeHint().height()

        self._notes_scroll.setFixedHeight(
            min(max(wanted, 60), self.MAX_NOTES_HEIGHT)
        )
        self.adjustSize()

    def mousePressEvent(self, event):
        """Frameless window: drag it by any free area."""

        handle = self.windowHandle()

        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return

        super().mousePressEvent(event)
