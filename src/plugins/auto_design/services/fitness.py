"""Auto Design - fitness of one model (no Qt). STUB: the details come later."""
from __future__ import annotations

import logging
from pathlib import Path

from src.core.sap_client import SapClient

logger = logging.getLogger(__name__)


def fitness_calculator(sap: SapClient, sap_path: Path) -> object | None:
    """Evaluate the SAP2000 model at `sap_path` (it is the open model).

    Input: a SAP2000 file. Output: the optimization objectives.
    TODO: to be written.
    """

    logger.info("fitness_calculator is not written yet (%s)", sap_path)

    return None