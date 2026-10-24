"""About page: logo emblem, version, copyright and support contact.

Part of the shell (not a plugin). It is opened from the About card at the
bottom of the sidebar and is created lazily like every plugin page.
Visual language: the same "structural drawing sheet" as the Home page.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QDesktopServices,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import version as version_info
from .theme import (
    AMBER,
    CYAN,
    FONT_TITLE,
    HERO_BG,
    INK_DEEP,
    INK_RAISED,
    LOGO_PNG,
    PAPER,
    RULE,
    RULE_HI,
    STEEL,
    STEEL_DIM,
)
from .widgets import ClickableFrame, draw_corner_ticks, mix, with_alpha

COMPANY = "Namvaran"
COPYRIGHT_YEAR = 2026
SUPPORT_EMAIL = "B.Sarkheil@namvaran.ir"
SUPPORT_PHONE = "+989355121169"

# Release date of the current version: `__release_date__` in src/version.py.
RELEASE_DATE = getattr(version_info, "__release_date__", "—")


class LogoEmblem(QWidget):
    """Logo inside slowly turning drafting rings (comet, ticks, amber head)."""

    SIZE = 148
    LOGO_SIZE = 72
    SPIN_MS = 6000
    INTRO_MS = 4000

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(self.SIZE, self.SIZE)

        self._logo = QPixmap(str(LOGO_PNG))
        self._angle = 0.0
        self._intro = 0.0
        self._played = False

        self._spin = QVariantAnimation(self)
        self._spin.setDuration(self.SPIN_MS)
        self._spin.setStartValue(0.0)
        self._spin.setEndValue(360.0)
        self._spin.setLoopCount(-1)
        self._spin.valueChanged.connect(self._on_spin)

        self._intro_animation = QVariantAnimation(self)
        self._intro_animation.setDuration(self.INTRO_MS)
        self._intro_animation.setStartValue(0.0)
        self._intro_animation.setEndValue(1.0)
        self._intro_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._intro_animation.valueChanged.connect(self._on_intro)

    def _on_spin(self, value) -> None:
        self._angle = float(value)
        self.update()

    def _on_intro(self, value) -> None:
        self._intro = float(value)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)

        self._spin.start()

        if not self._played:
            self._played = True
            self._intro = 0.0
            self._intro_animation.start()

    def hideEvent(self, event):
        # No animation work while the page is not visible.
        self._spin.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        c = QPointF(self.width() / 2, self.height() / 2)

        # soft glow
        glow = QRadialGradient(c, 74)
        glow.setColorAt(0.0, with_alpha(CYAN, 46))
        glow.setColorAt(0.6, with_alpha(CYAN, 14))
        glow.setColorAt(1.0, with_alpha(CYAN, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(c, 74, 74)

        # outer dashed ring
        dashed = QPen(with_alpha(CYAN, 80), 1)
        dashed.setDashPattern([2.0, 5.0])
        painter.setPen(dashed)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(c, 72, 72)

        # tick ring, turning slowly the other way
        painter.save()
        painter.translate(c)
        painter.rotate(-self._angle * 0.25)

        for index in range(48):
            major = index % 12 == 0
            pen = QPen(
                with_alpha(AMBER, 230) if major else with_alpha(STEEL, 110),
                1.6 if major else 1.0,
            )
            painter.setPen(pen)
            painter.drawLine(
                QPointF(64, 0), QPointF(70 if major else 67, 0)
            )
            painter.rotate(7.5)

        painter.restore()

        # comet ring with amber head
        painter.save()
        painter.translate(c)
        painter.rotate(self._angle)

        gradient = QConicalGradient(QPointF(0, 0), 0)
        gradient.setColorAt(0.0, QColor(CYAN))
        gradient.setColorAt(0.6, with_alpha(CYAN, 0))
        gradient.setColorAt(1.0, with_alpha(CYAN, 0))
        painter.setPen(QPen(QBrush(gradient), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 56, 56)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(AMBER, 70))
        painter.drawEllipse(QPointF(56, 0), 7.5, 7.5)
        painter.setBrush(QColor(AMBER))
        painter.drawEllipse(QPointF(56, 0), 3.8, 3.8)
        painter.restore()

        # inner disc
        painter.setBrush(with_alpha(INK_DEEP, 235))
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawEllipse(c, 46, 46)

        # logo
        painter.setOpacity(self._intro)

        if self._logo.isNull():
            font = QFont(FONT_TITLE)
            font.setPointSizeF(20)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(CYAN))
            painter.drawText(
                QRectF(0, 0, self.width(), self.height()),
                Qt.AlignmentFlag.AlignCenter,
                "SL",
            )
        else:
            size = self.LOGO_SIZE * (0.86 + 0.14 * self._intro)
            target = QRectF(c.x() - size / 2, c.y() - size / 2, size, size)
            painter.drawPixmap(target, self._logo, QRectF(self._logo.rect()))

        painter.setOpacity(1.0)


class SheetCard(QFrame):
    """Drawing-sheet card: blueprint grid, title-block labels, amber corners."""

    RADIUS = 18
    GRID_STEP = 24
    GRID_MAJOR = 4

    def __init__(self, label_left: str, label_right: str, parent=None):
        super().__init__(parent)

        self._label_left = label_left
        self._label_right = label_right

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        sheet = QPainterPath()
        sheet.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.setClipPath(sheet)
        painter.fillPath(sheet, QBrush(QColor(HERO_BG)))

        # light falling from the top edge
        light = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        light.setColorAt(0.0, with_alpha(CYAN, 30))
        light.setColorAt(0.45, with_alpha(CYAN, 0))
        painter.fillRect(rect, QBrush(light))

        # blueprint grid
        minor = QPen(with_alpha(CYAN, 12), 1)
        major = QPen(with_alpha(CYAN, 26), 1)
        step = self.GRID_STEP

        for index, x in enumerate(range(0, int(rect.right()) + step, step)):
            painter.setPen(major if index % self.GRID_MAJOR == 0 else minor)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        for index, y in enumerate(range(0, int(rect.bottom()) + step, step)):
            painter.setPen(major if index % self.GRID_MAJOR == 0 else minor)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        painter.setClipping(False)

        # title-block labels
        font = QFont(FONT_TITLE)
        font.setPointSizeF(7.5)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        painter.setFont(font)
        painter.setPen(QColor(STEEL_DIM))

        width = rect.width() / 2 - 28
        painter.drawText(
            QRectF(rect.left() + 28, rect.top() + 12, width, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._label_left,
        )
        painter.drawText(
            QRectF(rect.center().x(), rect.top() + 12, width, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._label_right,
        )

        # border and sheet-corner marks
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawPath(sheet)
        draw_corner_ticks(painter, rect, QColor(AMBER), inset=9.0, length=13.0)


class ContactRow(ClickableFrame):
    """Clickable contact line with a drawn icon ("mail" or "phone")."""

    RADIUS = 10
    ICON_BOX = 36
    FLASH_MS = 1600

    def __init__(
        self,
        kind: str,
        caption: str,
        value: str,
        tooltip: str,
        parent=None,
    ):
        super().__init__(parent)

        self._kind = kind
        self._caption_text = caption

        self.setFixedHeight(58)
        self.setToolTip(tooltip)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12 + self.ICON_BOX + 12, 0, 12, 0)
        layout.setSpacing(0)

        self._caption = QLabel(caption)
        self._caption.setObjectName("aboutContactCaption")

        value_label = QLabel(value)
        value_label.setObjectName("aboutContactValue")

        for label in (self._caption, value_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addStretch()
        text.addWidget(self._caption)
        text.addWidget(value_label)
        text.addStretch()

        layout.addLayout(text, 1)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(self.FLASH_MS)
        self._flash_timer.timeout.connect(self._restore_caption)

    def flash(self, text: str) -> None:
        """Show short feedback in the caption line, then restore it."""

        self._caption.setText(text)
        self._flash_timer.start()

    def _restore_caption(self) -> None:
        self._caption.setText(self._caption_text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self.emphasis

        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.fillPath(path, QBrush(mix(INK_DEEP, INK_RAISED, t)))
        painter.setPen(QPen(mix(RULE_HI, AMBER, t * 0.85), 1))
        painter.drawPath(path)

        # icon box
        box = QRectF(
            12,
            (self.height() - self.ICON_BOX) / 2,
            self.ICON_BOX,
            self.ICON_BOX,
        )
        box_path = QPainterPath()
        box_path.addRoundedRect(box, 8, 8)
        painter.fillPath(box_path, QBrush(mix(HERO_BG, INK_RAISED, t)))
        painter.setPen(QPen(mix(RULE, CYAN, t), 1))
        painter.drawPath(box_path)

        self._paint_glyph(painter, box, mix(CYAN, AMBER, t))

    def _paint_glyph(self, painter: QPainter, box: QRectF, color: QColor) -> None:
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        c = box.center()

        if self._kind == "mail":
            env = QRectF(c.x() - 9, c.y() - 6, 18, 12)
            painter.drawRoundedRect(env, 2.5, 2.5)
            painter.drawPolyline(
                [
                    QPointF(env.left() + 1.5, env.top() + 2.5),
                    QPointF(c.x(), c.y() + 1.5),
                    QPointF(env.right() - 1.5, env.top() + 2.5),
                ]
            )
        else:
            body = QRectF(c.x() - 6, c.y() - 10, 12, 20)
            painter.drawRoundedRect(body, 3, 3)
            painter.drawLine(
                QPointF(c.x() - 2, body.top() + 3.5),
                QPointF(c.x() + 2, body.top() + 3.5),
            )
            painter.drawPoint(QPointF(c.x(), body.bottom() - 3.5))


class AboutPage(QWidget):
    """About page of the application (shell page, not a plugin)."""

    def __init__(self, version: str, parent=None):
        super().__init__(parent)

        self.setObjectName("page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)

        page_layout = QVBoxLayout(inner)
        page_layout.setContentsMargins(24, 16, 24, 16)
        page_layout.setSpacing(0)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._build_card(version), 10)
        row.addStretch(1)

        page_layout.addStretch(1)
        page_layout.addLayout(row)
        page_layout.addStretch(1)

    # -----------------------------------------------------------------
    # Content
    # -----------------------------------------------------------------

    def _build_card(self, version: str) -> SheetCard:
        card = SheetCard("STRUCTURE LAB  ·  ABOUT", f"REV {version}")
        card.setMaximumWidth(600)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 36, 36, 22)
        layout.setSpacing(0)

        layout.addWidget(LogoEmblem(), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(2)

        title = QLabel("Structure Lab")
        title.setObjectName("aboutPageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        tagline = QLabel("Engineering tools for modeling, design and optimization.")
        tagline.setObjectName("aboutPageTagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        layout.addWidget(tagline)

        layout.addSpacing(12)

        chips = QHBoxLayout()
        chips.setSpacing(10)
        chips.addStretch(1)

        version_chip = QLabel(f"Version {version}")
        version_chip.setObjectName("aboutChipVersion")

        release_chip = QLabel(f"Released {RELEASE_DATE}")
        release_chip.setObjectName("aboutChip")

        chips.addWidget(version_chip)
        chips.addWidget(release_chip)
        chips.addStretch(1)
        layout.addLayout(chips)

        layout.addSpacing(16)

        divider = QFrame()
        divider.setObjectName("aboutDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        layout.addSpacing(12)

        copyright_label = QLabel(f"{COMPANY} © {COPYRIGHT_YEAR}")
        copyright_label.setObjectName("aboutCopyright")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copyright_label)

        layout.addSpacing(12)

        heading = QLabel("Contact for support:")
        heading.setObjectName("aboutHeading")
        layout.addWidget(heading)

        layout.addSpacing(6)

        contacts = QHBoxLayout()
        contacts.setSpacing(12)

        self._email_row = ContactRow(
            "mail", "Email", SUPPORT_EMAIL, "Click to write an email"
        )
        self._email_row.clicked.connect(self._open_mail)

        self._phone_row = ContactRow(
            "phone", "Phone", SUPPORT_PHONE, "Click to copy the number"
        )
        self._phone_row.clicked.connect(self._copy_phone)

        contacts.addWidget(self._email_row, 1)
        contacts.addWidget(self._phone_row, 1)
        layout.addLayout(contacts)

        return card

    # -----------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------

    def _open_mail(self) -> None:
        if not QDesktopServices.openUrl(QUrl(f"mailto:{SUPPORT_EMAIL}")):
            # No mail program: copy the address instead.
            QApplication.clipboard().setText(SUPPORT_EMAIL)
            self._email_row.flash("Copied ✓")

    def _copy_phone(self) -> None:
        QApplication.clipboard().setText(SUPPORT_PHONE)
        self._phone_row.flash("Copied ✓")