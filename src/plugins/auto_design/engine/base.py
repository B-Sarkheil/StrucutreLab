"""Evaluation engine interface. The GA only ever calls evaluate(x)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class EvalResult:
    weight: float
    dcr: np.ndarray
    drift: float = 0.0
    deflection: float = 0.0
    analysis_time: float = 0.0
    extra: dict = field(default_factory=dict)


class Engine(ABC):
    @abstractmethod
    def evaluate(self, x: np.ndarray) -> EvalResult:
        """x: section index per group -> weight, DCRs, drift, ..."""
