"""Dev tool: shows the Auto Design run page with fake data (no SAP2000, no GA).

Run from the project folder:

    .\\runtime\\python\\python.exe tools\\preview_run_page.py

It plays a made-up run: three status lines, then one generation every
700 ms. Try Cancel (then Back), the chart switch and the hover read-out.
Not part of the app: it lives in tools/ and never reaches the users.
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from src.plugins.auto_design.services.run_monitor import GenerationStats  # noqa: E402
from src.plugins.auto_design.ui.run_page import CANCELLED, FINISHED, RunPage  # noqa: E402
from src.ui.theme import apply_theme  # noqa: E402

GENERATIONS = 12
STEP_MS = 700
START_STATUSES = (
    "Reading the material type of every section",
    "Reading the section assigned to every frame",
    "Reading joint coordinates and frame connectivity",
)


class Preview(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Run page preview")
        self.resize(950, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.page = RunPage()
        layout.addWidget(self.page)

        self.page.cancel_requested.connect(self._on_cancel)
        self.page.back_requested.connect(self._restart)

        self._timer = QTimer(self)
        self._timer.setInterval(STEP_MS)
        self._timer.timeout.connect(self._tick)

        self._restart()

    def _restart(self) -> None:
        self._index = 0
        self.page.start(GENERATIONS)
        self._timer.start()

    def _on_cancel(self) -> None:
        self._timer.stop()
        QTimer.singleShot(900, lambda: self.page.set_state(CANCELLED))

    def _tick(self) -> None:
        total = len(START_STATUSES) + GENERATIONS + 1
        index = self._index
        self._index += 1

        if index < len(START_STATUSES):
            self.page.add_status(START_STATUSES[index])
        elif index <= len(START_STATUSES) + GENERATIONS:
            generation = index - len(START_STATUSES)
            self.page.add_status(f"Generation {generation}: analysing the population")
            fade = math.exp(-0.32 * generation)
            noise = random.uniform(-0.01, 0.01)
            best = 48_000 * (0.60 + 0.40 * fade + noise)
            self.page.add_generation(
                GenerationStats(
                    generation=generation,
                    bestWeight=best,
                    meanWeight=best * (1.12 + 0.30 * fade),
                    meanRatio=0.52 + 0.30 * (1 - fade),
                    maxRatio=1.40 - 0.38 * (1 - fade),
                )
            )
        else:
            self._timer.stop()
            self.page.set_state(FINISHED)
            return

        self.page.set_progress((index + 1) / total)


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = Preview()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
