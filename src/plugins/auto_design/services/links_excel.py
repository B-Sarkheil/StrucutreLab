"""Excel import / export of the linked frames (Auto Design, step 4.1).

Pure logic, no Qt. `openpyxl` is imported lazily, so the application
starts (and the rest of the wizard works) even if it is missing.

File layout: one sheet, one row per frame of the model.

    Frame | Type | Section | X (m) | Y (m) | Z (m) | Link group

Frames with the same text in "Link group" form one group; an empty cell
means "not linked". On import only the columns `Frame` and `Link group`
are read (the others are for the user's information, so groups can be
edited in Excel with the position of every frame in view).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

HEADERS = ("Frame", "Type", "Section", "X (m)", "Y (m)", "Z (m)", "Link group")
REQUIRED = ("Frame", "Link group")


class LinksExcelError(Exception):
    """A problem the user can understand (message is shown as is)."""


@dataclass(frozen=True)
class LinkRow:
    frame: str
    type: str
    section: str
    x: float | None
    y: float | None
    z: float | None
    group: str  # "" = not linked


def _openpyxl():
    try:
        import openpyxl
    except ImportError as exc:
        raise LinksExcelError(
            "The 'openpyxl' package is required for Excel import and export."
        ) from exc

    return openpyxl


def _text(value) -> str:
    """Cell value as text; 12.0 -> "12" (frame and group names may be numbers)."""

    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return str(value).strip()


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------


def export_links(path: str | Path, rows: Iterable[LinkRow]) -> None:
    """Write `rows` to an .xlsx file."""

    openpyxl = _openpyxl()

    from openpyxl.styles import Alignment, Font

    rows = list(rows)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Links"
    sheet.append(list(HEADERS))

    for row in rows:
        sheet.append(
            [
                row.frame,
                row.type,
                row.section,
                None if row.x is None else round(row.x, 3),
                None if row.y is None else round(row.y, 3),
                None if row.z is None else round(row.z, 3),
                row.group or None,
            ]
        )

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    widths = {
        "A": max(12, max((len(r.frame) for r in rows), default=0) + 2),
        "B": 20,
        "C": max(18, max((len(r.section) for r in rows), default=0) + 2),
        "D": 11,
        "E": 11,
        "F": 11,
        "G": 20,
    }

    for letter, width in widths.items():
        sheet.column_dimensions[letter].width = width

    for letter in ("D", "E", "F"):
        for cell in sheet[letter][1:]:
            cell.alignment = Alignment(horizontal="center")

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:G{len(rows) + 1}"

    try:
        workbook.save(str(path))
    except OSError as exc:
        raise LinksExcelError(
            f"Could not write the file (is it open in Excel?): {exc}"
        ) from exc


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------


def _find_columns(header) -> tuple[int, int]:
    if not header:
        raise LinksExcelError("The first sheet of the file is empty.")

    names = {
        str(value).strip().lower(): index
        for index, value in enumerate(header)
        if value is not None
    }
    missing = [title for title in REQUIRED if title.lower() not in names]

    if missing:
        raise LinksExcelError(
            "Missing column(s) in the first row: " + ", ".join(missing) + "."
        )

    return names["frame"], names["link group"]


def import_links(path: str | Path) -> dict[str, str]:
    """Read an .xlsx file: frame name -> link group text ("" = not linked),
    in the order of the file. A frame that appears twice keeps its last row."""

    openpyxl = _openpyxl()

    try:
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise LinksExcelError(f"Could not open the Excel file: {exc}") from exc

    result: dict[str, str] = {}

    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        frame_col, group_col = _find_columns(next(rows, None))

        for row in rows:
            frame = _text(row[frame_col] if frame_col < len(row) else None)

            if not frame:
                continue

            result[frame] = _text(row[group_col] if group_col < len(row) else None)
    except LinksExcelError:
        raise
    except Exception as exc:
        raise LinksExcelError(f"Could not read the Excel file: {exc}") from exc
    finally:
        workbook.close()

    if not result:
        raise LinksExcelError("The file contains no frames.")

    return result
