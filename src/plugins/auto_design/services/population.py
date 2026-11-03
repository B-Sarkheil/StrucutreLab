"""Auto Design - step 8: building blocks of the initial population (no Qt).

Frame roles (rule of `classify_frame`), the sections allowed for every
frame (same material as the reference section, allowed for the frame's
role) and the random genes of one population member.

The roles are computed ONCE, for the reference model, on the "Frame
types" page of the wizard (the user may change them there); the run
only reads them (`GAContext.frameRoles`).
"""
from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.plugins.auto_design.params import SectionPermission

COLUMN = "column"
BEAM = "beam"
HORIZONTAL_BRACE = "horizontalBrace"
VERTICAL_BRACE = "verticalBrace"

# display order of the roles (page combo box, counters)
ROLES = (COLUMN, BEAM, HORIZONTAL_BRACE, VERTICAL_BRACE)

ROLE_LABELS = {
    COLUMN: "Column",
    BEAM: "Beam",
    HORIZONTAL_BRACE: "Horizontal Brace",
    VERTICAL_BRACE: "Vertical Brace",
}

_FLOAT_SLACK = 1e-9  # meters; see classify_frame

# role -> SectionPermission field
ROLE_FIELDS = {
    COLUMN: "allowedForColumn",
    BEAM: "allowedForBeam",
    HORIZONTAL_BRACE: "allowedForHorizontalBrace",
    VERTICAL_BRACE: "allowedForVerticalBrace",
}


@dataclass
class Individual:
    """One member of a generation: a SAP2000 model and its genes."""

    name: str  # for example "Gen-1-3"
    path: Path  # the .sdb file of this member
    genes: dict[str, str]  # frame -> section
    fitness: object | None = None  # result of fitness_calculator (later steps)


def member_name(generation: int, member: int) -> str:
    return f"Gen-{generation}-{member}"


def classify_frame(
    frame: str,
    frameConnectivity: dict[str, tuple[str, str]],
    jointCoordinates: dict[str, tuple[float, float, float]],
    tolerance: float,
) -> str:
    """Role of a frame: COLUMN, BEAM, HORIZONTAL_BRACE or VERTICAL_BRACE.

    `tolerance` is the user's setting in cm; coordinates are in meters.
    Z is the vertical axis. With dx, dy, dz the absolute coordinate
    differences between joint I and joint J, and "small" meaning
    `<= tolerance` ("big" is `> tolerance`):

        dx, dy, dz all small        -> error (zero length)
        dx small and dy small       -> COLUMN
        dz small, dx or dy small    -> BEAM (inside a plane parallel to xz or yz)
        dz small, dx and dy big     -> HORIZONTAL_BRACE
        otherwise (dz big)          -> VERTICAL_BRACE

    Raises ValueError for a frame or joint that is not in the tables and
    for a frame of (almost) zero length.
    """

    if frame not in frameConnectivity:
        raise ValueError(f"Frame '{frame}': not found in the connectivity table.")

    joint_i, joint_j = frameConnectivity[frame]

    for joint in (joint_i, joint_j):
        if joint not in jointCoordinates:
            raise ValueError(f"Frame '{frame}': joint '{joint}' has no coordinates.")

    xi, yi, zi = jointCoordinates[joint_i]
    xj, yj, zj = jointCoordinates[joint_j]

    # cm -> m. The tiny extra keeps a difference that is exactly the
    # tolerance "small" in spite of float rounding (3.01 - 3.00 is
    # 0.010000000000000009, not 0.01).
    limit = tolerance / 100.0 + _FLOAT_SLACK
    small_x = abs(xi - xj) <= limit
    small_y = abs(yi - yj) <= limit
    small_z = abs(zi - zj) <= limit

    if small_x and small_y and small_z:
        raise ValueError(
            f"Frame '{frame}': joints '{joint_i}' and '{joint_j}' are closer than "
            "the tolerance in all directions (zero length)."
        )

    if small_x and small_y:
        return COLUMN

    if small_z:
        return BEAM if (small_x or small_y) else HORIZONTAL_BRACE

    return VERTICAL_BRACE


def classify_frames(
    frames: Iterable[str],
    frameConnectivity: dict[str, tuple[str, str]],
    jointCoordinates: dict[str, tuple[float, float, float]],
    tolerance: float,
) -> dict[str, str]:
    """Role of every frame in `frames` (same order). All problems are
    collected and raised together in one ValueError."""

    roles: dict[str, str] = {}
    problems: list[str] = []

    for frame in frames:
        try:
            roles[frame] = classify_frame(
                frame, frameConnectivity, jointCoordinates, tolerance
            )
        except ValueError as exc:
            problems.append(str(exc))

    if problems:
        shown = "\n".join(problems[:10])
        more = f"\n... and {len(problems) - 10} more." if len(problems) > 10 else ""
        raise ValueError(f"{len(problems)} frame(s) could not be classified:\n{shown}{more}")

    return roles


def build_gene_options(
    frameSections: dict[str, str],
    frameRoles: dict[str, str],
    sections: list[SectionPermission],
) -> dict[str, list[str]]:
    """Frame -> names of the sections it may get.

    A section is allowed for a frame when its Material Type equals the
    Material Type of the frame's reference section and it is allowed for
    the frame's role. Raises ValueError (all problems together) when a
    frame has no usable material or no allowed section.
    """

    material_of = {s.name: s.materialType for s in sections}
    cache: dict[tuple[str, str], list[str]] = {}
    options: dict[str, list[str]] = {}

    unknown_material: set[str] = set()
    no_option: dict[tuple[str, str], int] = {}

    for frame, current in frameSections.items():
        material = material_of.get(current, "")

        if not material:
            unknown_material.add(current)
            continue

        role = frameRoles[frame]
        key = (material, role)

        if key not in cache:
            field_name = ROLE_FIELDS[role]
            cache[key] = [
                s.name
                for s in sections
                if s.materialType == material and getattr(s, field_name)
            ]

        if not cache[key]:
            no_option[key] = no_option.get(key, 0) + 1
            continue

        options[frame] = cache[key]

    problems: list[str] = []

    if unknown_material:
        problems.append(
            "no Material Type for the section(s): " + ", ".join(sorted(unknown_material))
        )

    for (material, role), count in sorted(no_option.items()):
        problems.append(
            f"{count} frame(s) are {role} with material '{material}', "
            f"but no {material} section is allowed for {role}"
        )

    if problems:
        raise ValueError("Cannot build the initial population: " + "; ".join(problems) + ".")

    return options


def random_genes(options: dict[str, list[str]], rng: random.Random) -> dict[str, str]:
    """One random section for every frame (genes are independent)."""

    return {frame: rng.choice(choices) for frame, choices in options.items()}
