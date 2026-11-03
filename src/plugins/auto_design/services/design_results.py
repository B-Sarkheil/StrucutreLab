"""Auto Design - results of the SAP2000 analysis and design (no Qt).

Reads what `fitness_calculator` needs from the SAP2000 database tables
AFTER the analysis and the steel / concrete design have run:

* the weight of the structure (`Material List 1 - By Object Type`),
* the governing stress ratio of every frame (steel, concrete column,
  concrete beam).

Every reader of an ELEMENT constraint returns `frame -> ratio` (the
ratio is demand / capacity, 1.0 is the limit). Adding a new element
constraint (for example beam deflection) means writing one more reader
with this same shape and adding it to `ELEMENT_CONSTRAINTS` in
`fitness.py`.
"""
from __future__ import annotations

import logging

from src.core.sap_client import SapClient, SapError
from src.plugins.auto_design.services.sap_tables import pick_field

logger = logging.getLogger(__name__)

WEIGHT_TABLE = "Material List 1 - By Object Type"
STEEL_TABLE = "Steel Design 1 - Summary Data"
CONCRETE_COLUMN_TABLE = "Concrete Design 1 - Column Summary Data"
CONCRETE_BEAM_TABLE = "Concrete Design 2 - Beam Summary Data"

# The concrete beam table has no ratio, only an error message when the
# beam fails. A failed beam gets this fixed ratio (strict on purpose, so
# the GA strongly avoids it).
CONCRETE_BEAM_ERROR_RATIO = 1.5

# Same idea for a steel frame that has an error message and no ratio.
STEEL_ERROR_RATIO = 1.5

_NO_MESSAGE = {"", "no message", "none", "n/a", "-"}


def _number(text: str, key: str, table: str) -> float:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise SapError(f"Table '{table}': '{text}' in field '{key}' is not a number.") from None


def _optional_field(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    """First field of `candidates` found in the row (case-insensitive), else None."""

    lowered = {name.lower(): value for name, value in row.items()}

    for key in candidates:
        if key.lower() in lowered:
            return lowered[key.lower()].strip()

    return None


def _has_message(text: str | None) -> bool:
    return text is not None and text.strip().lower() not in _NO_MESSAGE


def read_design_table(client: SapClient, key: str) -> list[dict[str, str]]:
    """Rows of a design table. SAP2000 often adds the design code to the
    table key ("Steel Design 1 - Summary Data - AISC 360-16"), so when the
    plain key is refused the first available table that starts with it is
    used. A table that does not exist (for example no concrete in the
    model) gives [] and a warning."""

    try:
        return client.read_table(key)
    except SapError:
        pass

    try:
        matches = [k for k in client.available_table_keys() if k.startswith(key)]
    except SapError:
        matches = []

    if not matches:
        logger.warning("Design table '%s' is not available (nothing of this kind in the model?)", key)
        return []

    if len(matches) > 1:
        logger.warning("Several tables start with '%s': %s; using the first", key, matches)

    return client.read_table(matches[0])


def _keep_max(result: dict[str, float], frame: str, ratio: float) -> None:
    if ratio > result.get(frame, float("-inf")):
        result[frame] = ratio


# ---------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------


def read_total_weight(client: SapClient) -> float:
    """Sum of the `TotalWeight` column of `Material List 1 - By Object Type`
    (in the present units of the model: N-m-C, so Newton)."""

    rows = client.read_table(WEIGHT_TABLE)

    if not rows:
        raise SapError(f"Table '{WEIGHT_TABLE}' is empty.")

    return sum(
        _number(pick_field(row, "TotalWeight", WEIGHT_TABLE), "TotalWeight", WEIGHT_TABLE)
        for row in rows
    )


# ---------------------------------------------------------------------
# Stress ratios (element constraint)
# ---------------------------------------------------------------------


def read_steel_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> governing Ratio of the steel frames (the column `RatioType`
    only says which check governs; it is logged for the worst frame)."""

    result: dict[str, float] = {}
    worst: tuple[float, str, str] = (float("-inf"), "", "")

    for row in read_design_table(client, STEEL_TABLE):
        frame = pick_field(row, "Frame", STEEL_TABLE)
        text = pick_field(row, "Ratio", STEEL_TABLE)

        if text:
            ratio = _number(text, "Ratio", STEEL_TABLE)
        elif _has_message(_optional_field(row, ("ErrMsg",))):
            ratio = STEEL_ERROR_RATIO
        else:
            continue

        _keep_max(result, frame, ratio)

        if ratio > worst[0]:
            worst = (ratio, frame, _optional_field(row, ("RatioType",)) or "")

    if result:
        logger.info("Steel: %d frames, worst ratio %.3f (frame %s, %s)", len(result), *worst)

    return result


def read_concrete_column_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> `PMMRatio` of the concrete columns."""

    result: dict[str, float] = {}

    for row in read_design_table(client, CONCRETE_COLUMN_TABLE):
        frame = _optional_field(row, ("Frame", "Column"))

        if frame is None:
            raise SapError(
                f"Table '{CONCRETE_COLUMN_TABLE}': no frame field. Fields: {', '.join(row)}"
            )

        text = pick_field(row, "PMMRatio", CONCRETE_COLUMN_TABLE)

        if text:
            _keep_max(result, frame, _number(text, "PMMRatio", CONCRETE_COLUMN_TABLE))
        elif _has_message(_optional_field(row, ("ErrMsg",))):
            _keep_max(result, frame, CONCRETE_BEAM_ERROR_RATIO)

    return result


def read_concrete_beam_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> fixed ratio for the concrete beams: `CONCRETE_BEAM_ERROR_RATIO`
    when the table gives an error message, else 0 (passes). The table has
    no real DCR."""

    result: dict[str, float] = {}

    for row in read_design_table(client, CONCRETE_BEAM_TABLE):
        frame = _optional_field(row, ("Frame", "Beam"))

        if frame is None:
            raise SapError(
                f"Table '{CONCRETE_BEAM_TABLE}': no frame field. Fields: {', '.join(row)}"
            )

        failed = _has_message(_optional_field(row, ("ErrMsg",)))
        _keep_max(result, frame, CONCRETE_BEAM_ERROR_RATIO if failed else 0.0)

    return result


def read_stress_ratios(client: SapClient) -> dict[str, float]:
    """Frame -> stress ratio of every designed frame (steel, concrete column,
    concrete beam). A frame is in only one of the three tables; if it is in
    more than one the largest ratio is kept."""

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
