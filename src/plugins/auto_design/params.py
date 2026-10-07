"""Parameters collected by the Auto Design form.

Field names follow the project's naming (camelCase) on purpose, so the
same names are used from the form down to the GA code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutoDesignParams:
    """Validated values of the Auto Design form."""

    popSize: int  # population size, > 0
    tournamentSize: int  # tournament selection size, > 0
    genSize: int  # number of generations, > 0
    mutationPercent: float  # mutation percent, 0..100
    penalizeLevel: float  # penalty coefficient k, > 0
    tolerance: float  # beam/column detection tolerance (cm), > 0
    sapPath: str  # path of the SAP2000 reference file


@dataclass(frozen=True)
class SectionPermission:
    """One row of the sections table (step 2)."""

    name: str  # section name in the SAP2000 model
    allowedForColumn: bool = False
    allowedForBeam: bool = False
    allowedForBrace: bool = False
