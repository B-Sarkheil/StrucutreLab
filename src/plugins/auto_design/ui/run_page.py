"""Auto Design - run page: live view of the evolution.

Shown by the wizard when "Simulate Evolution" is pressed. Pure display:
the wizard owns the worker thread and feeds this page through its slots
(`add_status`, `set_progress`, `add_generation`, `set_state`). There is no
SAP2000 and no GA logic here.

Top to bottom (the middle part scrolls when the window is small):

* header: title, state chip (Running / Cancelling / ...), elapsed time,
* big animated progress bar with the estimated percent,
* four live numbers: generation, best weight, change vs the start, mean DCR,
* the evolution chart (the main part): switch between the weight and the DCR
  ratio of the members; move the mouse over it to read every generation,
* the status log: one line per thing the program did, newest at the bottom;
  it follows the newest line unless the user scrolled up to read older ones.

The footer is always visible: Back (only once the run has stopped) and
Cancel (asks for confirmation; the wizard stops the run).

To add another objective to the chart, add a `MetricSpec` to `METRICS`
(and the value to `GenerationStats`); the switch buttons follow the list.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from src.plugins.auto_design.services.run_monitor import GenerationStats
from src.plugins.auto_design.ui.icons import cancel_icon
from src.ui.theme import (
    AMBER,
    BLUE,
    CYAN,
    DANGER,
    FONT_TITLE,
    INK_DEEP,
    INK_HI,
    INK_RAISED,
    PAPER,
    RULE,
    RULE_HI,
    STEEL,
    STEEL_DIM,
)
from src.ui.widgets import arrow_icon, with_alpha

# Run states (set by the wizard through `RunPage.set_state`).
RUNNING = "running"
CANCELLING = "cancelling"
CANCELLED = "cancelled"
FINISHED = "finished"
FAILED = "failed"

GREEN = "#3DDC97"
VIOLET = "#B48CFF"

WEIGHT_UNIT = "kg"

# state -> (chip text, chip color, percent color, subtitle)
STATE_INFO = {
    RUNNING: (
        "Running",
        CYAN,
        PAPER,
        "The evolution is running. Keep Structure Lab open until it finishes.",
    ),
    CANCELLING: (
        "Cancelling…",
        AMBER,
        AMBER,
        "Stopping: the operation in progress has to finish first.",
    ),
    CANCELLED: (
        "Cancelled",
        STEEL,
        STEEL,
        "The run was cancelled. Go back to change the settings and run again.",
    ),
    FINISHED: ("Finished", GREEN, GREEN, "The run is complete."),
    FAILED: (
        "Failed",
        DANGER,
        DANGER,
        "The run stopped because of an error (see the status list below).",
    ),
}

# state -> (bar start color, bar end color, animated stripes)
BAR_COLORS = {
    RUNNING: (BLUE, CYAN, True),
    CANCELLING: ("#8A5A12", AMBER, True),
    CANCELLED: (RULE_HI, STEEL_DIM, False),
    FINISHED: ("#1E9E6A", GREEN, False),
    FAILED: ("#8E2B30", DANGER, False),
}

PAGE_STYLE = f"""
    QFrame#runCard {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-radius: 12px;
    }}
    QFrame#runTile {{
        background: {INK_RAISED};
        border: 1px solid {RULE};
        border-radius: 12px;
    }}
    QLabel#runTileCaption {{
        background: transparent;
        color: {STEEL_DIM};
        font-size: 8pt;
        font-weight: 600;
    }}
    QLabel#runTileValue {{
        background: transparent;
        color: {PAPER};
        font-family: "{FONT_TITLE}";
        font-size: 18pt;
        font-weight: 600;
    }}
    QLabel#runTileSub {{
        background: transparent;
        color: {STEEL};
        font-size: 8.5pt;
    }}
    QLabel#runCaption {{
        background: transparent;
        color: {STEEL};
        font-family: "{FONT_TITLE}";
        font-size: 11pt;
        font-weight: 600;
    }}
    QLabel#runCardTitle {{
        background: transparent;
        color: {PAPER};
        font-family: "{FONT_TITLE}";
        font-size: 12pt;
        font-weight: 600;
    }}
    QLabel#runPercent {{
        background: transparent;
        font-family: "{FONT_TITLE}";
        font-size: 30pt;
        font-weight: 600;
    }}
    QLabel#runElapsed {{
        background: transparent;
        color: {STEEL};
        font-size: 9.5pt;
    }}
    QPushButton#segButton {{
        background: {INK_DEEP};
        color: {STEEL};
        border: 1px solid {RULE_HI};
        border-radius: 8px;
        padding: 5px 16px;
        font-weight: 600;
    }}
    QPushButton#segButton:hover:!checked {{
        background: {INK_HI};
        color: {PAPER};
    }}
    QPushButton#segButton:checked {{
        background: {BLUE};
        color: #FFFFFF;
        border-color: {CYAN};
    }}
    QPushButton#cancelButton {{
        background: transparent;
        color: {DANGER};
        border: 1px solid {DANGER};
        border-radius: 8px;
        font-weight: 600;
    }}
    QPushButton#cancelButton:hover {{
        background: {DANGER};
        color: #FFFFFF;
    }}
    QPushButton#cancelButton:pressed {{
        background: #A93338;
        color: #FFFFFF;
    }}
    QPushButton#cancelButton:disabled {{
        background: transparent;
        color: {STEEL_DIM};
        border-color: {RULE};
    }}
    QListWidget#statusLog {{
        background: transparent;
        border: none;
        outline: none;
    }}
    QListWidget#statusLog QWidget#qt_scrollarea_viewport {{
        background: transparent;
    }}
