"""Auto Design - step 10: cross-section area of every section (no Qt).

Read from the SAP2000 database table `Frame Section Properties 01 - General`
(field `Area`, in the model's present units: kgf-m-C, so m2). The model
must be open. A section without a number in the table (for example an Auto
Select list) is left out and gets a log warning.
"""
from __future__ import annotations

import logging

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.sap_tables import pick_field
from src.plugins.auto_design.services.section_materials import SECTION_TABLE

logger = logging.getLogger(__name__)


def read_section_areas(client: SapClient) -> dict[str, float]:
    """Section name -> area."""

    result: dict[str, float] = {}

    for row in client.read_table(SECTION_TABLE):
        name = pick_field(row, "SectionName", SECTION_TABLE)
        text = pick_field(row, "Area", SECTION_TABLE).replace(",", ".")

        try:
            result[name] = float(text)
        except ValueError:
            logger.warning("Section '%s': area '%s' is not a number", name, text)

    return result
