"""Auto Design - fitness of one model (no Qt). STUB: the details come later."""
from __future__ import annotations

import logging
import math
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


def fitness_value(fitness: object | None) -> float:
    """The single number used to rank members (a LARGER value is better).

    TEMPORARY: it accepts only a plain number. When `fitness_calculator`
    is described (several objectives, penalties), the rule that turns its
    result into this number goes here.
    """

    if (
        isinstance(fitness, (int, float))
        and not isinstance(fitness, bool)
        and math.isfinite(fitness)
    ):
        return float(fitness)

    raise ValueError(
        "The fitness of a member is not a number yet "
        f"(got {fitness!r}): fitness_calculator is still to be written."
    )
