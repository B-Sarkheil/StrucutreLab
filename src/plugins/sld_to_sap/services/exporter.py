"""Write the two SAP2000 import tables (docs section 7). Headers must stay exactly as is."""
from __future__ import annotations

from pathlib import Path

from .pipeline import ConversionResult

JOINT_FILE = "SAP2000 Joint Coordinates.xlsx"
LOAD_FILE = "SAP2000 Distributed Loads.xlsx"


def _frame_value(name: str):
    return int(name) if name.isdigit() else name


def write_outputs(result: ConversionResult, out_dir: str | Path) -> list[Path]:
    """Write both files; refuses when the conversion has errors."""
    from openpyxl import Workbook

    if not result.ok:
        raise ValueError("The conversion has errors; no output is written.")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Joint Coordinates"
    ws.append(["TABLE:  Joint Coordinates"])
    ws.append(["Joint", "CoordSys", "CoordType", "XorR", "Y", "T", "Z", "SpecialJt", "GUID"])
    ws.append(["Text", "Text", "Text", "m", "m", "Degrees", "m", "Yes/No", "Text"])
    for j in result.joints:
        ws.append([j.name, "GLOBAL", "Cartesian", j.x, j.y, None, j.z, "Yes", None])
    joint_path = out / JOINT_FILE
    wb.save(joint_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "Frame Loads - Distributed"
    ws.append(["TABLE:  Frame Loads - Distributed"])
    ws.append(["Frame", "LoadPat", "CoordSys", "Type", "Dir", "DistType", "RelDistA", "RelDistB",
               "AbsDistA", "AbsDistB", "FOverLA", "FOverLB", "MOverLA", "MOverLB", "GUID"])
    ws.append(["Text", "Text", "Text", "Text", "Text", "Text", "Unitless", "Unitless", "m", "m",
               "Tonf/m", "Tonf/m", "Tonf-m/m", "Tonf-m/m", "Text"])
    for r in result.loads:
        ws.append([_frame_value(r.frame), r.load_pat, "GLOBAL", "Force", r.direction, "RelDist",
                   r.rel_a, r.rel_b, r.abs_a, r.abs_b, r.value, r.value, None, None, None])
    load_path = out / LOAD_FILE
    wb.save(load_path)
    return [joint_path, load_path]
