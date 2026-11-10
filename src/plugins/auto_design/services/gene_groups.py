"""Auto Design - step 4.1 (data), 8 and 9: linked frames = genes that are one (no Qt, no SAP).

The user can link two or more frames on the "Linked frames" page (step 4.1):
all the frames of a group always get THE SAME section. For the algorithm a
group is ONE gene. The DNA of a member is therefore a list of "units":

    unit = tuple of frame names that share one gene
           (a frame that is not linked is a unit of one frame)

* `normalize_links`   cleans the groups given by the page (unknown frames,
                      groups of one frame, groups that share a frame are merged),
* `build_units`       the units in DNA order (a group sits at the place of its
                      first frame in the SAP table order),
* `unit_options`      the sections allowed for a unit = the sections allowed
                      for EVERY frame of it (same Material Type, allowed for the
                      role of every frame); an empty result is an error,
* `random_unit_genes` one random section per unit, given to all its frames,
* `repair_genes`      makes the reference model respect the links (member 1).

Crossover (`genetic_operators.three_point_crossover`) works on the units, so
a child always keeps the links of its parents.
"""
from __future__ import annotations

import random
from collections.abc import Iterable, Sequence

Unit = tuple[str, ...]


def normalize_links(frames: Iterable[str], links: Iterable[Iterable[str]]) -> list[Unit]:
    """Valid groups: frames that exist, at least two frames, and no frame in
    two groups (groups that share a frame are merged). Frames of a group are
    in DNA order and the groups are ordered by their first frame."""

    order = {frame: index for index, frame in enumerate(frames)}
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]

        return item

    for group in links:
        known = [frame for frame in dict.fromkeys(group) if frame in order]

        for frame in known:
            parent.setdefault(frame, frame)

        for frame in known[1:]:
            parent[find(frame)] = find(known[0])

    buckets: dict[str, list[str]] = {}

    for frame in parent:
        buckets.setdefault(find(frame), []).append(frame)

    groups = [
        tuple(sorted(members, key=order.__getitem__))
        for members in buckets.values()
        if len(members) >= 2
    ]
    groups.sort(key=lambda group: order[group[0]])

    return groups


def build_units(frames: Iterable[str], links: Iterable[Iterable[str]]) -> list[Unit]:
    """The DNA: one unit per group and one per frame that is not linked, in
    the order of `frames` (a group is placed where its first frame is)."""

    frames = list(frames)
    group_of: dict[str, Unit] = {}

    for group in normalize_links(frames, links):
        for frame in group:
            group_of[frame] = group

    units: list[Unit] = []

    for frame in frames:
        group = group_of.get(frame)

        if group is None:
            units.append((frame,))
        elif group[0] == frame:
            units.append(group)

    return units


def unit_options(
    units: Sequence[Unit], options: dict[str, list[str]]
) -> list[list[str]]:
    """Sections allowed for every unit (same order as `units`): the sections
    that are allowed for every frame of the unit. Raises ValueError (all
    problems together) when a group has no common section."""

    result: list[list[str]] = []
    problems: list[str] = []

    for unit in units:
        common = list(options[unit[0]])

        for frame in unit[1:]:
            allowed = set(options[frame])
            common = [section for section in common if section in allowed]

        if not common:
            shown = ", ".join(unit[:4]) + (", ..." if len(unit) > 4 else "")
            problems.append(f"frames {shown} ({len(unit)} frames)")

        result.append(common)

    if problems:
        shown = "; ".join(problems[:5])
        more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
        raise ValueError(
            "These linked frames have no section that is allowed for all of them "
            f"(check their types, their Material Types and the allowed sections): {shown}{more}."
        )

    return result


def random_unit_genes(
    units: Sequence[Unit], choices: Sequence[Sequence[str]], rng: random.Random
) -> dict[str, str]:
    """One random section for every unit, given to all the frames of the unit."""

    genes: dict[str, str] = {}

    for unit, allowed in zip(units, choices):
        section = rng.choice(allowed)

        for frame in unit:
            genes[frame] = section

    return genes


def repair_genes(
    genes: dict[str, str],
    units: Sequence[Unit],
    choices: Sequence[Sequence[str]],
    areas: dict[str, float],
) -> dict[str, str]:
    """Genes that respect the links, from genes that may not (used for the
    reference model, member 1 of generation 1).

    A group whose frames already have one section is left as it is. Otherwise
    the section with the largest area among the sections the group has now
    (and that are allowed for the whole group) is given to all its frames; if
    none of them is allowed, the smallest allowed section that is not smaller
    than the largest current one (or the largest allowed one) is used.
    A section without an area counts as 0.
    """

    result = dict(genes)

    def area(section: str) -> float:
        return areas.get(section, 0.0)

    for unit, allowed in zip(units, choices):
        if len(unit) < 2:
            continue

        current = list(dict.fromkeys(genes[frame] for frame in unit))

        if len(current) == 1:
            continue

        usable = [section for section in current if section in set(allowed)]

        if usable:
            best = max(usable, key=area)
        else:
            need = max(area(section) for section in current)
            bigger = [section for section in allowed if area(section) >= need]
            best = min(bigger, key=area) if bigger else max(allowed, key=area)

        for frame in unit:
            result[frame] = best

    return result
