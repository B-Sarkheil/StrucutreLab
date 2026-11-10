"""Parameters collected by the Auto Design wizard.

Field names follow the project's naming (camelCase) on purpose, so the
same names are used from the form down to the GA code.

The SAP2000 reference file is chosen in step 1 and is kept by the
wizard (`AutoDesignWizard.sap_path`); it is not part of the GA settings.
The tolerance used to detect beams / columns / braces belongs to the
"Frame types" page, not to the GA settings; the result of that
page (frame -> role) is kept by the wizard (`AutoDesignWizard.frame_roles`).
The values of the "Constraint settings" page (step 4.2, before the GA settings,
step 4.3) are kept by the wizard as `AutoDesignWizard.constraints`
(`ConstraintParams`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstraintParams:
    """Validated values of the Constraint settings page (step 4.2)."""

    dcrGoal: float = 1.0  # DCR Goal, > 0 (the stress ratio limit)
    deflectionDivisor: int = 300  # n of the deflection goal L / n, > 0
    elementCoefficient: float = 1.0  # Element Constraint Coefficient (DCR and Deflection), > 0
    generalCoefficient: float = 1.0  # General Constraint Coefficient (Drift), > 0
    deflectionCombo: str = ""  # load combination of the deflection check
    updateSeismicLoads: bool = False  # update the seismic loads of every offspring model


@dataclass(frozen=True)
class AutoDesignParams:
    """Validated values of the GA settings form (step 4.2)."""

    popSize: int  # population size, > 0
    tournamentSize: int  # tournament selection size, 2..popSize
    genSize: int  # number of generations, > 0
    mutationPercent: float  # mutation percent, 0..100
    #penalizeLevel: float  # penalty coefficient k, > 0
    modelsFolder: str = ""  # database folder where the models of every generation are saved


@dataclass(frozen=True)
class SectionPermission:
    """One row of the sections table (step 2)."""

    name: str  # section name in the SAP2000 model
    allowedForColumn: bool = False
    allowedForBeam: bool = False
    allowedForHorizontalBrace: bool = False
    allowedForVerticalBrace: bool = False
    # SAP2000 Material Type of the section's material, as SAP names it
    # (Steel, Concrete, Other, ...). Filled at the start of the run
    # (step 5); not shown in the table and not part of the Excel file.
    materialType: str = ""
