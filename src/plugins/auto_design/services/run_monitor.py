"""Auto Design - live reporting of a run and cooperative cancel (no Qt).

The GA code talks to a `RunMonitor`; it never knows who listens. The wizard
connects the three callbacks to Qt signals of the worker thread, so the run
page can show the progress, the status lines and the numbers of every
generation while the run is going on.

Cancel is cooperative: `cancel()` only sets a flag. `status()` is a
checkpoint (it raises `RunCancelled` when the flag is set), and the GA code
may call `raise_if_cancelled()` anywhere else it can safely stop. A SAP2000
call that is already running cannot be interrupted; the run stops at the
next checkpoint.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RunCancelled(Exception):
    """Raised inside the run when the user asked to stop it."""


@dataclass(frozen=True)
class GenerationStats:
    """The numbers of one generation, shown by the run page.

    Generation 1 is the initial population (the reference structure).
    """

    generation: int
    bestWeight: float  # weight of the best structure of the generation
    meanWeight: float  # mean weight of the whole population
    meanRatio: float  # mean STRESS ratio of the frames of the best structure
    maxRatio: float  # largest STRESS ratio in the best structure (limit is 1.0)
    meanDeflection: float = 0.0  # mean deflection ratio of the beams of the best structure
    maxDeflection: float = 0.0  # largest deflection ratio (limit is 1.0)


def _ignore(*_args) -> None:
    return None


class RunMonitor:
    """Progress / status / generation reports and the cancel flag."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

        # Set by the listener (the wizard's worker). Called from the run's
        # thread, so a listener must be thread-safe (Qt signals are).
        self.on_status: Callable[[str], None] = _ignore
        self.on_progress: Callable[[float], None] = _ignore
        self.on_generation: Callable[[GenerationStats], None] = _ignore

    # -- cancel -----------------------------------------------------------

    def cancel(self) -> None:
        """Ask the run to stop at its next checkpoint (any thread)."""

        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise RunCancelled()

    # -- reports ----------------------------------------------------------

    def status(self, text: str) -> None:
        """Announce what the program is doing now (also a cancel checkpoint)."""

        self.raise_if_cancelled()
        logger.info("Status: %s", text)
        self.on_status(text)

    def progress(self, fraction: float) -> None:
        """Estimated progress of the whole run, 0.0 .. 1.0."""

        self.on_progress(max(0.0, min(1.0, float(fraction))))

    def generation(self, stats: GenerationStats) -> None:
        """Numbers of a finished generation."""

        self.on_generation(stats)
