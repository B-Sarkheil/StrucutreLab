"""Auto Design - step 5: Material Type of every section (no Qt).

The Material Type is read from two SAP2000 database tables: the material
of each frame section, then the Material Type of that material. The type
is stored exactly as SAP names it; nothing is mapped or rejected.
"""
from __future__ import annotations

import logging

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.sap_tables import pick_field

logger = logging.getLogger(__name__)

SECTION_TABLE = "Frame Section Properties 01 - General"
MATERIAL_TABLE = "Material Properties 01 - General"


def read_material_types(client: SapClient, section_names: list[str]) -> dict[str, str]:
    """Section name -> Material Type, for every name in `section_names`.

    A section with no row in the table (for example an Auto Select list)
    gets "" and a warning in the log.
    """

    section_rows = client.read_table(SECTION_TABLE)
    material_rows = client.read_table(MATERIAL_TABLE)

    material_of = {
        pick_field(r, "SectionName", SECTION_TABLE): pick_field(r, "Material", SECTION_TABLE)
        for r in section_rows
    }
    type_of = {
        pick_field(r, "Material", MATERIAL_TABLE): pick_field(r, "Type", MATERIAL_TABLE)
        for r in material_rows
    }

    result: dict[str, str] = {}

    for name in section_names:
        material = material_of.get(name, "")
        result[name] = type_of.get(material, "")

        if not result[name]:
            logger.warning(
                "Section '%s': no Material Type found (material '%s')", name, material
            )

    return result