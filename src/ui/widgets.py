"""Reusable custom-painted widgets for the Structure Lab shell."""

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .theme import CYAN, HERO_BG, LOGO_PNG, RULE_HI


def mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    """Linear blend from color `a` (t=0) to color `b` (t=1)."""

    ca = QColor(a)
    cb = QColor(b)
    t = max(0.0, min(1.0, t))

    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
        round(ca.alpha() + (cb.alpha() - ca.alpha()) * t),
    )


def with_alpha(color: str | QColor, alpha: int) -> QColor:
    """Return `color` with the given alpha (0-255)."""

    result = QColor(color)
    result.setAlpha(alpha)

    return result


def draw_corner_ticks(
    painter: QPainter,
    rect: QRectF,
    color: QColor,
    inset: float = 7.0,
    length: float = 9.0,
) -> None:
    """Draw L-shaped sheet-corner marks just inside `rect`."""

    pen = QPen(color, 1.5)
    pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    painter.setPen(pen)

    left = rect.left() + inset
    right = rect.right() - inset
    top = rect.top() + inset
    bottom = rect.bottom() - inset

    for x, y, dx, dy in (
        (left, top, 1, 1),
        (right, top, -1, 1),
        (left, bottom, 1, -1),
        (right, bottom, -1, -1),
    ):
        painter.drawLine(QPointF(x, y), QPointF(x + dx * length, y))
        painter.drawLine(QPointF(x, y), QPointF(x, y + dy * length))


class ClickableFrame(QFrame):
    """Frame that emits `clicked` and animates a hover amount (0..1).

    Subclasses paint themselves using `emphasis`, which is 1.0 while the
    frame has keyboard focus and follows the animated hover otherwise.
    """

    clicked = Signal()

    HOVER_MS = 140

    def __init__(self, parent=None):
        super().__init__(parent)

        self._hover = 0.0

        self._hover_animation = QVariantAnimation(self)
        self._hover_animation.setDuration(self.HOVER_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.valueChanged.connect(self._on_hover_value)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    @property
    def emphasis(self) -> float:
        """How strongly the frame is highlighted (0..1)."""

        return 1.0 if self.hasFocus() else self._hover

    def _on_hover_value(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _animate_hover(self, target: float) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.clicked.emit()
            event.accept()
            return

        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        """Emit `clicked` when the left button is released inside."""

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)

class HeroBanner(QWidget):
    """Home banner drawn like a drawing sheet.

    Blueprint grid, the app logo on the right and the app title on the
    left. The logo fades in once when the banner is first shown; this is
    the only unprompted motion in the app.
    """

    HEIGHT = 168
    FADE_MS = 900

    LOGO_SIZE = 124
    LOGO_MARGIN_RIGHT = 44

    GRID_STEP = 24
    GRID_MAJOR = 4

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)

        self.setFixedHeight(self.HEIGHT)

        self._logo = QPixmap(str(LOGO_PNG))
        self._progress = 0.0
        self._played = False

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(self.FADE_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 0, 32, 0)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("heroTitle")

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("heroSubtitle")
        subtitle_label.setWordWrap(True)
        subtitle_label.setMaximumWidth(330)

        layout.addStretch()
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch()

    def _on_progress(self, value) -> None:
        self._progress = float(value)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)

        if not self._played:
            self._played = True
            self._progress = 0.0
            self._animation.start()

    # -----------------------------------------------------------------
    # Painting
    # -----------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        sheet = QPainterPath()
        sheet.addRoundedRect(rect, 14, 14)

        painter.setClipPath(sheet)
        painter.fillPath(sheet, QBrush(QColor(HERO_BG)))

        self._paint_grid(painter, rect)
        self._paint_logo(painter)

        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawPath(sheet)

    def _paint_grid(self, painter: QPainter, rect: QRectF) -> None:
        minor = QPen(with_alpha(CYAN, 14), 1)
        major = QPen(with_alpha(CYAN, 30), 1)

        step = self.GRID_STEP

        for index, x in enumerate(range(0, int(rect.right()) + step, step)):
            painter.setPen(major if index % self.GRID_MAJOR == 0 else minor)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        for index, y in enumerate(range(0, int(rect.bottom()) + step, step)):
            painter.setPen(major if index % self.GRID_MAJOR == 0 else minor)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def _paint_logo(self, painter: QPainter) -> None:
        """Draw logo.png on the right side, vertically centered."""

        if self._logo.isNull():
            return

        size = float(self.LOGO_SIZE)
        target = QRectF(
            self.width() - size - self.LOGO_MARGIN_RIGHT,
            (self.height() - size) / 2,
            size,
            size,
        )

        painter.setOpacity(self._progress)
        painter.drawPixmap(target, self._logo, QRectF(self._logo.rect()))
        painter.setOpacity(1.0)

class FadeStackedWidget(QStackedWidget):
    """QStackedWidget that fades the incoming page in (answers a click)."""

    FADE_MS = 160

    def __init__(self, parent=None):
        super().__init__(parent)

        self._fade = None

    def fade_to(self, page: QWidget) -> None:
        """Show `page`, fading it in unless it is already current."""

        self._finish_fade()

        if page is self.currentWidget():
            return

        self.setCurrentWidget(page)

        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(self.FADE_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(self._finish_fade)

        self._fade = (page, animation)
        animation.start()

    def _finish_fade(self) -> None:
        if self._fade is None:
            return

        page, animation = self._fade
        self._fade = None

        animation.stop()
        animation.deleteLater()
        page.setGraphicsEffect(None)
