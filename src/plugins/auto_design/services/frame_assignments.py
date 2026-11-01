"""Auto Design - step 6: section assigned to every frame (no Qt).

This is the "DNA" of the reference structure: which section each frame
of the SAP2000 model has. Read from the SAP2000 database table.
"""
from __future__ import annotations

import logging

from src.core.sap_client import SapClient
from src.plugins.auto_design.services.sap_tables import pick_field

logger = logging.getLogger(__name__)

ASSIGNMENT_TABLE = "Frame Section Assignments"


def read_frame_sections(client: SapClient) -> dict[str, str]:
    """Frame name -> assigned (analysis) section name, in SAP table order."""

    result: dict[str, str] = {}

    for row in client.read_table(ASSIGNMENT_TABLE):
        frame = pick_field(row, "Frame", ASSIGNMENT_TABLE)
        section = pick_field(row, "AnalSect", ASSIGNMENT_TABLE)

        if not section:
            logger.warning("Frame '%s' has no section in the table", frame)

        result[frame] = section

    return result