"""


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------


def _nice_ticks(lo: float, hi: float, target: int = 5) -> tuple[list[float], float]:
    """Round tick values inside [lo, hi] and their step."""

    span = hi - lo

    if span <= 0:
        return [lo], 1.0

    raw = span / target
    magnitude = 10 ** math.floor(math.log10(raw))
    step = magnitude

    for factor in (1, 2, 2.5, 5, 10):
        step = factor * magnitude

        if step >= raw:
            break

    value = math.ceil(lo / step - 1e-9) * step
    ticks: list[float] = []

    while value <= hi + step * 1e-9:
        ticks.append(value)
        value += step

    return ticks, step


def _tick_decimals(ticks: list[float]) -> int:
    for decimals in range(5):
        if all(abs(round(t, decimals) - t) < 1e-9 for t in ticks):
            return decimals

    return 4


def _nice_int_step(maximum: float, max_labels: int = 10) -> int:
    magnitude = 1

    while True:
        for factor in (1, 2, 5):
            step = factor * magnitude

            if maximum / step <= max_labels:
                return step

        magnitude *= 10


def _format_clock(milliseconds: int) -> str:
    seconds = max(0, milliseconds // 1000)

    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


# ---------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------


class EvolutionProgressBar(QWidget):
    """Large rounded bar: gradient fill, sliding stripes while the run is
    active, a glowing amber head at the end of the fill and a 10 % scale.
    The value glides to each new value."""

    HEIGHT = 44
    RADIUS = 14.0
    GROW_MS = 600
    STRIPE_MS = 1300
    STRIPE_W = 24.0

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setFixedHeight(self.HEIGHT)

        self._target = 0.0
        self._shown = 0.0
        self._state = RUNNING
        self._phase = 0.0

        self._grow = QVariantAnimation(self)
        self._grow.setDuration(self.GROW_MS)
        self._grow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._grow.valueChanged.connect(self._on_grow)

        self._stripes = QVariantAnimation(self)
        self._stripes.setDuration(self.STRIPE_MS)
        self._stripes.setStartValue(0.0)
        self._stripes.setEndValue(1.0)
        self._stripes.setLoopCount(-1)
        self._stripes.valueChanged.connect(self._on_phase)

    def value(self) -> float:
        return self._target

    def set_value(self, fraction: float, animate: bool = True) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        self._target = fraction
        self._grow.stop()

        if not animate or not self.isVisible():
            self._shown = fraction
            self.update()
            return

        self._grow.setStartValue(self._shown)
        self._grow.setEndValue(fraction)
        self._grow.start()

    def set_state(self, state: str) -> None:
        self._state = state
        self._sync_stripes()
        self.update()

    def _on_grow(self, value) -> None:
        self._shown = float(value)
        self.update()

    def _on_phase(self, value) -> None:
        self._phase = float(value)
        self.update()

    def _sync_stripes(self) -> None:
        animated = BAR_COLORS[self._state][2] and self.isVisible()
        running = self._stripes.state() == QAbstractAnimation.State.Running

        if animated and not running:
            self._stripes.start()
        elif not animated and running:
            self._stripes.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._shown = self._target
        self._sync_stripes()

    def hideEvent(self, event):
        # No animation work while the page is not visible.
        self._stripes.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        start, end, animated = BAR_COLORS[self._state]

        track = QPainterPath()
        track.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.fillPath(track, QBrush(QColor(INK_DEEP)))

        painter.save()
        painter.setClipPath(track)

        # 10 % scale marks along the bottom edge
        painter.setPen(QPen(with_alpha(CYAN, 40), 1))

        for index in range(1, 10):
            x = rect.left() + rect.width() * index / 10
            painter.drawLine(QPointF(x, rect.bottom() - 7), QPointF(x, rect.bottom()))

        fill_width = rect.width() * self._shown

        if fill_width > 1.0:
            fill_rect = QRectF(rect.left(), rect.top(), fill_width, rect.height())
            fill = QPainterPath()
            fill.addRoundedRect(fill_rect, self.RADIUS, self.RADIUS)

            gradient = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            gradient.setColorAt(0.0, QColor(start))
            gradient.setColorAt(1.0, QColor(end))
            painter.fillPath(fill, QBrush(gradient))

            painter.save()
            painter.setClipPath(fill, Qt.ClipOperation.IntersectClip)

            if animated:
                stripe = QPen(with_alpha("#FFFFFF", 34), 9)
                painter.setPen(stripe)
                x = fill_rect.left() - rect.height() + self._phase * self.STRIPE_W

                while x < fill_rect.right():
                    painter.drawLine(
                        QPointF(x, rect.bottom()), QPointF(x + rect.height(), rect.top())
                    )
                    x += self.STRIPE_W

            gloss = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() * 0.55)
            gloss.setColorAt(0.0, with_alpha("#FFFFFF", 52))
            gloss.setColorAt(1.0, with_alpha("#FFFFFF", 0))
            painter.fillRect(
                QRectF(fill_rect.left(), rect.top(), fill_width, rect.height() * 0.55),
                QBrush(gloss),
            )
            painter.restore()

            # glowing head
            head_color = QColor(AMBER) if animated else QColor(end)
            cy = rect.center().y()
            glow = QRadialGradient(QPointF(fill_rect.right(), cy), 26)
            glow.setColorAt(0.0, with_alpha(head_color, 120))
            glow.setColorAt(1.0, with_alpha(head_color, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(fill_rect.right(), cy), 26, 26)

            head = QPen(head_color, 2.4)
            head.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(head)
            painter.drawLine(
                QPointF(fill_rect.right() - 1.5, rect.top() + 7),
                QPointF(fill_rect.right() - 1.5, rect.bottom() - 7),
            )

        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawPath(track)


# ---------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesSpec:
    label: str
    attr: str  # field of GenerationStats
    color: str
    dashed: bool = False


@dataclass(frozen=True)
class MetricSpec:
    """One thing the chart can show (the switch buttons follow `METRICS`)."""

    key: str
    button: str  # text of the switch button
    heading: str  # title of the chart card
    unit: str
    decimals: int
    series: tuple[SeriesSpec, ...]  # the first one is the main line
    limit: float | None = None  # horizontal limit line (for example DCR = 1)
    limit_label: str = ""


METRICS = (
    MetricSpec(
        key="weight",
        button="Weight",
        heading="Structure weight per generation",
        unit=WEIGHT_UNIT,
        decimals=1,
        series=(
            SeriesSpec("Best", "bestWeight", CYAN),
            SeriesSpec("Population mean", "meanWeight", STEEL, dashed=True),
        ),
    ),
    MetricSpec(
        key="ratio",
        button="DCR",
        heading="Demand / capacity ratio of the best structure",
        unit="",
        decimals=3,
        series=(
            SeriesSpec("Mean", "meanRatio", CYAN),
            SeriesSpec("Maximum", "maxRatio", VIOLET),
        ),
        limit=1.0,
        limit_label="Limit 1.0",
    ),
    MetricSpec(
        key="deflection",
        button="Deflection",
        heading="Beam deflection ratio of the best structure",
        unit="",
        decimals=3,
        series=(
            SeriesSpec("Mean", "meanDeflection", CYAN),
            SeriesSpec("Maximum", "maxDeflection", VIOLET),
        ),
        limit=1.0,
        limit_label="Limit 1.0",
    ),
)


class EvolutionChart(QWidget):
    """Line chart over the generations: gradient area under the main line,
    amber marker on the newest value, optional limit line, and a read-out of
    all lines at the generation under the mouse."""

    PAD_LEFT = 70.0
    PAD_RIGHT = 22.0
    PAD_TOP = 24.0
    PAD_BOTTOM = 42.0
    INNER_X = 12.0  # data starts a little inside the frame
    MARKER_LIMIT = 60  # no point markers beyond this many generations

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setMinimumHeight(250)
        self.setMouseTracking(True)

        self._metric = METRICS[0]
        self._stats: list[GenerationStats] = []
        self._total = 1
        self._hover: int | None = None
        self._dcr_goal = 1.0

    # -- data -------------------------------------------------------------

    def set_metric(self, metric: MetricSpec) -> None:
        self._metric = metric
        self._hover = None
        self.update()

    def set_total(self, total: int) -> None:
        self._total = max(1, int(total))
        self.update()

    def clear(self) -> None:
        self._stats = []
        self._hover = None
        self.update()

    def set_dcr_goal(self, goal: float) -> None:
        """The limit line of the DCR chart is the DCR goal of step 4.1."""

        self._dcr_goal = float(goal)
        self.update()

    def _limit(self) -> tuple[float | None, str]:
        """(value, label) of the limit line of the metric shown now."""

        if self._metric.key == "ratio":
            return self._dcr_goal, f"DCR goal {self._dcr_goal:g}"

        return self._metric.limit, self._metric.limit_label


    def add(self, stats: GenerationStats) -> None:
        self._stats.append(stats)
        self.update()

    # -- geometry ---------------------------------------------------------

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self.PAD_LEFT,
            self.PAD_TOP,
            max(0.0, self.width() - self.PAD_LEFT - self.PAD_RIGHT),
            max(0.0, self.height() - self.PAD_TOP - self.PAD_BOTTOM),
        )

    def _x_max(self) -> float:
        last = max((s.generation for s in self._stats), default=1)

        return float(max(self._total, last, 2))

    def _x_of(self, plot: QRectF, generation: float) -> float:
        data = plot.adjusted(self.INNER_X, 0, -self.INNER_X, 0)

        return data.left() + (generation - 1) / (self._x_max() - 1) * data.width()

    @staticmethod
    def _y_of(plot: QRectF, lo: float, hi: float, value: float) -> float:
        return plot.bottom() - (value - lo) / (hi - lo) * plot.height()

    def _y_range(self) -> tuple[float, float]:
        values = [
            getattr(stats, series.attr)
            for stats in self._stats
            for series in self._metric.series
        ]

        limit = self._limit()[0]

        if limit is not None:
            values.append(limit)

        if not values:
            return 0.0, 1.0

        lo, hi = min(values), max(values)
        non_negative = lo >= 0.0

        if hi - lo < 1e-9:
            pad = abs(hi) * 0.05 or 1.0
        else:
            pad = (hi - lo) * 0.14

        lo, hi = lo - pad, hi + pad

        if non_negative and lo < 0.0:
            lo = 0.0

        return lo, hi

    def _fmt(self, value: float) -> str:
        return f"{value:,.{self._metric.decimals}f}"

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        plot = self._plot_rect()

        if plot.width() < 40 or plot.height() < 40:
            return

        lo, hi = self._y_range()

        self._paint_grid(painter, plot, lo, hi)

        if not self._stats:
            font = QFont(self.font())
            font.setPointSizeF(10.5)
            painter.setFont(font)
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                plot, Qt.AlignmentFlag.AlignCenter, "Waiting for the first generation…"
            )
            return

        self._paint_limit(painter, plot, lo, hi)

        series = self._metric.series

        for index in range(len(series) - 1, -1, -1):
            self._paint_series(painter, plot, lo, hi, series[index], index == 0)

        self._paint_latest(painter, plot, lo, hi)
        self._paint_legend(painter, plot)

        if self._hover is not None and self._hover < len(self._stats):
            self._paint_hover(painter, plot, lo, hi)

    def _paint_grid(self, painter: QPainter, plot: QRectF, lo: float, hi: float) -> None:
        ticks, _step = _nice_ticks(lo, hi)
        decimals = _tick_decimals(ticks)

        font = QFont(self.font())
        font.setPointSizeF(8)
        painter.setFont(font)

        grid = QPen(with_alpha(CYAN, 24), 1)

        for value in ticks:
            y = self._y_of(plot, lo, hi, value)
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                QRectF(0, y - 9, plot.left() - 8, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:,.{decimals}f}",
            )

        x_max = self._x_max()
        step = _nice_int_step(x_max - 1)
        generation = 1

        while generation <= x_max + 1e-9:
            x = self._x_of(plot, generation)
            painter.setPen(grid)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                QRectF(x - 24, plot.bottom() + 5, 48, 16),
                Qt.AlignmentFlag.AlignCenter,
                str(generation),
            )
            generation += step

        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.topLeft(), plot.bottomLeft())

        painter.setPen(QColor(STEEL))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 22, plot.width(), 16),
            Qt.AlignmentFlag.AlignCenter,
            "Generation",
        )

        if self._metric.unit:
            painter.setPen(QColor(STEEL_DIM))
            painter.drawText(
                QRectF(4, 2, plot.left() - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._metric.unit,
            )

    def _paint_limit(self, painter: QPainter, plot: QRectF, lo: float, hi: float) -> None:
        limit, label = self._limit()

        if limit is None or not lo <= limit <= hi:
            return

        y = self._y_of(plot, lo, hi, limit)
        pen = QPen(with_alpha(AMBER, 200), 1.4)
        pen.setDashPattern([6.0, 4.0])
        painter.setPen(pen)
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        font = QFont(self.font())
        font.setPointSizeF(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(AMBER))
        painter.drawText(
            QRectF(plot.right() - 124, y - 17, 118, 14),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            label,
        )

    def _points(
        self, plot: QRectF, lo: float, hi: float, series: SeriesSpec
    ) -> list[QPointF]:
        return [
            QPointF(
                self._x_of(plot, stats.generation),
                self._y_of(plot, lo, hi, getattr(stats, series.attr)),
            )
            for stats in self._stats
        ]

    def _paint_series(
        self,
        painter: QPainter,
        plot: QRectF,
        lo: float,
        hi: float,
        series: SeriesSpec,
        primary: bool,
    ) -> None:
        points = self._points(plot, lo, hi, series)
        color = QColor(series.color)

        painter.save()
        painter.setClipRect(plot.adjusted(-2, -6, 2, 6))

        if primary and len(points) >= 2:
            area = QPainterPath()
            area.moveTo(points[0].x(), plot.bottom())

            for point in points:
                area.lineTo(point)

            area.lineTo(points[-1].x(), plot.bottom())
            area.closeSubpath()

            gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
            gradient.setColorAt(0.0, with_alpha(color, 90))
            gradient.setColorAt(1.0, with_alpha(color, 0))
            painter.fillPath(area, QBrush(gradient))

        pen = QPen(color, 2.6 if primary else 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        if series.dashed:
            pen.setDashPattern([4.0, 3.0])

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if len(points) >= 2:
            path = QPainterPath(points[0])

            for point in points[1:]:
                path.lineTo(point)

            painter.drawPath(path)

        painter.restore()

        if len(points) <= self.MARKER_LIMIT:
            painter.setBrush(QColor(INK_RAISED))
            painter.setPen(QPen(color, 1.6))
            radius = 3.4 if primary else 2.6

            for point in points:
                painter.drawEllipse(point, radius, radius)

    def _paint_latest(self, painter: QPainter, plot: QRectF, lo: float, hi: float) -> None:
        """Amber marker and value bubble on the newest point of the main line."""

        series = self._metric.series[0]
        value = getattr(self._stats[-1], series.attr)
        point = QPointF(
            self._x_of(plot, self._stats[-1].generation),
            self._y_of(plot, lo, hi, value),
        )

        glow = QRadialGradient(point, 15)
        glow.setColorAt(0.0, with_alpha(AMBER, 130))
        glow.setColorAt(1.0, with_alpha(AMBER, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(point, 15, 15)

        painter.setBrush(QColor(AMBER))
        painter.setPen(QPen(QColor(INK_DEEP), 1.5))
        painter.drawEllipse(point, 4.8, 4.8)

        font = QFont(self.font())
        font.setPointSizeF(9)
        font.setBold(True)
        painter.setFont(font)

        text = self._fmt(value)
        width = QFontMetrics(font).horizontalAdvance(text) + 18
        height = 22.0

        x = point.x() - width - 10

        if x < plot.left() + 4:
            x = point.x() + 10

        x = min(x, plot.right() - width)
        y = point.y() - height - 8

        if y < plot.top():
            y = point.y() + 8

        box = QRectF(x, y, width, height)
        shape = QPainterPath()
        shape.addRoundedRect(box, 7, 7)
        painter.fillPath(shape, QBrush(with_alpha(INK_DEEP, 235)))
        painter.setPen(QPen(QColor(AMBER), 1))
        painter.drawPath(shape)
        painter.setPen(QColor(PAPER))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_legend(self, painter: QPainter, plot: QRectF) -> None:
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        sample, gap, spacing = 20.0, 6.0, 18.0
        widths = [
            sample + gap + metrics.horizontalAdvance(s.label) for s in self._metric.series
        ]
        x = plot.right() - sum(widths) - spacing * (len(widths) - 1)
        cy = 11.0

        for series, width in zip(self._metric.series, widths):
            pen = QPen(QColor(series.color), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)

            if series.dashed:
                pen.setDashPattern([3.0, 2.5])

            painter.setPen(pen)
            painter.drawLine(QPointF(x, cy), QPointF(x + sample, cy))
            painter.setPen(QColor(STEEL))
            painter.drawText(
                QRectF(x + sample + gap, 0, width, 22),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                series.label,
            )
            x += width + spacing

    def _paint_hover(self, painter: QPainter, plot: QRectF, lo: float, hi: float) -> None:
        stats = self._stats[self._hover]
        x = self._x_of(plot, stats.generation)

        pen = QPen(with_alpha(PAPER, 90), 1)
        pen.setDashPattern([3.0, 3.0])
        painter.setPen(pen)
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        rows: list[tuple[str, str]] = [(f"Generation {stats.generation}", PAPER)]

        for series in self._metric.series:
            value = getattr(stats, series.attr)
            unit = f" {self._metric.unit}" if self._metric.unit else ""
            rows.append((f"{series.label}:  {self._fmt(value)}{unit}", series.color))

            ring = QPointF(x, self._y_of(plot, lo, hi, value))
            painter.setBrush(QColor(INK_DEEP))
            painter.setPen(QPen(QColor(series.color), 2))
            painter.drawEllipse(ring, 5, 5)

        font = QFont(self.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        width = max(metrics.horizontalAdvance(text) for text, _c in rows) + 22
        line = 18.0
        height = line * len(rows) + 12
        box_x = x + 14 if x + 14 + width <= plot.right() else x - 14 - width
        box = QRectF(box_x, plot.top() + 8, width, height)

        shape = QPainterPath()
        shape.addRoundedRect(box, 8, 8)
        painter.fillPath(shape, QBrush(with_alpha(INK_DEEP, 240)))
        painter.setPen(QPen(QColor(RULE_HI), 1))
        painter.drawPath(shape)

        for index, (text, color) in enumerate(rows):
            row_font = QFont(font)
            row_font.setBold(index == 0)
            painter.setFont(row_font)
            painter.setPen(QColor(color))
            painter.drawText(
                QRectF(box.left() + 11, box.top() + 6 + index * line, width - 14, line),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )

    # -- mouse ------------------------------------------------------------

    def mouseMoveEvent(self, event):
        index = None

        if self._stats:
            plot = self._plot_rect()
            position = event.position()

            if plot.adjusted(-10, -10, 10, 10).contains(position):
                index = min(
                    range(len(self._stats)),
                    key=lambda i: abs(
                        self._x_of(plot, self._stats[i].generation) - position.x()
                    ),
                )

        if index != self._hover:
            self._hover = index
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover = None
            self.update()

        super().leaveEvent(event)


# ---------------------------------------------------------------------
# Live numbers
# ---------------------------------------------------------------------


class StatTile(QFrame):
    """Caption, one big value and a small line under it."""

    def __init__(self, caption: str, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("runTile")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 12)
        layout.setSpacing(1)

        self._caption = QLabel(caption.upper())
        self._caption.setObjectName("runTileCaption")

        self._value = QLabel("–")
        self._value.setObjectName("runTileValue")

        self._sub = QLabel("")
        self._sub.setObjectName("runTileSub")

        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        layout.addWidget(self._sub)

    def set_value(self, value: str, sub: str = "", color: str | None = None) -> None:
        self._value.setText(value)
        self._value.setStyleSheet(f"color: {color};" if color else "")
        self._sub.setText(sub)


# ---------------------------------------------------------------------
# Status log
# ---------------------------------------------------------------------

ROLE_STATE = Qt.ItemDataRole.UserRole
ROLE_TIME = Qt.ItemDataRole.UserRole + 1

# state of a line: "active" (in progress), "done", "stopped" (cancelled), "error"
TEXT_COLORS = {"active": PAPER, "done": STEEL, "stopped": STEEL_DIM, "error": DANGER}


class _StatusDelegate(QStyledItemDelegate):
    ROW = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = 0.0  # 0..1, pulse of the active line

    def sizeHint(self, option, index):
        return QSize(0, self.ROW)

    def paint(self, painter, option, index):
        state = index.data(ROLE_STATE) or "done"
        stamp = index.data(ROLE_TIME) or ""
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        rect = QRectF(option.rect)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(QPen(QColor(RULE), 1))
        painter.drawLine(
            QPointF(rect.left() + 10, rect.bottom() - 0.5),
            QPointF(rect.right() - 10, rect.bottom() - 0.5),
        )

        self._paint_icon(painter, state, QPointF(rect.left() + 24, rect.center().y()))

        stamp_font = QFont("Consolas")
        stamp_font.setPointSizeF(9)
        painter.setFont(stamp_font)
        painter.setPen(QColor(STEEL_DIM))
        painter.drawText(
            QRectF(rect.left() + 42, rect.top(), 70, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            stamp,
        )

        font = QFont(option.font)
        font.setBold(state in ("active", "error"))
        painter.setFont(font)
        painter.setPen(QColor(TEXT_COLORS.get(state, STEEL)))

        text_rect = QRectF(rect.left() + 118, rect.top(), rect.width() - 118 - 16, rect.height())
        elided = QFontMetrics(font).elidedText(
            text, Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided
        )

        painter.restore()

    def _paint_icon(self, painter: QPainter, state: str, c: QPointF) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if state == "active":
            ring = 4.0 + 5.0 * self.phase
            painter.setPen(QPen(with_alpha(AMBER, int(170 * (1.0 - self.phase))), 1.6))
            painter.drawEllipse(c, ring, ring)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(AMBER))
            painter.drawEllipse(c, 3.6, 3.6)
            return

        if state == "done":
            pen = QPen(QColor(GREEN), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                [
                    QPointF(c.x() - 4.5, c.y() + 0.5),
                    QPointF(c.x() - 1.5, c.y() + 3.5),
                    QPointF(c.x() + 4.5, c.y() - 3.5),
                ]
            )
            return

        if state == "error":
            pen = QPen(QColor(DANGER), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(c.x() - 3.6, c.y() - 3.6), QPointF(c.x() + 3.6, c.y() + 3.6))
            painter.drawLine(QPointF(c.x() - 3.6, c.y() + 3.6), QPointF(c.x() + 3.6, c.y() - 3.6))
            return

        # stopped
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(STEEL_DIM))
        painter.drawRoundedRect(QRectF(c.x() - 3.5, c.y() - 3.5, 7, 7), 1.5, 1.5)


class StatusLog(QListWidget):
    """What the program is doing, one line under the other. The line in
    progress pulses; finished lines get a tick. Follows the newest line
    unless the user has scrolled up."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("statusLog")
        self._delegate = _StatusDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)

        self._pulse = QVariantAnimation(self)
        self._pulse.setDuration(1100)
        self._pulse.setStartValue(0.0)
        self._pulse.setEndValue(1.0)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self._on_pulse)

    # -- public -----------------------------------------------------------

    def add(self, text: str) -> None:
        """A new step starts; the previous one is done."""

        self._deactivate("done")
        self._append(text, "active")

    def finish(self, outcome: str, text: str) -> None:
        """The run ended: `outcome` is "done", "stopped" or "error"."""

        self._deactivate(outcome)
        self._append(text, outcome)

    def clear_log(self) -> None:
        self.clear()
        self._sync_pulse()

    # -- internals --------------------------------------------------------

    def _active_item(self) -> QListWidgetItem | None:
        count = self.count()

        if count and self.item(count - 1).data(ROLE_STATE) == "active":
            return self.item(count - 1)

        return None

    def _deactivate(self, outcome: str) -> None:
        item = self._active_item()

        if item is not None:
            item.setData(ROLE_STATE, outcome)

    def _append(self, text: str, state: str) -> None:
        bar = self.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4

        item = QListWidgetItem(text)
        item.setData(ROLE_STATE, state)
        item.setData(ROLE_TIME, datetime.now().strftime("%H:%M:%S"))
        self.addItem(item)

        if at_end:
            QTimer.singleShot(0, self.scrollToBottom)

        self._sync_pulse()
        self.viewport().update()

    def _on_pulse(self, value) -> None:
        self._delegate.phase = float(value)
        self.viewport().update()

    def _sync_pulse(self) -> None:
        wanted = self._active_item() is not None and self.isVisible()
        running = self._pulse.state() == QAbstractAnimation.State.Running

        if wanted and not running:
            self._pulse.start()
        elif not wanted and running:
            self._pulse.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_pulse()

    def hideEvent(self, event):
        self._pulse.stop()
        super().hideEvent(event)

