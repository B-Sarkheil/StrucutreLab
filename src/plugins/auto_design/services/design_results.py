"""Auto Design - results of the SAP2000 analysis and design (no Qt).

Reads what `fitness_calculator` needs AFTER the analysis and the steel /
concrete design have run:

* the weight of the structure: database table `Material List 1 - By Object
  Type`, column `TotalWeight`, summed (there is no API call for it),
* the governing stress ratio of every frame, from the design API with the
  group "ALL" (so the name of the design code never matters):
    - steel frames:     DesignSteel.GetSummaryResults  (Ratio),
    - concrete columns: DesignConcrete.GetSummaryResultsColumn  (PMMRatio),
    - concrete beams:   DesignConcrete.GetSummaryResultsBeam  (no ratio:
      only an error message, so a failed beam gets a fixed ratio).

Every reader of an ELEMENT constraint returns `frame -> ratio` (demand /
capacity, 1.0 is the limit). Adding a new element constraint (for example
beam deflection) means writing one more reader with this same shape and
adding it to `ELEMENT_CONSTRAINTS` in `fitness.py`.

The design combinations are never touched: the design uses the combos the
user selected in the reference model.
"""
from __future__ import annotations

import logging

from src.core.sap_client import SapClient, SapError
from src.plugins.auto_design.services.sap_tables import pick_field

logger = logging.getLogger(__name__)

WEIGHT_TABLE = "Material List 1 - By Object Type"

ALL_GROUP = "ALL"  # the group every SAP2000 model has

# A concrete beam has no ratio, only an error message when it fails. A
# failed beam gets this fixed ratio (strict on purpose, so the GA strongly
# avoids it). The same value is the least ratio of a steel or concrete
# column frame that reports an error message.
ERROR_RATIO = 1.5

_NO_MESSAGE = {"", "no message", "none", "n/a", "-"}


def _has_message(text: object) -> bool:
    return str(text if text is not None else "").strip().lower() not in _NO_MESSAGE


def _keep_max(result: dict[str, float], frame: str, ratio: float) -> None:
    if ratio > result.get(frame, float("-inf")):
        result[frame] = ratio


def _unpack(result: object, parts: int, call: str) -> tuple[int, list[list]] | None:
    """Split the tuple pythonnet returns for a Get...Summary call.

    The tuple is (ret, NumberItems, array1, array2, ...). Returns the arrays
    cut to NumberItems, or None when SAP2000 returns an error code (for
    example no frame of that kind in the model).
    """

    if not isinstance(result, tuple) or len(result) != parts + 2:
        raise SapError(f"Unexpected result of {call}: {result!r}")

    ret, count = result[0], int(result[1])

    if ret != 0:
        logger.warning("%s returned the error code %s: nothing of this kind is used", call, ret)
        return None

    return count, [list(array or [])[:count] for array in result[2:]]


# ---------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------


def read_total_weight(client: SapClient) -> float:
    """Sum of the `TotalWeight` column of `Material List 1 - By Object Type`
    (in the present units of the model: kgf-m-C, so kg; see
    SapClient.open_model)."""

    rows = client.read_table(WEIGHT_TABLE)

    if not rows:
        raise SapError(f"Table '{WEIGHT_TABLE}' is empty.")

    total = 0.0

    for row in rows:
        text = pick_field(row, "TotalWeight", WEIGHT_TABLE).replace(",", ".")

        try:
            total += float(text)
        except ValueError:
            raise SapError(
                f"Table '{WEIGHT_TABLE}': '{text}' in field 'TotalWeight' is not a number."
            ) from None

    return total


# ---------------------------------------------------------------------
# Stress ratios (element constraint)
# ---------------------------------------------------------------------


def read_steel_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> governing Ratio of the steel frames."""

    group = client.api.eItemType.Group
    raw = client.model.DesignSteel.GetSummaryResults(
        ALL_GROUP, 0, None, None, None, None, None, None, None, group
    )
    data = _unpack(raw, 7, "DesignSteel.GetSummaryResults")

    if data is None or data[0] == 0:
        return {}

    _count, (frames, ratios, ratio_types, _locations, combos, errors, _warnings) = data

    result: dict[str, float] = {}
    worst = (float("-inf"), "", "", "")

    for frame, ratio, ratio_type, combo, error in zip(frames, ratios, ratio_types, combos, errors):
        ratio = float(ratio)

        if _has_message(error):
            ratio = max(ratio, ERROR_RATIO)

        _keep_max(result, str(frame), ratio)

        if ratio > worst[0]:
            worst = (ratio, str(frame), str(ratio_type), str(combo))

    logger.info("Steel: %d frames, worst ratio %.3f (frame %s, %s, %s)", len(result), *worst)

    return result


def read_concrete_column_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> governing PMMRatio of the concrete columns."""

    group = client.api.eItemType.Group
    raw = client.model.DesignConcrete.GetSummaryResultsColumn(
        ALL_GROUP, 0, None, None, None, None, None, None, None, None, None, None, None, None, group
    )
    data = _unpack(raw, 12, "DesignConcrete.GetSummaryResultsColumn")

    if data is None or data[0] == 0:
        return {}

    _count, arrays = data
    frames, pmm_ratios, errors = arrays[0], arrays[5], arrays[10]

    result: dict[str, float] = {}

    for frame, ratio, error in zip(frames, pmm_ratios, errors):
        ratio = float(ratio)

        if _has_message(error):
            ratio = max(ratio, ERROR_RATIO)

        _keep_max(result, str(frame), ratio)

    logger.info("Concrete columns: %d frames, worst ratio %.3f", len(result), max(result.values(), default=0.0))

    return result


def read_concrete_beam_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> `ERROR_RATIO` when the concrete beam has an error message,
    else 0 (it passes). SAP2000 gives no real DCR for concrete beams."""

    group = client.api.eItemType.Group
    raw = client.model.DesignConcrete.GetSummaryResultsBeam(
        ALL_GROUP, 0, None, None, None, None, None, None, None, None, None, None, None, None,
        None, None, group,
    )
    data = _unpack(raw, 14, "DesignConcrete.GetSummaryResultsBeam")

    if data is None or data[0] == 0:
        return {}

    _count, arrays = data
    frames, errors = arrays[0], arrays[12]

    result: dict[str, float] = {}

    for frame, error in zip(frames, errors):
        _keep_max(result, str(frame), ERROR_RATIO if _has_message(error) else 0.0)

    logger.info(
        "Concrete beams: %d frames, %d with an error message",
        len(result),
        sum(r >= ERROR_RATIO for r in result.values()),
    )

    return result


def read_stress_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> stress ratio of every designed frame (steel, concrete column,
    concrete beam). A frame is in only one of the three; if it is in more
    than one the largest ratio is kept."""

    result: dict[str, float] = {}

    for reader in (read_steel_ratios, read_concrete_column_ratios, read_concrete_beam_ratios):
        for frame, ratio in reader(client).items():
            _keep_max(result, frame, ratio)

    if not result:
        raise SapError(
            "No design results were found (no steel or concrete frame was designed). "
            "Check the design code and the design settings of the reference model."
        )

    return result
