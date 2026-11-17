"""Auto Design - step 9.1.5: directed and random mutation of a child (no Qt, no SAP).

After the crossover a child gets two kinds of mutation, both on UNITS (a unit
is one frame or a group of linked frames, see `gene_groups.py`):

1. Directed mutation: `directedPercent` % of the units are chosen at random.
   The largest governing ratio r_gov of the unit decides how many steps the
   section moves in the strong -> weak order of the unit's allowed sections:

       r_gov <  0.5         1 step weaker       1.0 < r_gov <= 1.2   1 step stronger
       0.5 <= r_gov <= 1.0  no change           1.2 < r_gov <= 2.0   2 steps stronger
                                                r_gov > 2.0          3 steps stronger

   r_gov = max(stress ratio / DCR goal, deflection ratio) of the frame. The
   KIND of the larger one decides the order:

       deflection                      -> I33
       stress, MMajRatio is the largest -> Z33
       stress, MMinRatio is the largest -> Z22
       stress, PRatio is the largest    -> Area

   The three stress components are compared at the governing load combination
   of the frame (they come from one row of the steel design table, see
   `design_results.read_steel_flexure_ratios`). A frame without them (for
   example a concrete frame) uses Z33. On a tie the order of the list above
   wins (deflection loses to stress, then Z33, Z22, Area).
   The orders only contain the sections allowed for the unit (type of the
   frames and Material Type), so a step never leaves the allowed sections.
2. Random mutation: `randomPercent` % of the units, chosen among the units NOT
   chosen for the directed mutation, get a new random allowed section.

A child has no analysis yet, so r_gov of a unit is taken from the PARENT that
gave this unit to the child (the parent's section is the one that was checked).
"""
from __future__ import annotations

import logging
import random
from collections.abc import Sequence

from src.plugins.auto_design.services.fitness import Fitness
from src.plugins.auto_design.services.section_ordering import (
    AXIAL,
    DEFLECTION,
    MINOR,
    STRESS,
    step_section,
)

logger = logging.getLogger(__name__)


def weaker_steps(r_gov: float) -> int:
    """Steps toward weaker sections (negative = stronger) for a ratio."""

    if r_gov < 0.5:
        return 1  # cautious: only one step weaker
    if r_gov <= 1.0:  # 0.5 .. 1.0: no change
        return 0
    if r_gov <= 1.2:
        return -1
    if r_gov <= 2.0:
        return -2
    return -3


def stress_order_kind(fitness: Fitness, frame: str) -> str:
    """Order kind used when the STRESS ratio of `frame` governs: the largest of
    MMajRatio (STRESS, Z33), MMinRatio (MINOR, Z22) and PRatio (AXIAL, Area).
    On a tie the first of that list wins. STRESS (Z33) when the frame has none
    of the three."""

    candidates = (
        (fitness.majorRatios.get(frame), STRESS),
        (fitness.minorRatios.get(frame), MINOR),
        (fitness.axialRatios.get(frame), AXIAL),
    )

    best: tuple[float, str] | None = None

    for value, kind in candidates:
        if value is None:
            continue

        if best is None or value > best[0]:
            best = (value, kind)

    return best[1] if best is not None else STRESS


def unit_governing(
    unit: Sequence[str], fitness: object, dcr_goal: float
) -> tuple[float, str] | None:
    """(largest r_gov of the frames of the unit, order kind of that ratio), or
    None when the parent has no ratio for these frames. On a tie stress wins
    over deflection."""

    if not isinstance(fitness, Fitness):
        return None

    best: tuple[float, str] | None = None

    for frame in unit:
        candidates = []
        stress = fitness.stressRatios.get(frame)
        deflection = fitness.deflectionRatios.get(frame)

        if stress is not None:
            candidates.append((stress / dcr_goal, stress_order_kind(fitness, frame)))

        if deflection is not None:
            candidates.append((deflection, DEFLECTION))

        for ratio, kind in candidates:
            if best is None or ratio > best[0]:
                best = (ratio, kind)

    return best


def _count(units: int, percent: float) -> int:
    return min(units, int(units * percent / 100.0 + 0.5))


def mutate_child(
    genes: dict[str, str],
    units: Sequence[tuple[str, ...]],
    choices: Sequence[Sequence[str]],
    orders: dict[str, list[list[str]]],
    sources: Sequence[object],
    dcr_goal: float,
    directedPercent: float,
    randomPercent: float,
    rng: random.Random,
) -> dict[str, str]:
    """Genes of the child after the directed and the random mutation.

    choices : allowed sections of every unit (`gene_groups.unit_options`)
    orders  : kind -> for every unit its allowed sections, strong -> weak
              (needed only when directedPercent > 0)
    sources : for every unit the Fitness of the parent that gave it to the child
    """

    result = dict(genes)
    ids = list(range(len(units)))

    directed = rng.sample(ids, _count(len(ids), directedPercent))
    taken = set(directed)
    free = [i for i in ids if i not in taken]
    randomly = rng.sample(free, min(len(free), _count(len(ids), randomPercent)))

    moved = 0

    for i in directed:
        found = unit_governing(units[i], sources[i], dcr_goal)

        if found is None:
            continue

        ratio, kind = found
        steps = weaker_steps(ratio)

        if steps == 0:
            continue

        new = step_section(orders[kind][i], result[units[i][0]], steps)

        if new is None or new == result[units[i][0]]:
            continue

        for frame in units[i]:
            result[frame] = new

        moved += 1

    for i in randomly:
        current = result[units[i][0]]
        options = [s for s in choices[i] if s != current] or list(choices[i])
        new = rng.choice(options)

        for frame in units[i]:
            result[frame] = new

    logger.info(
        "Mutation: %d directed units chosen (%d changed), %d random units",
        len(directed), moved, len(randomly),
    )

    return result
