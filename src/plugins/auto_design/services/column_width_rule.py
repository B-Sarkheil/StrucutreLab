"""Auto Design - steps 8.0 and 9.1.6: column width / height rule (no Qt, no SAP calls of its own).

Rule: a column must be at least as wide as the flange of every beam that is
connected to it. Beams are connected to a column at a joint of the column
(the columns are divided where the beams are). The rule is applied to the
COLUMN, never to the beam.

Beam side (decided from the local axes of the column, see `beam_side`):

* beam along local axis 2 of the column -> it meets the FLANGE of the column:
      t2 (flange width) of the column >= t2 (flange width) of the beam
* beam along local axis 3 of the column -> it meets the WEB of the column:
      t3 (depth) of the column >= t2 (flange width) of the beam
* an oblique beam: the larger component of its direction decides.

Sections without t2 / t3 (pipes, auto select lists ...) are ignored. Concrete
sections have t2 and t3 and are included. Equality is allowed.

Step 8.0 (`prune_beam_options`): a beam section whose flange width is larger
than the largest dimension (t2 or t3) of every section allowed for columns can
never be satisfied by any column, so it is removed from the beam options. The
column options are never reduced and the beam options are not reduced by
anything else.

Step 9.1.6 (`repair_columns`): after the crossover and the mutations of a
child, every column unit that breaks the rule gets the first section (by
ascending area) that passes the rule and has a larger area than the current
one; when none is larger, the smallest passing section is used.

`count_violations` counts the column frames that break the rule (used to rank
the members: a member with a violation is behind every member without one).
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.population import BEAM, COLUMN
from src.plugins.auto_design.services.sap_tables import pick_field
from src.plugins.auto_design.services.section_materials import SECTION_TABLE

logger = logging.getLogger(__name__)

SIDE_FLANGE = "flange"
SIDE_WEB = "web"

_EPS = 1e-9

# section name -> (t3, t2): depth and flange width, in the model units (m)
Dims = dict[str, tuple[float, float]]


@dataclass(frozen=True)
class ColumnRule:
    """Everything the rule needs, computed once in step 8.0."""

    columns: frozenset[str]  # every frame of role Column
    links: dict[str, tuple[tuple[str, str], ...]]  # column -> ((beam, SIDE_*), ...)
    dims: Dims
    areas: dict[str, float]


# ---------------------------------------------------------------------
# Section dimensions
# ---------------------------------------------------------------------


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def read_section_dimensions(client: SapClient) -> Dims:
    """Section name -> (t3, t2) from `Frame Section Properties 01 - General`.
    A section with a missing or non-positive t2 or t3 is left out."""

    result: Dims = {}

    for row in client.read_table(SECTION_TABLE):
        name = pick_field(row, "SectionName", SECTION_TABLE)
        t3 = _number(pick_field(row, "t3", SECTION_TABLE))
        t2 = _number(pick_field(row, "t2", SECTION_TABLE))

        if t3 is not None and t2 is not None and t3 > 0.0 and t2 > 0.0:
            result[name] = (t3, t2)

    return result


# ---------------------------------------------------------------------
# Geometry: which side of the column does a beam meet
# ---------------------------------------------------------------------

Vector = tuple[float, float, float]


def _sub(a: Vector, b: Vector) -> Vector:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vector, b: Vector) -> Vector:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _scale(a: Vector, k: float) -> Vector:
    return (a[0] * k, a[1] * k, a[2] * k)


def _unit(a: Vector) -> Vector:
    length = math.sqrt(_dot(a, a))

    return _scale(a, 1.0 / length) if length > 0.0 else a


def beam_side(
    column_i: Vector, column_j: Vector, angle_deg: float, beam_direction: Vector
) -> str:
    """SIDE_FLANGE when the beam runs (mostly) along local axis 2 of the
    column, else SIDE_WEB.

    Local axes of a vertical column (SAP2000, simple axes): axis 1 goes from
    joint I to joint J; with Ang = 0 axis 2 is +X and axis 3 = axis 1 x axis 2;
    Ang rotates axes 2 and 3 about axis 1 (right-hand rule).
    `beam_direction` is the vector from the shared joint to the other end of
    the beam.
    """

    u1 = _unit(_sub(column_j, column_i))
    x_axis: Vector = (1.0, 0.0, 0.0)
    base = _sub(x_axis, _scale(u1, _dot(x_axis, u1)))

    if _dot(base, base) < 1e-12:  # not expected for a column
        base = (0.0, 1.0, 0.0)

    base = _unit(base)
    angle = math.radians(angle_deg)
    axis2 = _unit(
        (
            *(
                math.cos(angle) * b + math.sin(angle) * r
                for b, r in zip(base, _cross(u1, base))
            ),
        )
    )
    axis3 = _cross(u1, axis2)

    along_2 = abs(_dot(beam_direction, axis2))
    along_3 = abs(_dot(beam_direction, axis3))

    return SIDE_FLANGE if along_2 >= along_3 else SIDE_WEB


def build_column_links(
    roles: dict[str, str],
    connectivity: dict[str, tuple[str, str]],
    coordinates: dict[str, Vector],
    read_axes: Callable[[str], tuple[float, bool]],
) -> dict[str, tuple[tuple[str, str], ...]]:
    """Column -> ((beam, side), ...) for every column that has beams at one of
    its two joints. `read_axes(frame)` gives (Ang in degrees, Advanced flag).
    Columns with advanced local axes are not supported: ValueError."""

    beams_at: dict[str, list[str]] = {}

    for frame, role in roles.items():
        if role == BEAM and frame in connectivity:
            for joint in connectivity[frame]:
                beams_at.setdefault(joint, []).append(frame)

    result: dict[str, tuple[tuple[str, str], ...]] = {}
    advanced: list[str] = []

    for frame, role in roles.items():
        if role != COLUMN or frame not in connectivity:
            continue

        joint_i, joint_j = connectivity[frame]

        if joint_i not in coordinates or joint_j not in coordinates:
            continue

        found = [(beam, joint) for joint in (joint_i, joint_j) for beam in beams_at.get(joint, [])]

        if not found:
            continue

        angle, is_advanced = read_axes(frame)

        if is_advanced:
            advanced.append(frame)
            continue

        links: list[tuple[str, str]] = []

        for beam, joint in found:
            beam_i, beam_j = connectivity[beam]
            other = beam_j if beam_i == joint else beam_i

            if other not in coordinates:
                continue

            direction = _sub(coordinates[other], coordinates[joint])
            links.append(
                (beam, beam_side(coordinates[joint_i], coordinates[joint_j], angle, direction))
            )

        if links:
            result[frame] = tuple(links)

    if advanced:
        shown = ", ".join(advanced[:10]) + (" ..." if len(advanced) > 10 else "")
        raise ValueError(
            f"{len(advanced)} column(s) have advanced local axes, which the column width / "
            f"height rule does not support: {shown}. Switch the rule off on the "
            "Constraint settings page or change those local axes."
        )

    return result


# ---------------------------------------------------------------------
# Step 8.0: pruning of the beam options
# ---------------------------------------------------------------------


def prune_beam_options(
    options: dict[str, list[str]],
    roles: dict[str, str],
    dims: Dims,
    column_sections: Sequence[str],
) -> tuple[dict[str, list[str]], int]:
    """Beam options without the sections whose flange width is larger than
    the largest t2 / t3 of the sections allowed for columns. Returns the new
    options and the number of removed (frame, section) pairs. Other frames
    are not touched. ValueError when a beam is left with no section."""

    sizes = [max(dims[s]) for s in column_sections if s in dims]

    if not sizes:
        return options, 0

    limit = max(sizes)
    result: dict[str, list[str]] = {}
    removed = 0
    empty: list[str] = []

    for frame, choices in options.items():
        if roles.get(frame) != BEAM:
            result[frame] = choices
            continue

        kept = [s for s in choices if s not in dims or dims[s][1] <= limit + _EPS]
        removed += len(choices) - len(kept)

        if not kept:
            empty.append(frame)

        result[frame] = kept

    if empty:
        shown = ", ".join(empty[:10]) + (" ..." if len(empty) > 10 else "")
        raise ValueError(
            "Column width / height rule: every section allowed for these beams is wider than "
            f"the widest section allowed for columns ({limit:.4g} m): {shown}. "
            "Allow wider column sections or narrower beam sections."
        )

    return result, removed


# ---------------------------------------------------------------------
# Check and repair
# ---------------------------------------------------------------------


def _passes(dims: tuple[float, float], need_flange: float, need_web: float) -> bool:
    t3, t2 = dims

    return t2 >= need_flange - _EPS and t3 >= need_web - _EPS


def column_requirement(
    column: str, genes: dict[str, str], rule: ColumnRule
) -> tuple[float, float]:
    """(minimum t2, minimum t3) the column section must have, from the
    sections the beams of this column have in `genes`."""

    need_flange = need_web = 0.0

    for beam, side in rule.links.get(column, ()):
        beam_dims = rule.dims.get(genes.get(beam, ""))

        if beam_dims is None:
            continue

        width = beam_dims[1]

        if side == SIDE_FLANGE:
            need_flange = max(need_flange, width)
        else:
            need_web = max(need_web, width)

    return need_flange, need_web


def count_violations(genes: dict[str, str], rule: ColumnRule) -> int:
    """Number of column frames that break the rule."""

    count = 0

    for column in rule.links:
        column_dims = rule.dims.get(genes.get(column, ""))

        if column_dims is None:
            continue

        need_flange, need_web = column_requirement(column, genes, rule)

        if not _passes(column_dims, need_flange, need_web):
            count += 1

    return count


def repair_columns(
    genes: dict[str, str],
    units: Sequence[tuple[str, ...]],
    choices: Sequence[Sequence[str]],
    rule: ColumnRule,
) -> tuple[dict[str, str], int]:
    """Step 9.1.6: genes after the repair and the number of units changed.

    Only units made of columns only are repaired (a unit that mixes columns
    with other frames is left as it is). The requirement of a unit is the
    largest one of its frames; the new section is the first one, by ascending
    area, that passes and has a larger area than the current one, else the
    smallest one that passes. A unit with no passing section is left as it is.
    """

    result = dict(genes)
    changed = 0

    def area(section: str) -> float:
        return rule.areas.get(section, 0.0)

    for unit, allowed in zip(units, choices):
        if not all(frame in rule.columns for frame in unit):
            continue

        current = result[unit[0]]
        current_dims = rule.dims.get(current)

        if current_dims is None:
            continue

        need_flange = need_web = 0.0

        for frame in unit:
            flange, web = column_requirement(frame, result, rule)
            need_flange, need_web = max(need_flange, flange), max(need_web, web)

        if _passes(current_dims, need_flange, need_web):
            continue

        passing = [
            s
            for s in allowed
            if s in rule.dims and _passes(rule.dims[s], need_flange, need_web)
        ]

        if not passing:
            continue

        passing.sort(key=lambda s: (area(s), s))
        larger = [s for s in passing if area(s) > area(current)]
        new = larger[0] if larger else passing[0]

        for frame in unit:
            result[frame] = new

        changed += 1

    return result, changed
