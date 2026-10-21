"""Small vector icons for the SLD to SAP page, drawn in code (no image files needed)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

_SCALE = 2  # draw at 2x so the icons stay sharp on high-DPI screens


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    """Transparent pixmap and a painter working on a 24 x 24 design grid."""
    pixmap = QPixmap(size * _SCALE, size * _SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(_SCALE)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.scale(size / 24, size / 24)
    return pixmap, painter


def _pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def document_icon(label: str, color: str = "#5CC8F0", size: int = 22) -> QIcon:
    """A sheet of paper with a folded corner and a short label ("LSP", "PDF")."""
    pixmap, p = _canvas(size)
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)

    page = QPainterPath()
    page.moveTo(5, 2)
    page.lineTo(14, 2)
    page.lineTo(19, 7)
    page.lineTo(19, 22)
    page.lineTo(5, 22)
    page.closeSubpath()
    p.drawPath(page)
    p.drawPolyline([QPointF(14, 2), QPointF(14, 7), QPointF(19, 7)])

    font = QFont("Segoe UI")
    font.setPixelSize(7)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(5, 10, 14, 10), Qt.AlignmentFlag.AlignCenter, label)
    p.end()
    return QIcon(pixmap)


def convert_icon(color: str = "#FFFFFF", disabled_color: str = "#8794A2", size: int = 28) -> QIcon:
    """Two opposite arrows (conversion); a normal and a disabled variant."""
    icon = QIcon()
    for mode, tone in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, disabled_color)):
        pixmap, p = _canvas(size)
        p.setPen(_pen(tone, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # top arrow, pointing right
        p.drawLine(QPointF(4, 8), QPointF(20, 8))
        p.drawPolyline([QPointF(16, 4), QPointF(20, 8), QPointF(16, 12)])
        # bottom arrow, pointing left
        p.drawLine(QPointF(20, 16), QPointF(4, 16))
        p.drawPolyline([QPointF(8, 12), QPointF(4, 16), QPointF(8, 20)])
        p.end()
        icon.addPixmap(pixmap, mode)
    return icon


def message_pixmap(color: str = "#48B8FF", size: int = 28) -> QPixmap:
    """Speech bubble with three dots: the page "talking" to the user."""
    pixmap, p = _canvas(size)

    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(3, 3.5, 18, 13.5), 4, 4)
    tail = QPainterPath()
    tail.moveTo(8, 16.5)
    tail.lineTo(8, 21)
    tail.lineTo(13, 16.5)
    tail.closeSubpath()
    shape = bubble.united(tail)

    fill = QColor(color)
    fill.setAlpha(45)
    p.setPen(_pen(color, 1.7))
    p.setBrush(fill)
    p.drawPath(shape)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    for x in (8, 12, 16):
        p.drawEllipse(QPointF(x, 10.2), 1.4, 1.4)
    p.end()
    return pixmap
