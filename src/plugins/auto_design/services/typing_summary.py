"""Auto Design - step 10: numbers behind the typing page (no Qt, no SAP).

* `best_individual`: the best member of a population by the GA ranking
  (`fitness.ranking_key`, smaller = better). After the run it is the
  selected member; it does not rely on the list being sorted (with
  `genSize = 1` the initial population is not sorted).
* `sections_by_role`: for every role, the sections used by the member and
  how many frames have each of them.
* `weight_change_percent`: weight of the member against the reference.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from src.plugins.auto_design.services.fitness import CV_EPSILON, selection_key
from src.plugins.auto_design.services.population import (
    BEAM,
    COLUMN,
    HORIZONTAL_BRACE,
    VERTICAL_BRACE,
    Individual,
)
from dataclasses import dataclass

# Order of the groups on the typing page (agreed with the user).
TYPING_ORDER = (COLUMN, BEAM, VERTICAL_BRACE, HORIZONTAL_BRACE)


def best_individual(population: Sequence[Individual]) -> Individual:
    if not population:
        raise ValueError("The population is empty.")

    return min(population, key=lambda member: selection_key(member))


def _natural_key(name: str) -> list:
    # "IPE200" < "IPE1000"; text and numbers always sit at the same positions.
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def sections_by_role(
    genes: dict[str, str], roles: dict[str, str]
) -> dict[str, list[tuple[str, int]]]:
    """role -> [(section, number of frames), ...] sorted by section name.
    Every role of `TYPING_ORDER` is present (an empty list when unused)."""

    counters: dict[str, Counter] = {role: Counter() for role in TYPING_ORDER}

    for frame, section in genes.items():
        counters[roles[frame]][section] += 1

    return {
        role: sorted(counter.items(), key=lambda item: _natural_key(item[0]))
        for role, counter in counters.items()
    }


def weight_change_percent(weight: float, reference_weight: float) -> float | None:
    """(weight - reference) / reference * 100; None without a usable reference."""

    if not reference_weight:
        return None

    return (weight - reference_weight) / reference_weight * 100.0


# Verdicts of `weight_change` (the UI maps them to colors).
BETTER = "better"
WORSE = "worse"
NEUTRAL = "neutral"  # the weight is not comparable (feasibility changed)
SAME = "same"


@dataclass(frozen=True)
class WeightChange:
    percent: float | None  # weight change against the base member, in percent
    verdict: str  # BETTER, WORSE, NEUTRAL or SAME
    note: str  # short explanation, "" when the plain percent says it all


def weight_change(
    weight: float,
    cv: float,
    base_weight: float,
    base_cv: float,
    epsilon: float = CV_EPSILON,
) -> WeightChange:
    """Compare a member with the base member (the best of generation 1) taking
    the constraints into account: a heavier member that satisfies the
    constraints is not worse than a lighter one that violates them.

    * both feasible        : the weight decides (lighter = better),
    * base infeasible, now feasible : NEUTRAL (the extra weight pays for the constraints),
    * both infeasible      : the CV decides (smaller = better),
    * base feasible, now infeasible : WORSE.
    """

    percent = weight_change_percent(weight, base_weight)
    feasible = cv <= epsilon
    base_feasible = base_cv <= epsilon

    if feasible and base_feasible:
        if percent is None or abs(percent) <= 1e-9:
            return WeightChange(percent, SAME, "")

        return WeightChange(percent, BETTER if percent < 0 else WORSE, "")

    if feasible:
        return WeightChange(percent, NEUTRAL, "feasible now, start was not")

    if base_feasible:
        return WeightChange(percent, WORSE, "violates constraints")

    note = f"still infeasible: CV {cv:.3g} vs {base_cv:.3g}"

    if abs(cv - base_cv) <= 1e-9:
        return WeightChange(percent, SAME, note)

    return WeightChange(percent, BETTER if cv < base_cv else WORSE, note)
