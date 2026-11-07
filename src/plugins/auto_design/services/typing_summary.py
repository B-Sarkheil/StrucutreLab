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

from src.plugins.auto_design.services.fitness import ranking_key
from src.plugins.auto_design.services.population import (
    BEAM,
    COLUMN,
    HORIZONTAL_BRACE,
    VERTICAL_BRACE,
    Individual,
)

# Order of the groups on the typing page (agreed with the user).
TYPING_ORDER = (COLUMN, BEAM, VERTICAL_BRACE, HORIZONTAL_BRACE)


def best_individual(population: Sequence[Individual]) -> Individual:
    if not population:
        raise ValueError("The population is empty.")

    return min(population, key=lambda member: ranking_key(member.fitness))


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
