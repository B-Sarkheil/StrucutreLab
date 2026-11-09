"""Auto Design - fitness of one model (no Qt); used by steps 8 and 9.

`fitness_calculator` runs the analysis and the design of the open SAP2000
model and returns a `Fitness`: the weight W and the constraint violation CV.

CV:

    r_i_gov = max(r_i_stress / DCR_goal, r_i_deflection)   governing ratio of element i

    v_e = mean_i  max(0, r_i_gov - 1)          element constraints
    v_d = mean_j  max(0, r_j_drift - 1)        global constraints (later drift)

    CV  = w_e * v_e + w_d * v_d (+ ...)        w_e = Element Constraint Coefficient, w_d = General Constraint Coefficient (step 4.1)
                                               

The numbers shown to the user are NOT the governing ones: `meanRatio` /
`maxRatio` are the stress ratios only, `meanDeflection` / `maxDeflection` the
beam deflection ratios only.

To add a constraint:

* element constraint (one ratio per frame): write a reader `f(sap) -> {frame: ratio}`
  and merge it in `fitness_calculator` with the others (`governing_ratios`);
* global constraint (one ratio per story, ...): write a reader
  `f(sap) -> [ratio, ...]`, add it to `GLOBAL_CONSTRAINTS` under a name and
  give that name a weight in `CvWeights.globalWeights`.

Ranking (`ranking_key`): members with CV <= CV_EPSILON are feasible and come
first, ordered by W (lighter is better); the others come after them, ordered
by CV (smaller is better). A smaller key is a better member.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from src.core.sap_client import SapClient, SapError
from src.plugins.auto_design.services.deflection import (
    DeflectionSettings,
    read_deflection_ratios,
)
from src.plugins.auto_design.services.design_results import (
    read_stress_ratios,
    read_total_weight,
)

logger = logging.getLogger(__name__)

# A member with CV not larger than this is feasible.
CV_EPSILON = 1e-6

# list of ratios (one per story, joint, ...)
GlobalReader = Callable[[SapClient], list[float]]

GLOBAL_CONSTRAINTS: dict[str, GlobalReader] = {}  # for example {"drift": read_drift_ratios}


@dataclass(frozen=True)
class CvWeights:
    """Weights of the terms of CV (w_e, w_d, ...). A global constraint
    without an entry in `globalWeights` gets weight 1."""

    element: float = 1.0
    globalWeights: dict[str, float] = field(default_factory=lambda: {"drift": 1.0})


@dataclass(frozen=True)
class Fitness:
    """Result of `fitness_calculator`."""

    weight: float  # W (kg: the model is in kgf-m-C)
    cv: float  # constraint violation, 0 = no violation
    elementViolation: float  # v_e
    globalViolations: dict[str, float]  # name -> v of every global constraint
    meanRatio: float  # mean STRESS ratio of the frames
    maxRatio: float  # largest STRESS ratio
    elementCount: int  # number of frames with a stress ratio
    meanDeflection: float = 0.0  # mean deflection ratio of the beams (0 = not used)
    maxDeflection: float = 0.0  # largest deflection ratio of the beams
    deflectionCount: int = 0  # number of beams with a deflection ratio


# ---------------------------------------------------------------------
# CV (pure functions: no SAP)
# ---------------------------------------------------------------------


def governing_ratios(parts: Iterable[dict[str, float]]) -> dict[str, float]:
    """r_i_gov: the largest ratio of every element over all element constraints."""

    result: dict[str, float] = {}

    for part in parts:
        for element, ratio in part.items():
            if ratio > result.get(element, float("-inf")):
                result[element] = ratio

    return result


def mean_violation(ratios: Iterable[float]) -> float:
    """mean of max(0, r - 1); 0 for an empty list."""

    values = list(ratios)

    if not values:
        return 0.0

    return sum(max(0.0, r - 1.0) for r in values) / len(values)


def compute_cv(
    elementRatios: dict[str, float],
    globalRatios: dict[str, list[float]],
    weights: CvWeights,
) -> tuple[float, float, dict[str, float]]:
    """(CV, v_e, {name: v}) from the governing element ratios and the
    global ratios of every global constraint."""

    element_violation = mean_violation(elementRatios.values())
    global_violations = {name: mean_violation(r) for name, r in globalRatios.items()}

    cv = weights.element * element_violation + sum(
        weights.globalWeights.get(name, 1.0) * v for name, v in global_violations.items()
    )

    return cv, element_violation, global_violations


# ---------------------------------------------------------------------
# Fitness of a SAP2000 model
# ---------------------------------------------------------------------


def fitness_calculator(
    sap: SapClient,
    sap_path: Path,
    weights: CvWeights | None = None,
    deflection: DeflectionSettings | None = None,
    dcr_goal: float = 1.0,
) -> Fitness:
    """Evaluate the SAP2000 model at `sap_path` (it is the open model, already saved).

    Runs the analysis and the steel and concrete design, reads W and CV,
    and saves the model again so the file keeps the results. With
    `deflection` the beams also get a deflection ratio (the output stations
    of the beams are set first; this needs the model unlocked).
    """

    weights = weights or CvWeights()
    if not dcr_goal > 0.0:
        raise ValueError(f"DCR goal must be positive (got {dcr_goal}).")
    use_deflection = deflection is not None and bool(deflection.beams)

    if use_deflection:
        sap.unlock_model()

        for beam in deflection.beams:
            sap.set_output_stations(beam, deflection.segments)

    sap.run_analysis()  # raises SapError when it fails

    if not sap.run_steel_design():
        logger.warning("Steel design returned an error code (%s)", sap_path)

    if not sap.run_concrete_design():
        logger.warning("Concrete design returned an error code (%s)", sap_path)

    weight = read_total_weight(sap)

    stress_ratios = read_stress_ratios(sap)
    deflection_ratios = read_deflection_ratios(sap, deflection) if use_deflection else {}

    # The stress ratio is divided by the DCR goal BEFORE it is compared with the
    # deflection ratio (whose goal is already L / n, so its limit is 1.0).
    scaled_stress = {frame: ratio / dcr_goal for frame, ratio in stress_ratios.items()}
    element_ratios = governing_ratios([scaled_stress, deflection_ratios])
    
    global_ratios = {name: reader(sap) for name, reader in GLOBAL_CONSTRAINTS.items()}

    cv, element_violation, global_violations = compute_cv(element_ratios, global_ratios, weights)

    if not (math.isfinite(weight) and math.isfinite(cv)):
        raise SapError(f"Weight or CV is not a finite number (W={weight}, CV={cv}).")

    stress = list(stress_ratios.values())
    bending = list(deflection_ratios.values())

    fitness = Fitness(
        weight=weight,
        cv=cv,
        elementViolation=element_violation,
        globalViolations=global_violations,
        meanRatio=sum(stress) / len(stress) if stress else 0.0,
        maxRatio=max(stress, default=0.0),
        elementCount=len(stress),
        meanDeflection=sum(bending) / len(bending) if bending else 0.0,
        maxDeflection=max(bending, default=0.0),
        deflectionCount=len(bending),
    )

    sap.save_model_as(sap_path)  # keep the analysis and design results in the file

    logger.info(
        "Fitness %s: W=%.6g, CV=%.6g, max stress %.3f, max deflection %.3f",
        Path(sap_path).name, fitness.weight, fitness.cv, fitness.maxRatio, fitness.maxDeflection,
    )

    return fitness


# ---------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------


def is_feasible(fitness: Fitness, epsilon: float = CV_EPSILON) -> bool:
    return fitness.cv <= epsilon


def ranking_key(fitness: object | None, epsilon: float = CV_EPSILON) -> tuple[int, float]:
    """Sort key: a SMALLER key is a BETTER member.

    (0, W) for a feasible member (CV <= epsilon), (1, CV) for the others,
    so every feasible member is ahead of every infeasible one.
    """

    if not isinstance(fitness, Fitness):
        raise ValueError(
            f"The fitness of a member is not a Fitness object (got {fitness!r})."
        )

    if is_feasible(fitness, epsilon):
        return (0, fitness.weight)

    return (1, fitness.cv)