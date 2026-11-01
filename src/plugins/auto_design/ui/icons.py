"""Small vector icons of the Auto Design pages, drawn in code (no image files)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from src.ui.theme import STEEL_DIM


def _paint_helix(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """DNA double helix: two crossing strands with rungs."""

    cx = rect.center().x()
    amplitude = rect.width() * 0.34
    top = rect.top() + rect.height() * 0.06
    height = rect.height() * 0.88
    turns = 1.5
    steps = 48

    def x_at(t: float, phase: float) -> float:
        return cx + amplitude * math.sin(2 * math.pi * turns * t + phase)

    # rungs where the strands are furthest apart
    rung = QColor(color)
    rung.setAlpha(150)
    rung_pen = QPen(rung, 1.2)
    rung_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(rung_pen)

    for k in range(3):
        t = (0.5 + k) / (2 * turns)
        y = top + height * t
        painter.drawLine(QPointF(x_at(t, 0.0), y), QPointF(x_at(t, math.pi), y))

    # the two strands
    strand_pen = QPen(color, 2.0)
    strand_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    strand_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(strand_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    for phase in (0.0, math.pi):
        path = QPainterPath()

        for i in range(steps + 1):
            t = i / steps
            point = QPointF(x_at(t, phase), top + height * t)

            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        painter.drawPath(path)


def _paint_play(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Filled play triangle with softly rounded corners."""

    path = QPainterPath()
    path.moveTo(rect.left(), rect.top())
    path.lineTo(rect.right(), rect.center().y())
    path.lineTo(rect.left(), rect.bottom())
    path.closeSubpath()

    pen = QPen(color, 2.0)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(color)
    painter.drawPath(path)


def evolution_run_icon(
    size: int = 30, color: str = "#FFFFFF", disabled_color: str = STEEL_DIM
) -> QIcon:
    """"Run the evolution" icon: a DNA helix followed by a play triangle.

    The pixmap is about 1.4 x `size` wide and `size` high: use an icon size
    of QSize(round(size * 1.4), size).
    """

    icon = QIcon()
    scale = 2  # draw at 2x so it stays sharp on high-DPI screens
    width = int(round(size * 1.4))

    for mode, tone in (
        (QIcon.Mode.Normal, color),
        (QIcon.Mode.Disabled, disabled_color),
    ):
        pixmap = QPixmap(width * scale, size * scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(scale)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        _paint_helix(painter, QRectF(0, 0, size * 0.62, size), QColor(tone))
        _paint_play(
            painter,
            QRectF(size * 0.80, size * 0.24, size * 0.50, size * 0.52),
            QColor(tone),
        )

        painter.end()
        icon.addPixmap(pixmap, mode)

    return icon
