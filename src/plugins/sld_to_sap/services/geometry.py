"""CAD (mm) to model (m) conversion (docs section 2)."""
from __future__ import annotations

import math


def round_mm(x: float) -> float:
    """Round to 3 decimals, halves away from zero (MATLAB `round`, not Python's)."""
    if x == 0:
        return 0.0
    return math.copysign(math.floor(abs(x) * 1000 + 0.5) / 1000, x)


def to_model(
    kind: str,
    cx: float,
    cy: float,
    ox: float,
    oy: float,
    v: float,
    z0: float,
) -> tuple[float, float, float]:
    """Model (X, Y, Z) in metres of a CAD point; all inputs already in metres.

    `kind` is "x", "y" or "z"; `v` is the value next to the origin mark (or the
    explicit value of a point, which replaces the coordinate normal to the sheet).
    """
    if kind == "x":
        return v, round_mm(cx - ox), round_mm(cy - oy + z0)
    if kind == "y":
        return round_mm(cx - ox), v, round_mm(cy - oy + z0)
    return round_mm(cx - ox), round_mm(cy - oy), v
