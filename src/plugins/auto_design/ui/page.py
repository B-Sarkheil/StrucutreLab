"""Auto Design - step 1: choose the SAP2000 reference file.

The page only asks for the .sdb file. The file can be dropped on the
big drop area or picked with the file dialog. On Next the path is
validated and the page emits `next_requested` with the path (str).

The SAP2000 logo is read from `src/ui/assets/icons/sap.png` (`sap.ico`
and `sao.ico` are accepted too, in that order). If none of them exists,
a plain "SAP" lettering is drawn instead, so the page never breaks.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import (
    AMBER,
    CYAN,
    DANGER,
    FONT_TITLE,
    HERO_BG,
    ICONS_DIR,
    INK_HI,
    INK_RAISED,
    PAPER,
    RULE,
    RULE_HI,
    STEEL,
    STEEL_DIM,
)
from src.ui.widgets import ClickableFrame, arrow_icon, draw_corner_ticks, mix, with_alpha

SAP_ICON_NAMES = ("sap.png", "sap.ico", "sao.ico")

PAGE_STYLE = f"""
    QLabel#dropTitle {{
        background: transparent;
        color: {PAPER};
        font-family: "{FONT_TITLE}";
        font-size: 17pt;
        font-weight: 600;
    }}
    QLabel#dropHint {{
        background: transparent;
        color: {STEEL};
        font-size: 10pt;
    }}
    QLabel#dropDetail {{
        background: transparent;
        color: {STEEL_DIM};
        font-size: 9pt;
    }}
    QLabel#dropChip {{
        background: transparent;
        color: {STEEL_DIM};
        border: 1px solid {RULE};
        border-radius: 4px;
        padding: 1px 8px;
        font-size: 8.5pt;
    }}
    QLabel#pageError {{
        background: transparent;
        color: {DANGER};
        font-size: 9.5pt;
    }}
