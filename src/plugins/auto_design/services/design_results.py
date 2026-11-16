"""Auto Design - results of the SAP2000 analysis and design (no Qt); used by the fitness (steps 8 and 9).

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

# ---------------------------------------------------------------------
# Major flexure / minor flexure / axial ratios at the governing point (directed mutation)
# ---------------------------------------------------------------------

# Prefix of the steel design table that holds MMajRatio, MMinRatio and PRatio.
# The rest of the key is the design code name, so the table is found by prefix.
FLEXURE_TABLE_PREFIX = "Steel Design 2 - PMM Details"

_FLEXURE_WARNED: set[str] = set()


def _read_steel_governing_points(client: SapClient) -> dict[str, tuple[str, float]]:
    """Frame -> (load combination, location) of the row with the governing
    (largest) ratio, from the same summary call that gives the DCR."""

    group = client.api.eItemType.Group
    raw = client.model.DesignSteel.GetSummaryResults(
        ALL_GROUP, 0, None, None, None, None, None, None, None, group
    )
    data = _unpack(raw, 7, "DesignSteel.GetSummaryResults")

    if data is None or data[0] == 0:
        return {}

    _count, (frames, ratios, _types, locations, combos, _errors, _warnings) = data

    best: dict[str, float] = {}
    result: dict[str, tuple[str, float]] = {}

    for frame, ratio, location, combo in zip(frames, ratios, locations, combos):
        frame, ratio = str(frame), float(ratio)

        if ratio > best.get(frame, float("-inf")):
            best[frame] = ratio
            result[frame] = (str(combo).strip(), float(location))

    return result


def read_steel_flexure_ratios(
    client: SapClient,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """(frame -> MMajRatio, frame -> MMinRatio, frame -> PRatio) of the steel
    frames, all taken from ONE row of the PMM table: the row of the governing
    load combination (the one that gives the DCR) whose location is closest to
    the governing location. The ratios are never mixed between different
    combinations.

    When the table, a field or the governing point is not found, the frame is
    left out (the directed mutation then falls back to Z33); a problem with
    the whole table gives three empty dicts and one warning in the log. A
    frame whose row has no readable PRatio is left out of the third dict only."""

    try:
        table = next(
            (k for k in client.table_keys() if k.lower().startswith(FLEXURE_TABLE_PREFIX.lower())),
            None,
        )

        if table is None:
            raise SapError(f"No table starting with '{FLEXURE_TABLE_PREFIX}' was found.")

        governing = _read_steel_governing_points(client)

        # frame -> (distance to the governing location, -largest of the three ratios,
        #           major, minor, axial or None)
        chosen: dict[str, tuple[float, float, float, float, float | None]] = {}

        for row in client.read_table(table):
            frame = pick_field(row, "Frame", table)
            point = governing.get(frame)

            if point is None:
                continue

            combo, location = point

            if pick_field(row, "Combo", table).lower() != combo.lower():
                continue

            try:
                major = float(pick_field(row, "MMajRatio", table).replace(",", "."))
                minor = float(pick_field(row, "MMinRatio", table).replace(",", "."))
            except ValueError:
                continue

            try:
                axial: float | None = float(pick_field(row, "PRatio", table).replace(",", "."))
            except (SapError, ValueError):
                axial = None

            try:
                distance = abs(float(pick_field(row, "Location", table).replace(",", ".")) - location)
            except ValueError:
                distance = 0.0

            key = (distance, -max(major, minor, axial or 0.0), major, minor, axial)

            if frame not in chosen or key[:2] < chosen[frame][:2]:
                chosen[frame] = key
    except SapError as exc:
        if str(exc) not in _FLEXURE_WARNED:
            _FLEXURE_WARNED.add(str(exc))
            logger.warning("Major/minor/axial ratios not available (Z33 is used): %s", exc)

        return {}, {}, {}

    return (
        {frame: values[2] for frame, values in chosen.items()},
        {frame: values[3] for frame, values in chosen.items()},
        {frame: values[4] for frame, values in chosen.items() if values[4] is not None},
    )
