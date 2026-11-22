"""Excel import / export of the frame types (Auto Design, step 3).

Pure logic, no Qt. `openpyxl` is imported lazily, so the application
starts (and the rest of the wizard works) even if it is missing.

File layout: one sheet, one row per frame of the model.

    Frame | ΔX (m) | ΔY (m) | ΔZ (m) | Type

On import only the columns `Frame` and `Type` are read (the Delta columns
are for the user's information). The Type is one of the labels of the page
(Column, Beam, Horizontal Brace, Vertical Brace); case, spaces, "_" and "-"
are ignored, and the internal names (horizontalBrace) are accepted too.
An empty Type cell leaves the frame unchanged. Nothing is returned when any
Type cell is unrecognised, so a typo never half-applies.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.plugins.auto_design.services.population import ROLE_LABELS, ROLES

HEADERS = ("Frame", "ΔX (m)", "ΔY (m)", "ΔZ (m)", "Type")
REQUIRED = ("Frame", "Type")


class RolesExcelError(Exception):
    """A problem the user can understand (message is shown as is)."""


@dataclass(frozen=True)
class RoleRow:
    frame: str
    dx: float
    dy: float
    dz: float
    role: str


def _openpyxl():
    try:
        import openpyxl
    except ImportError as exc:
        raise RolesExcelError(
            "The 'openpyxl' package is required for Excel import and export."
        ) from exc

    return openpyxl


def _text(value) -> str:
    """Cell value as text; 12.0 -> "12" (frame names may be numbers)."""

    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return str(value).strip()


def _normalize(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", text.lower())


def _role_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}

    for role in ROLES:
        lookup[_normalize(role)] = role
        lookup[_normalize(ROLE_LABELS[role])] = role

    return lookup


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------


def export_roles(path: str | Path, rows: Iterable[RoleRow]) -> None:
    """Write `rows` to an .xlsx file."""

    openpyxl = _openpyxl()

    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    rows = list(rows)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Frame types"
    sheet.append(list(HEADERS))

    for row in rows:
        sheet.append(
            [
                row.frame,
                round(row.dx, 3),
                round(row.dy, 3),
                round(row.dz, 3),
                ROLE_LABELS[row.role],
            ]
        )

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    widest = max((len(r.frame) for r in rows), default=10)
    sheet.column_dimensions["A"].width = max(14, widest + 2)

    for letter in ("B", "C", "D"):
        sheet.column_dimensions[letter].width = 12

        for cell in sheet[letter][1:]:
            cell.alignment = Alignment(horizontal="center")

    sheet.column_dimensions["E"].width = 22
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:E{len(rows) + 1}"

    if rows:
        # Drop-down in Excel so the user can only type a valid type.
        labels = ",".join(ROLE_LABELS[role] for role in ROLES)
        validation = DataValidation(type="list", formula1=f'"{labels}"', allow_blank=True)
        sheet.add_data_validation(validation)
        validation.add(f"E2:E{len(rows) + 1}")

    try:
        workbook.save(str(path))
    except OSError as exc:
        raise RolesExcelError(
            f"Could not write the file (is it open in Excel?): {exc}"
        ) from exc


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------


def _find_columns(header) -> tuple[int, int]:
    if not header:
        raise RolesExcelError("The first sheet of the file is empty.")

    names = {
        str(value).strip().lower(): index
        for index, value in enumerate(header)
        if value is not None
    }
    missing = [title for title in REQUIRED if title.lower() not in names]

    if missing:
        raise RolesExcelError(
            "Missing column(s) in the first row: " + ", ".join(missing) + "."
        )

    return names["frame"], names["type"]


def import_roles(path: str | Path) -> dict[str, str]:
    """Read an .xlsx file: frame name -> role, in the order of the file.
    Frames with an empty Type cell are left out. A frame that appears twice
    keeps its last row."""

    openpyxl = _openpyxl()

    try:
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise RolesExcelError(f"Could not open the Excel file: {exc}") from exc

    lookup = _role_lookup()
    result: dict[str, str] = {}
    problems: list[str] = []

    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        frame_col, type_col = _find_columns(next(rows, None))

        for number, row in enumerate(rows, start=2):
            frame = _text(row[frame_col] if frame_col < len(row) else None)

            if not frame:
                continue

            text = _text(row[type_col] if type_col < len(row) else None)

            if not text:
                continue

            role = lookup.get(_normalize(text))

            if role is None:
                problems.append(f"row {number}: '{text}'")
                continue

            result[frame] = role
    except RolesExcelError:
        raise
    except Exception as exc:
        raise RolesExcelError(f"Could not read the Excel file: {exc}") from exc
    finally:
        workbook.close()

    if problems:
        shown = "; ".join(problems[:5])
        more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
        allowed = ", ".join(ROLE_LABELS[role] for role in ROLES)
        raise RolesExcelError(f"Unknown type. Use: {allowed}. Problem at {shown}{more}.")

    if not result:
        raise RolesExcelError("The file contains no frame types.")

    return result