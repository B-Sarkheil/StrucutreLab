"""Auto Design - step 9.1.4 (directed mutation): sections ordered from strong to weak (no Qt).

The order depends on the kind of the governing ratio of a unit:

* STRESS      (DCR)       -> plastic modulus about axis 3-3, field `Z33`,
* DEFLECTION  (beam drift) -> moment of inertia about axis 3-3, field `I33`.

A bigger value is a stronger section. Both values are read from the SAP2000
table `Frame Section Properties 01 - General` (model open, kgf-m-C units).
A section whose value is missing or not a number counts as 0 (the weakest).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.sap_tables import pick_field
from src.plugins.auto_design.services.section_materials import SECTION_TABLE

logger = logging.getLogger(__name__)

STRESS = "stress"
DEFLECTION = "deflection"
KINDS = (STRESS, DEFLECTION)

# kind -> field of the section table used to sort
ORDER_FIELD = {STRESS: "Z33", DEFLECTION: "I33"}


def read_section_properties(client: SapClient) -> dict[str, dict[str, float]]:
    """Section name -> {STRESS: Z33, DEFLECTION: I33}."""

    result: dict[str, dict[str, float]] = {}

    for row in client.read_table(SECTION_TABLE):
        name = pick_field(row, "SectionName", SECTION_TABLE)
        values: dict[str, float] = {}

        for kind, field_name in ORDER_FIELD.items():
            text = pick_field(row, field_name, SECTION_TABLE).replace(",", ".")

            try:
                values[kind] = float(text)
            except ValueError:
                values[kind] = 0.0
                logger.warning(
                    "Section '%s': %s '%s' is not a number (counts as 0)", name, field_name, text
                )

        result[name] = values

    return result


def sort_strong_to_weak(
    sections: Iterable[str], properties: dict[str, dict[str, float]], kind: str
) -> list[str]:
    """The sections (without repeats) from the strongest to the weakest by
    `kind` (STRESS: Z33, DEFLECTION: I33). Equal values: by name."""

    if kind not in ORDER_FIELD:
        raise ValueError(f"Unknown order kind '{kind}'.")

    def value(section: str) -> float:
        return properties.get(section, {}).get(kind, 0.0)

    return sorted(dict.fromkeys(sections), key=lambda s: (-value(s), s))


def step_section(ordered: list[str], current: str, weaker_steps: int) -> str | None:
    """The section `weaker_steps` places weaker than `current` in `ordered`
    (strong -> weak). Negative = stronger. Stops at the ends of the list.
    None when `current` is not in the list."""

    if current not in ordered:
        return None

    position = ordered.index(current) + weaker_steps

    return ordered[max(0, min(len(ordered) - 1, position))]
