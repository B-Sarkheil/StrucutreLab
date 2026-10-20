"""User inputs of the SLD to SAP tool (see docs/sld_to_sap_algorithm.md, section 4)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SldParams:
    """Numeric inputs. Lengths ending in `_mm` are millimetres, `z0` is metres."""

    z0: float  # real level (model, m) of the origin point in X / Y elevation files
    tolerance_mm: float = 10.0  # "on one line / plane" test (perpendicular to the beam)
    end_tolerance_mm: float = 5.0  # load may stick out of the beam ends by this much
    eqz_coef: float = 0.2  # vertical earthquake coefficient (0.2 * Sds, ASCE 7-10)
    friction_coef: float = 0.15  # pipe / beam friction

    @property
    def tol(self) -> float:
        """`tolerance` in metres."""
        return 0.001 * self.tolerance_mm

    @property
    def end_tol(self) -> float:
        """`endTolerance` in metres."""
        return 0.001 * self.end_tolerance_mm