class CancelButton(QPushButton):
    """Cancel button whose X icon follows the hover: red normally, white
    while the mouse is over it (the button fills with red then)."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)

        self._normal = cancel_icon(22)
        self._hover = cancel_icon(22, color="#FFFFFF")
        self.setIcon(self._normal)
        self.setIconSize(QSize(22, 22))

    def enterEvent(self, event):
        if self.isEnabled():
            self.setIcon(self._hover)

        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._normal)
        super().leaveEvent(event)

    def changeEvent(self, event):
        # After Cancel is pressed the button is disabled while the mouse is
        # still over it: go back to the normal (gray when disabled) icon.
        if event.type() == QEvent.Type.EnabledChange:
            self.setIcon(self._normal)

        super().changeEvent(event)

# ---------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------

class ElidedLabel(QLabel):
    """Label that never forces the page wider: a long text is cut in the
    middle ("D:\\Models\\…\\Gen-5-1.sdb"); the full text is the tooltip."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = max(10, self.width())
        self.setText(
            QFontMetrics(self.font()).elidedText(
                self._full, Qt.TextElideMode.ElideMiddle, width
            )
        )


class RunPage(QWidget):
    """Live view of one run. See the module docstring."""

    back_requested = Signal()
    cancel_requested = Signal()
    next_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")
        self.setStyleSheet(PAGE_STYLE)

        self._state = RUNNING
        self._total = 1
        self._first_best: float | None = None
        self._first_generation = 0

        self._clock = QElapsedTimer()
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._update_elapsed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(34, 26, 34, 12)
        layout.setSpacing(0)

        layout.addLayout(self._build_header())
        layout.addSpacing(16)
        layout.addWidget(self._build_progress_card())
        layout.addWidget(self._build_final_box())
        layout.addSpacing(12)
        layout.addLayout(self._build_tiles())
        layout.addSpacing(12)
        layout.addWidget(self._build_chart_card(), 3)
        layout.addSpacing(12)
        layout.addWidget(self._build_log_card(), 2)

        outer.addLayout(self._build_footer())

        self._apply_state(RUNNING)

    # -- building ---------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        title = QLabel("Auto Design")
        title.setObjectName("pageTitle")

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)

        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(title)
        left.addWidget(self.subtitle)

        self.chip = QLabel("")
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chip.setFixedHeight(24)
        self.chip.setMinimumWidth(104)

        self.elapsed = QLabel("Elapsed 0:00:00")
        self.elapsed.setObjectName("runElapsed")
        self.elapsed.setAlignment(Qt.AlignmentFlag.AlignRight)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addSpacing(8)
        right.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self.elapsed, 0, Qt.AlignmentFlag.AlignRight)
        right.addStretch(1)

        header = QHBoxLayout()
        header.setSpacing(20)
        header.addLayout(left, 1)
        header.addLayout(right)

        return header

    def _build_progress_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("runCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 18)
        layout.setSpacing(10)

        caption = QLabel("Overall progress")
        caption.setObjectName("runCaption")

        self.percent = QLabel("0%")
        self.percent.setObjectName("runPercent")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        top = QHBoxLayout()
        top.addWidget(caption, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        top.addWidget(self.percent)

        self.bar = EvolutionProgressBar()

        layout.addLayout(top)
        layout.addWidget(self.bar)

        return card

    def _build_tiles(self) -> QHBoxLayout:
        self.tile_generation = StatTile("Generation")
        self.tile_best = StatTile("Best weight")
        self.tile_change = StatTile("Change in weight")
        self.tile_ratio = StatTile("Mean DCR")
        self.tile_deflection = StatTile("Mean Deflection")

        tiles = QHBoxLayout()
        tiles.setSpacing(12)

        for tile in (
            self.tile_generation,
            self.tile_best,
            self.tile_change,
            self.tile_ratio,
            self.tile_deflection,
        ):
            tiles.addWidget(tile, 1)

        return tiles

    def _build_chart_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("runCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 12)
        layout.setSpacing(8)

        self.chart_title = QLabel("")
        self.chart_title.setObjectName("runCardTitle")

        switch = QHBoxLayout()
        switch.setSpacing(6)
        self._metric_group = QButtonGroup(self)
        self._metric_group.setExclusive(True)

        for index, metric in enumerate(METRICS):
            button = QPushButton(metric.button)
            button.setObjectName("segButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked=False, m=metric: self._select_metric(m))
            self._metric_group.addButton(button, index)
            switch.addWidget(button)

        head = QHBoxLayout()
        head.addWidget(self.chart_title)
        head.addStretch(1)
        head.addLayout(switch)

        self.chart = EvolutionChart()

        layout.addLayout(head)
        layout.addWidget(self.chart, 1)

        self._select_metric(METRICS[0])

        return card

    def _build_log_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("runCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 12)
        layout.setSpacing(6)

        title = QLabel("Status")
        title.setObjectName("runCardTitle")

        self.log = StatusLog()
        self.log.setMinimumHeight(150)

        layout.addWidget(title)
        layout.addWidget(self.log, 1)

        return card

    def _build_footer(self) -> QHBoxLayout:
        self.back_button = QPushButton("Back")
        self.back_button.setIcon(arrow_icon("left", color=PAPER))
        self.back_button.setIconSize(QSize(32, 24))
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setMinimumSize(110, 42)
        self.back_button.clicked.connect(self._on_back_clicked)

        self.cancel_button = CancelButton("  Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setMinimumSize(150, 42)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        self.next_button = QPushButton("Next")
        self.next_button.setIcon(arrow_icon("right"))
        self.next_button.setIconSize(QSize(32, 24))
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_button.setObjectName("primaryButton")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setMinimumSize(150, 42)
        self.next_button.clicked.connect(self.next_requested.emit)

        footer = QHBoxLayout()
        footer.setContentsMargins(34, 8, 34, 20)
        footer.setSpacing(10)
        footer.addWidget(self.back_button)
        footer.addStretch(1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.next_button)

        return footer

    # -- feeding the page (called by the wizard) ----------------------------

    def start(self, total_generations: int, dcr_goal: float = 1.0) -> None:
        """Reset the page for a new run."""

        self._total = max(1, int(total_generations))
        self._first_best = None

        self.chart.clear()
        self.chart.set_total(self._total)
        self.chart.set_dcr_goal(dcr_goal)
        self.log.clear_log()
        self.final_box.setVisible(False)

        self.bar.set_value(0.0, animate=False)
        self._set_percent(0.0)

        self.tile_generation.set_value("–", f"of {self._total}")
        self.tile_best.set_value("–", WEIGHT_UNIT)
        self.tile_change.set_value("–", "")
        self.tile_ratio.set_value("–", "")
        self.tile_deflection.set_value("–", "")

        self._state = RUNNING
        self._apply_state(RUNNING)

        self._clock.start()
        self._ticker.start()
        self._update_elapsed()

    def set_progress(self, fraction: float) -> None:
        self.bar.set_value(fraction)
        self._set_percent(fraction)

    def add_status(self, text: str) -> None:
        self.log.add(text)

    def add_generation(self, stats: GenerationStats) -> None:
        self.chart.add(stats)

        if self._first_best is None:
            self._first_best = stats.bestWeight
            self._first_generation = stats.generation

        self.tile_generation.set_value(f"{stats.generation} / {self._total}", "generation")
        self.tile_best.set_value(f"{stats.bestWeight:,.1f}", WEIGHT_UNIT)

        first = self._first_best

        if first:
            change = (stats.bestWeight - first) / first * 100.0
            color = GREEN if change < -1e-9 else (DANGER if change > 1e-9 else None)
            self.tile_change.set_value(
                f"{change:+.1f} %", f"vs generation {self._first_generation}", color
            )

        self.tile_ratio.set_value(f"{stats.meanRatio:.3f}", f"max {stats.maxRatio:.3f}")
        
        if stats.maxDeflection > 0.0:
            self.tile_deflection.set_value(
                f"{stats.meanDeflection:.3f}", f"max {stats.maxDeflection:.3f}"
            )
        else:
            self.tile_deflection.set_value("–", "not used")

    def set_final(self, name: str, path: str, weight: float,
                  max_ratio: float, feasible: bool, cv: float,
                  max_deflection: float = 0.0, deflection_used: bool = False,
                  dcr_goal: float = 1.0) -> None:
        """The selected member of the finished run: its SAP file and numbers."""

        self._style_chip(self.chip_name, f"★ {name}", CYAN)
        self._style_chip(self.chip_weight, f"{weight:,.1f} {WEIGHT_UNIT}", AMBER)
        self._style_chip(
            self.chip_dcr,
            f"max DCR {max_ratio:.3f}  (goal {dcr_goal:g})",
            GREEN if max_ratio <= dcr_goal else DANGER,
        )

        self.chip_defl.setVisible(deflection_used)

        if deflection_used:
            self._style_chip(
                self.chip_defl,
                f"max Deflection {max_deflection:.3f}",
                GREEN if max_deflection <= 1.0 else DANGER,
            )

        if feasible:
            self._style_chip(self.chip_state, "✓ All constraints satisfied", GREEN)
        else:
            self._style_chip(self.chip_state, f"✗ Violates constraints (CV = {cv:.4g})", DANGER)

        self.final_path.set_full_text(path)
        self.final_box.setVisible(True)

    def set_state(self, state: str, message: str = "") -> None:
        """RUNNING, CANCELLING, CANCELLED, FINISHED or FAILED."""

        self._state = state

        if state == FINISHED:
            self.set_progress(1.0)
            self.log.finish("done", "The run finished.")
        elif state == CANCELLED:
            self.log.finish("stopped", "The run was cancelled.")
        elif state == FAILED:
            self.log.finish("error", f"The run failed: {message}" if message else "The run failed.")

        if state not in (RUNNING, CANCELLING):
            self._ticker.stop()
            self._update_elapsed()

        self._apply_state(state)

    # -- internals ----------------------------------------------------------

    def _select_metric(self, metric: MetricSpec) -> None:
        unit = f"  ({metric.unit})" if metric.unit else ""
        self.chart_title.setText(metric.heading + unit)
        self.chart.set_metric(metric)

    def _set_percent(self, fraction: float) -> None:
        self.percent.setText(f"{int(max(0.0, min(1.0, fraction)) * 100)}%")

    def _update_elapsed(self) -> None:
        elapsed = self._clock.elapsed() if self._clock.isValid() else 0
        self.elapsed.setText(f"Elapsed {_format_clock(elapsed)}")

    def _apply_state(self, state: str) -> None:
        text, color, percent_color, subtitle = STATE_INFO[state]

        self.chip.setText(text)
        tint = QColor(color)
        self.chip.setStyleSheet(
            f"QLabel {{ color: {color};"
            f" background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 38);"
            f" border: 1px solid {color}; border-radius: 12px;"
            f" padding: 0 14px; font-size: 9pt; font-weight: 600; }}"
        )
        self.percent.setStyleSheet(f"color: {percent_color};")
        self.subtitle.setText(subtitle)
        self.bar.set_state(state)

        active = state in (RUNNING, CANCELLING)

        self.cancel_button.setVisible(active)
        self.cancel_button.setEnabled(state == RUNNING)
        self.back_button.setEnabled(not active)
        self.next_button.setEnabled(state == FINISHED)
        self.back_button.setToolTip(
            "Cancel the run first to go back." if active else "Back to the settings"
        )

    def _on_cancel_clicked(self) -> None:
        if self._state != RUNNING:
            return

        answer = QMessageBox.question(
            self,
            "Cancel the run",
            "Stop the evolution now?\n\n"
            "The operation in progress finishes first, then the run stops. "
            "You can go back afterwards and change the settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes or self._state != RUNNING:
            return

        self._state = CANCELLING
        self._apply_state(CANCELLING)
        self.cancel_requested.emit()

    def _on_back_clicked(self) -> None:
        if self._state in (RUNNING, CANCELLING):
            return

        self.back_requested.emit()

    # -- final box ----------------------------------------------------------
    
    @staticmethod
    def _style_chip(label: QLabel, text: str, color: str) -> None:
        tint = QColor(color)
        label.setText(text)
        label.setStyleSheet(
            f"QLabel {{ color: {color};"
            f" background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 36);"
            f" border: 1px solid {color}; border-radius: 12px;"
            f" padding: 3px 14px; font-size: 10pt; font-weight: 700; }}"
        )

    def _build_final_box(self) -> QWidget:
        self.final_box = QWidget()
        box = QVBoxLayout(self.final_box)
        box.setContentsMargins(0, 12, 0, 0)

        card = QFrame()
        card.setObjectName("finalCard")
        card.setStyleSheet(
            f"QFrame#finalCard {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 {INK_HI}, stop:1 {INK_RAISED}); border: 1px solid {RULE_HI};"
            f" border-left: 4px solid {GREEN}; border-radius: 12px; }}"
        )
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 14, 20, 14)
        inner.setSpacing(10)

        title = QLabel("FINAL SELECTED MEMBER")
        title.setStyleSheet(
            f"background: transparent; color: {GREEN}; font-family: '{FONT_TITLE}';"
            " font-size: 12pt; font-weight: 700; letter-spacing: 2px;"
        )

        self.chip_name = QLabel("")
        self.chip_weight = QLabel("")
        self.chip_dcr = QLabel("")
        self.chip_defl = QLabel("")
        self.chip_state = QLabel("")

        chips = QHBoxLayout()
        chips.setSpacing(8)

        for chip in (self.chip_name, self.chip_weight, self.chip_dcr,
                     self.chip_defl, self.chip_state):
            chips.addWidget(chip, 0, Qt.AlignmentFlag.AlignLeft)

        chips.addStretch(1)

        file_caption = QLabel("SAP2000 file")
        file_caption.setStyleSheet(
            f"background: transparent; color: {STEEL_DIM}; font-size: 9pt; font-weight: 700;"
        )
        self.final_path = ElidedLabel()
        self.final_path.setStyleSheet(f"background: transparent; color: {STEEL}; font-size: 9.5pt;")
        self.final_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_row.addWidget(file_caption)
        path_row.addWidget(self.final_path, 1)

        inner.addWidget(title)
        inner.addLayout(chips)
        inner.addLayout(path_row)

        box.addWidget(card)
        self.final_box.setVisible(False)
        return self.final_box
