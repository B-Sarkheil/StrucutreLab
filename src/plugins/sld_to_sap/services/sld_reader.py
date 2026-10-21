"""Read the CSV files written by SLD2SAP.lsp (docs sections 3.1 and 5.2)."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .issues import Issue

_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_COORD_COLUMNS = ["X1", "Y1", "X2", "Y2", "X3", "Y3", "X4", "Y4"]


def is_number(text: str) -> bool:
    """True when the whole text is a plain decimal number (not nan / inf / 1e3)."""
    return bool(_NUMBER.match(text.strip()))


@dataclass
class SldRow:
    index: int
    coords: list[float | None]  # X1,Y1,X2,Y2,X3,Y3,X4,Y4 in mm
    texts: list[str]  # Text1..TextN, stripped, "" when empty

    @property
    def cad(self) -> tuple[float, float] | None:
        if self.coords[0] is None or self.coords[1] is None:
            return None
        return self.coords[0], self.coords[1]

    @property
    def is_rect(self) -> bool:
        return all(c is not None for c in self.coords[2:])

    @property
    def has_partial_rect(self) -> bool:
        rest = self.coords[2:]
        return any(c is not None for c in rest) and not all(c is not None for c in rest)


@dataclass
class SldFile:
    name: str
    kind: str  # "x" | "y" | "z"
    ox: float  # origin, metres
    oy: float
    v: float  # value next to the origin mark
    rows: list[SldRow] = field(default_factory=list)  # without the origin row


def discover_files(paths: list[str | Path]) -> list[Path]:
    """CSV files from files and folders; hidden / temporary files dropped; sorted."""
    found: list[Path] = []
    for p in map(Path, paths):
        items = sorted(p.glob("*.csv")) if p.is_dir() else [p]
        for item in items:
            if item.name.startswith((".", "~")):
                continue
            if item not in found:
                found.append(item)
    return sorted(found, key=lambda f: f.name.casefold())


def _read_rows(path: Path, issues: list[Issue]) -> list[SldRow]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = raw.splitlines()
    if not lines:
        issues.append(Issue("S00", "The file is empty.", path.name))
        return []

    header = next(csv.reader([lines[0]]))
    if len(header) == 1 and ";" in header[0]:
        issues.append(
            Issue("S00", "The file uses ';' as separator; save it with ',' separators.", path.name)
        )
        return []

    names = [h.strip().casefold() for h in header]
    try:
        col_index = names.index("index")
        col_coords = [names.index(c.casefold()) for c in _COORD_COLUMNS]
    except ValueError as exc:
        issues.append(Issue("S00", f"Missing header column ({exc}).", path.name))
        return []
    col_texts = [i for i, n in enumerate(names) if n.startswith("text")]

    rows: list[SldRow] = []
    for number, record in enumerate(csv.reader(lines[1:]), start=2):
        if not any(cell.strip() for cell in record):
            continue
        record = record + [""] * (len(header) - len(record))  # short row: pad

        try:
            index = int(float(record[col_index]))
        except ValueError:
            index = number
        coords: list[float | None] = []
        bad = False
        for c in col_coords:
            cell = record[c].strip()
            if not cell:
                coords.append(None)
            elif is_number(cell):
                coords.append(float(cell))
            else:
                coords.append(None)
                bad = True
        if bad:
            issues.append(Issue("S17", "A coordinate is not a number.", path.name, index))
            continue
        texts = [record[c].strip() for c in col_texts]
        rows.append(SldRow(index, coords, texts))
    return rows


def read_sld_csv(path: str | Path, issues: list[Issue]) -> SldFile | None:
    """Parse one file and find its origin row. Problems are appended to `issues`."""
    path = Path(path)
    rows = _read_rows(path, issues)
    if not rows:
        return None

    marks: list[tuple[SldRow, int]] = []  # (row, text column) of every x / y / z word
    for row in rows:
        for col, text in enumerate(row.texts):
            if text.casefold() in ("x", "y", "z"):
                marks.append((row, col))

    if not marks:
        issues.append(Issue("S01", "Origin point (x / y / z) not found.", path.name))
        return None
    if len(marks) > 1:
        for row, _ in marks:
            issues.append(Issue("S02", "More than one origin point.", path.name, row.index, row.cad))
        return None

    row, col = marks[0]
    word = row.texts[col].casefold()
    other = row.texts[1 - col] if col in (0, 1) and len(row.texts) > 1 else ""

    if col > 1 or not is_number(other):
        issues.append(
            Issue(
                "S03",
                "The origin point needs the letter and one number (e.g. 'Z' and '2441.3').",
                path.name,
                row.index,
                row.cad,
            )
        )
        return None
    if row.cad is None or row.is_rect or row.has_partial_rect:
        issues.append(Issue("S04", "The origin must be a circle.", path.name, row.index, row.cad))
        return None

    rows.remove(row)
    assert row.cad is not None
    return SldFile(
        name=path.name,
        kind=word,
        ox=row.cad[0] / 1000,
        oy=row.cad[1] / 1000,
        v=float(other),
        rows=rows,
    )
