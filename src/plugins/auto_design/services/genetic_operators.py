"""Auto Design - genetic operators of the generation loop (no Qt, no SAP).

Step 9.1.1 / 9.1.2  `tournament_parents`: tournament selection of two parents.
Step 9.1.3          `random_cut_points`: three different random cut points.
Step 9.1.4          `three_point_crossover`: two children from two parents.
Step 9.2            `select_survivors`: the best members of parents + children.

Ranking: the operators take a function `rank(individual)` that returns a
sortable key, and a SMALLER key is a BETTER member (see
`fitness.ranking_key`: feasible members by weight, then infeasible ones by
CV). The operators do not know what the key is made of.

The DNA of a member is a list of UNITS (see `gene_groups.build_units`): a
unit is the tuple of the frames that share one gene (frames linked on the
"Linked frames" page), or one single frame. The number of genes used for the
cut points is the number of UNITS, not the number of frames. A plain list of
frame names is accepted too (every frame is then its own unit).
Everything here works on plain data, so it can be tested without SAP2000.
"""
from __future__ import annotations

import random
from collections.abc import Callable, Sequence

from src.plugins.auto_design.services.population import Individual

# smaller = better
Rank = Callable[[Individual], object]


def tournament_parents(
    population: Sequence[Individual],
    tournamentSize: int,
    rng: random.Random,
    rank: Rank,
) -> tuple[Individual, Individual]:
    """Steps 9.1.1 and 9.1.2.

    `tournamentSize` DIFFERENT members are drawn at random from the
    population (a member cannot be drawn twice), and the two with the
    best (smallest) `rank` are the parents. Ties keep the order of the draw.
    """

    if tournamentSize < 2:
        raise ValueError(
            "Tournament Size must be at least 2: two parents are needed."
        )

    if tournamentSize > len(population):
        raise ValueError(
            f"Tournament Size ({tournamentSize}) is larger than the "
            f"population ({len(population)})."
        )

    drawn = rng.sample(list(population), tournamentSize)
    ranked = sorted(drawn, key=rank)  # stable sort, best first

    return ranked[0], ranked[1]


def select_survivors(
    pool: Sequence[Individual],
    rank: Rank,
    count: int,
) -> list[Individual]:
    """Step 9.2: the `count` members of `pool` with the best (smallest)
    `rank`, best first. On equal ranks the member that comes first in
    `pool` wins (so put the parents before the children).
    """

    if count > len(pool):
        raise ValueError(f"Cannot keep {count} members out of {len(pool)}.")

    return sorted(pool, key=rank)[:count]  # stable sort


def random_cut_points(geneCount: int, rng: random.Random) -> tuple[int, int, int]:
    """Step 9.1.3: three different numbers between 1 and `geneCount` (the
    number of UNITS of the DNA, not of frames), returned in increasing order.

    Cut point c means: genes 1..c stay before the cut, gene c+1 is the
    first one after it (so the last part is empty when c3 == geneCount).
    """

    if geneCount < 3:
        raise ValueError(
            f"Three-point crossover needs at least 3 genes, got {geneCount} "
            "(linked frames count as one gene)."
        )

    c1, c2, c3 = sorted(rng.sample(range(1, geneCount + 1), 3))

    return c1, c2, c3


def three_point_crossover(
    units: Sequence[str | Sequence[str]],
    genesA: dict[str, str],
    genesB: dict[str, str],
    cuts: tuple[int, int, int],
) -> tuple[dict[str, str], dict[str, str]]:
    """Step 9.1.4: both parents are cut into four parts at `cuts`; the
    parts are swapped two by two:

        child 1 = A1 B2 A3 B4        child 2 = B1 A2 B3 A4

    `units` is the DNA order: every item is the tuple of the frames of one
    gene (or one frame name). All the frames of a unit come from the SAME
    parent, so linked frames stay equal in the children. Genes are
    frame -> section.
    """

    child1: dict[str, str] = {}
    child2: dict[str, str] = {}

    for index, unit in enumerate(units):
        position = index + 1  # genes are numbered from 1
        part = sum(position > cut for cut in cuts)  # 0, 1, 2 or 3 (= part 1..4)
        swap = part % 2 == 1  # parts 2 and 4 are exchanged
        members = (unit,) if isinstance(unit, str) else unit

        for frame in members:
            child1[frame] = genesB[frame] if swap else genesA[frame]
            child2[frame] = genesA[frame] if swap else genesB[frame]

    return child1, child2
