"""Auto Design - step 8: building blocks of the initial population (no Qt).

Frame roles, the sections allowed for every frame (same material as the
reference section, allowed for the frame's role) and the random genes of
one population member.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from src.plugins.auto_design.params import SectionPermission

COLUMN = "column"
BEAM = "beam"
HORIZONTAL_BRACE = "horizontalBrace"
VERTICAL_BRACE = "verticalBrace"

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
    TODO: the rule will be described by the user.
    """

    raise NotImplementedError(
        "classify_frame (step 8.2.1.1) is not written yet: its rule is still to be defined."
    )


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