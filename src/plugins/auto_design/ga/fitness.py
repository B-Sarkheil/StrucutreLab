"""Penalty fitness: W * (1 + k * sum(max(0, DCR - 1)))."""
from __future__ import annotations

import numpy as np


def fitness(weight: float, dcr: np.ndarray, k: float = 10.0) -> float:
    return weight * (1.0 + k * float(np.sum(np.maximum(0.0, dcr - 1.0))))