"""


def _format_size(size: int) -> str:
    value = float(size)

    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} GB"


class IconBadge(QWidget):
    """SAP2000 logo on a round badge with a soft glow."""

    SIZE = 124
    ICON = 68

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._active = 0.0
        self._pixmap = self._load_icon()

    @classmethod
    def _load_icon(cls):
        for name in SAP_ICON_NAMES:
            path = ICONS_DIR / name

            if not path.is_file():
                continue

            if path.suffix.lower() == ".ico":
                pixmap = QIcon(str(path)).pixmap(QSize(256, 256))
            else:
                pixmap = QPixmap(str(path))

            if not pixmap.isNull():
                return pixmap

        return None

    def set_active(self, value: float) -> None:
        self._active = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        center = QPointF(self.width() / 2, self.height() / 2)
        radius = self.width() / 2

        glow = QRadialGradient(center, radius)
        glow.setColorAt(0.0, with_alpha(CYAN, int(45 + 60 * self._active)))
        glow.setColorAt(1.0, with_alpha(CYAN, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, radius, radius)

        ring = QPen(with_alpha(CYAN, 80), 1)
        ring.setDashPattern([2.0, 4.0])
        painter.setPen(ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius * 0.92, radius * 0.92)

        disc = radius * 0.72
        painter.setPen(QPen(mix(RULE_HI, AMBER, self._active), 1.5))
        painter.setBrush(QBrush(QColor(HERO_BG)))
        painter.drawEllipse(center, disc, disc)

        if self._pixmap is not None:
            # Fit inside the ICON x ICON box, keeping the aspect ratio.
            box = float(self.ICON)
            ratio = self._pixmap.width() / self._pixmap.height()
            width = box if ratio >= 1 else box * ratio
            height = box / ratio if ratio >= 1 else box
            target = QRectF(
                center.x() - width / 2, center.y() - height / 2, width, height
            )
            painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
            return

        # Fallback when sap.ico is not in the icons folder.
        font = QFont(FONT_TITLE)
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(CYAN))
        painter.drawText(
            QRectF(0, 0, self.width(), self.height()),
            Qt.AlignmentFlag.AlignCenter,
            "SAP",
        )


class DropZone(ClickableFrame):
    """Big area: drop a .sdb file here or click to browse.

    Emits `clicked` (open the file dialog) and `file_dropped(path)`.
    """

    file_dropped = Signal(str)

    RADIUS = 16
    PATH_WIDTH = 560
    GRID_STEP = 24
    GRID_MAJOR = 4

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("dropZone")
        self.setMinimumHeight(320)
        self.setAcceptDrops(True)

        self._dragging = False
        self._has_file = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.badge = IconBadge()

        self.title = QLabel()
        self.title.setObjectName("dropTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hint = QLabel()
        self.hint.setObjectName("dropHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setMaximumWidth(self.PATH_WIDTH + 40)

        self.detail = QLabel()
        self.detail.setObjectName("dropDetail")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.browse_button = QPushButton("Browse files…")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setMinimumSize(150, 38)
        self.browse_button.clicked.connect(self.clicked.emit)

        self.chip = QLabel("SAP2000 v23  *.sdb")
        self.chip.setObjectName("dropChip")

        for widget in (self.badge, self.title, self.hint, self.detail):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(self.title, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(6)
        layout.addWidget(self.hint, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(4)
        layout.addWidget(self.detail, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(14)
        layout.addWidget(self.browse_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignHCenter)

        self.set_file(None)

    # -----------------------------------------------------------------
    # State
    # -----------------------------------------------------------------

    def set_file(self, path: str | None) -> None:
        """Show the empty prompt (None) or the chosen file."""

        self._has_file = path is not None

        if path is None:
            self.title.setText("Select your SAP2000 model")
            self.hint.setText(
                "Drag and drop a .sdb file here, or click anywhere in this area to "
                "browse. This is the reference model Auto Design opens to read its "
                "sections and run the analyses."
            )
            self.hint.setToolTip("")
            self.detail.setText("")
            self.detail.setVisible(False)
            self.chip.setVisible(True)
            self.browse_button.setText("Browse files…")
        else:
            file = Path(path)
            metrics = QFontMetrics(self.hint.font())
            folder = metrics.elidedText(
                str(file.parent), Qt.TextElideMode.ElideMiddle, self.PATH_WIDTH
            )

            try:
                size = _format_size(file.stat().st_size)
            except OSError:
                size = "unknown size"

            self.title.setText(file.name)
            self.hint.setText(folder)
            self.hint.setToolTip(str(file))
            self.detail.setText(f"{size}  ·  drop another file to replace it")
            self.detail.setVisible(True)
            self.chip.setVisible(False)
            self.browse_button.setText("Change file…")

        self._sync_badge()
        self.update()

    def _set_dragging(self, dragging: bool) -> None:
        self._dragging = dragging
        self._sync_badge()
        self.update()

    def _level(self) -> float:
        return max(self.emphasis, 1.0 if self._dragging else 0.0)

    def _sync_badge(self) -> None:
        self.badge.set_active(self._level())

    def _on_hover_value(self, value) -> None:
        super()._on_hover_value(value)
        self._sync_badge()

    # -----------------------------------------------------------------
    # Drag and drop
    # -----------------------------------------------------------------

    @staticmethod
    def _local_file(mime) -> str | None:
        if not mime.hasUrls():
            return None

        urls = [url for url in mime.urls() if url.isLocalFile()]

        if len(urls) != 1:
            return None

        return urls[0].toLocalFile()

    def dragEnterEvent(self, event):
        if self._local_file(event.mimeData()) is None:
            event.ignore()
            return

        self._set_dragging(True)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_dragging(False)
        event.accept()

    def dropEvent(self, event):
        path = self._local_file(event.mimeData())
        self._set_dragging(False)

        if path is None:
            event.ignore()
            return

        event.acceptProposedAction()
        self.file_dropped.emit(str(Path(path)))

    # -----------------------------------------------------------------
    # Painting
    # -----------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self._level()

        shape = QPainterPath()
        shape.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.fillPath(shape, QBrush(mix(INK_RAISED, INK_HI, t)))

        painter.save()
        painter.setClipPath(shape)
        self._paint_grid(painter, rect)
        painter.restore()

        pen = QPen(mix(RULE_HI, AMBER, t), 1.5)

        if not self._has_file:
            pen.setDashPattern([6.0, 4.0])

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawPath(shape)

        tick = mix(CYAN if self._has_file else RULE_HI, AMBER, t)
        draw_corner_ticks(painter, rect, tick, inset=12.0, length=12.0)

    def _paint_grid(self, painter: QPainter, rect: QRectF) -> None:
        minor = QPen(with_alpha(CYAN, 9), 1)
        major = QPen(with_alpha(CYAN, 20), 1)
        step = self.GRID_STEP

        for index, x in enumerate(range(0, int(rect.right()) + step, step)):
            painter.setPen(major if index % self.GRID_MAJOR == 0 else minor)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        for index, y in enumerate(range(0, int(rect.bottom()) + step, step)):
            painter.setPen(major if index % self.GRID_MAJOR == 0 else minor)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))


class AutoDesignPage(QWidget):
    """First page of the Auto Design wizard: the SAP2000 reference file."""

    next_requested = Signal(str)  # path of the .sdb file

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")
        self.setStyleSheet(PAGE_STYLE)

        self._path: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(0)

        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Choose the SAP2000 reference model to start from.")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(20)

        self.zone = DropZone()
        self.zone.clicked.connect(self._browse)
        self.zone.file_dropped.connect(self._accept_path)
        layout.addWidget(self.zone, 1)

        self.error = QLabel("")
        self.error.setObjectName("pageError")
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error.setWordWrap(True)
        self.error.setFixedHeight(28)

        layout.addSpacing(6)
        layout.addWidget(self.error)
        layout.addSpacing(6)

        self.next_button = QPushButton("Next")
        self.next_button.setIcon(arrow_icon("right"))
        self.next_button.setIconSize(QSize(32, 24))
        # Right-to-left layout puts the icon after the text.
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_button.setObjectName("primaryButton")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setMinimumSize(150, 42)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._on_next)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

    @property
    def sap_path(self) -> str:
        """Currently chosen file ('' when nothing is chosen)."""

        return self._path or ""

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    def _browse(self) -> None:
        start = str(Path(self._path).parent) if self._path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SAP2000 reference file",
            start,
            "SAP2000 files (*.sdb);;All files (*)",
        )

        if path:
            self._accept_path(str(Path(path)))

    def _accept_path(self, path: str) -> None:
        """Take a file from the dialog or from a drop (extension is checked)."""

        if Path(path).suffix.lower() != ".sdb":
            self._show_error("Only SAP2000 model files (.sdb) are supported.")
            return

        self._path = path
        self.zone.set_file(path)
        self._show_error("")

    def _show_error(self, message: str) -> None:
        self.error.setText(message)

    def _on_next(self) -> None:
        if not self._path:
            self._show_error("Select the SAP2000 reference file.")
            return

        if not Path(self._path).is_file():
            self._show_error("File not found.")
            return

        self._show_error("")
        self.next_requested.emit(self._path)
