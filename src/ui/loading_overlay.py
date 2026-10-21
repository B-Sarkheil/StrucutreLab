"""Application-wide loading overlay.

A translucent "ink" sheet over a page with a small drawing-sheet card in the
middle: a cyan comet spinner with an amber head, the sheet-corner marks used
by the tool cards, a title and an optional detail line.

Usage (any page, any plugin):

    overlay = LoadingOverlay(page)            # page is any QWidget
    overlay.show_loading("Reading model…", "Only needed when the file changes")
    overlay.set_text("Checking loads…")       # while it is visible
    overlay.hide_loading()

Flicker control: the overlay only appears if the work is still running after
`SHOW_DELAY_MS`, and once visible it stays at least `MIN_VISIBLE_MS`, so quick
checks never flash it. While visible it blocks mouse and keyboard input to the
page below it. It is a plain widget: no plugin logic.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QElapsedTimer,
    QEasingCurve,
    QEvent,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

from .theme import AMBER, CYAN, FONT_TITLE, INK_DEEP, INK_RAISED, PAPER, RULE_HI, STEEL
from .widgets import draw_corner_ticks, with_alpha


class LoadingOverlay(QWidget):
    SHOW_DELAY_MS = 200
    MIN_VISIBLE_MS = 450
    FADE_MS = 180
    SPIN_MS = 1100

    CARD_W = 300
    CARD_H = 188
    SPINNER_R = 27.0

    def __init__(self, parent: QWidget):
        super().__init__(parent)

        self._title = ""
        self._detail = ""
        self._opacity = 0.0
        self._angle = 0.0
        self._want = False
        self._prev_focus: QWidget | None = None

        self._visible_for = QElapsedTimer()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.BusyCursor)
        self.setAutoFillBackground(False)

        # Appear only when the work is not instant.
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.setInterval(self.SHOW_DELAY_MS)
        self._delay.timeout.connect(self._begin_show)

        self._fade = QVariantAnimation(self)
        self._fade.setDuration(self.FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._on_fade_value)
        self._fade.finished.connect(self._on_fade_finished)

        self._spin = QVariantAnimation(self)
        self._spin.setDuration(self.SPIN_MS)
        self._spin.setStartValue(0.0)
        self._spin.setEndValue(360.0)
        self._spin.setLoopCount(-1)
        self._spin.valueChanged.connect(self._on_spin_value)

        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.hide()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def show_loading(self, title: str, detail: str = "") -> None:
        """Request the overlay; it fades in after a short delay if still needed."""
        self._title = title
        self._detail = detail
        self._want = True
        self.update()

        if self.isVisible():
            self._fade_to(1.0)  # also cancels a fade-out that is under way
        elif not self._delay.isActive():
            self._delay.start()

    def set_text(self, title: str, detail: str = "") -> None:
        """Change the text while the overlay is (or is about to be) shown."""
        self._title = title
        self._detail = detail
        self.update()

    def hide_loading(self) -> None:
        """Release the overlay; it fades out (after the minimum visible time)."""
        self._want = False
        self._delay.stop()
        if not self.isVisible():
            return

        remaining = self.MIN_VISIBLE_MS - self._visible_for.elapsed()
        if remaining > 0:
            QTimer.singleShot(remaining, self._finish_hide)
        else:
            self._finish_hide()

    # -----------------------------------------------------------------
    # Show / hide mechanics
    # -----------------------------------------------------------------

    def _begin_show(self) -> None:
        if not self._want:
            return
        self.setGeometry(self.parentWidget().rect())
        self._opacity = 0.0
        self._visible_for.start()
        self.show()
        self.raise_()

        focused = QApplication.focusWidget()
        self._prev_focus = focused if focused is not self else None
        self.setFocus(Qt.FocusReason.OtherFocusReason)  # keyboard input stops here

        self._spin.start()
        self._fade_to(1.0)

    def _finish_hide(self) -> None:
        if self._want or not self.isVisible():
            return  # asked again in the meantime
        self._fade_to(0.0)

    def _fade_to(self, target: float) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._opacity)
        self._fade.setEndValue(target)
        self._fade.start()

    def _on_fade_value(self, value) -> None:
        self._opacity = float(value)
        self.update()

    def _on_fade_finished(self) -> None:
        if self._opacity > 0.0 or self._want:
            return
        self._spin.stop()
        self.hide()
        previous, self._prev_focus = self._prev_focus, None
        if previous is not None:
            try:
                previous.setFocus(Qt.FocusReason.OtherFocusReason)
            except RuntimeError:  # the widget was deleted meanwhile
                pass

    def _on_spin_value(self, value) -> None:
        self._angle = float(value)
        self.update()

    # -----------------------------------------------------------------
    # Keep covering the parent; swallow input while visible
    # -----------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return False

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        event.accept()

    # -----------------------------------------------------------------
    # Painting
    # -----------------------------------------------------------------

    def paintEvent(self, event):
        a = self._opacity
        if a <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # dimmed page below
        painter.fillRect(self.rect(), with_alpha(INK_DEEP, int(175 * a)))

        # card
        card = QRectF(
            (self.width() - self.CARD_W) / 2,
            (self.height() - self.CARD_H) / 2,
            self.CARD_W,
            self.CARD_H,
        )
        painter.setOpacity(a)

        path = QPainterPath()
        path.addRoundedRect(card, 14, 14)
        painter.fillPath(path, QBrush(QColor(INK_RAISED)))
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawPath(path)
        draw_corner_ticks(painter, card, QColor(AMBER), inset=8.0, length=10.0)

        # spinner
        center = QPointF(card.center().x(), card.top() + 66)
        r = self.SPINNER_R

        track = QPen(with_alpha(CYAN, 38), 4)
        painter.setPen(track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, r, r)

        painter.save()
        painter.translate(center)
        painter.rotate(self._angle)

        gradient = QConicalGradient(QPointF(0, 0), 0)
        gradient.setColorAt(0.0, QColor(CYAN))
        gradient.setColorAt(0.65, with_alpha(CYAN, 0))
        gradient.setColorAt(1.0, with_alpha(CYAN, 0))
        comet = QPen(QBrush(gradient), 4)
        painter.setPen(comet)
        painter.drawEllipse(QPointF(0, 0), r, r)

        # amber head at the tip of the comet
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(AMBER, 70))
        painter.drawEllipse(QPointF(r, 0), 8.5, 8.5)
        painter.setBrush(QColor(AMBER))
        painter.drawEllipse(QPointF(r, 0), 4.5, 4.5)
        painter.restore()

        # text
        title_font = QFont(FONT_TITLE)
        title_font.setPointSizeF(11.5)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(PAPER))
        title_rect = QRectF(card.left() + 16, card.top() + 112, card.width() - 32, 26)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self._title)

        if self._detail:
            detail_font = QFont(self.font())
            detail_font.setPointSizeF(9)
            painter.setFont(detail_font)
            painter.setPen(QColor(STEEL))
            detail_rect = QRectF(card.left() + 16, card.top() + 140, card.width() - 32, 34)
            painter.drawText(
                detail_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                self._detail,
            )

        painter.end()
