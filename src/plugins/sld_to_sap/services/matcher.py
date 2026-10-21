"""Find the SAP frame under a distributed load rectangle (docs section 5.4)."""
from __future__ import annotations

from dataclasses import dataclass

from ..params import SldParams
from .connectivity import Frame
from .geometry import round_mm
from .issues import Issue
from .sld_reader import SldFile, SldRow


@dataclass(frozen=True)
class Line:
    """Where the load lies, in model coordinates (metres)."""

    fix_dir: str  # "x": beam along Y (X is fixed), "y": beam along X
    perp: float  # fixed coordinate (X when fix_dir == "x", else Y)
    a_lo: float  # load extent along the beam
    a_hi: float
    z: tuple[float, ...]  # level(s) the beam must have


@dataclass(frozen=True)
class Match:
    frame: Frame
    fix_dir: str
    abs_a: float
    abs_b: float


def build_lines(sld: SldFile, row: SldRow, params: SldParams, issues: list[Issue]) -> list[Line]:
    """One line for an elevation file, two (vertical, horizontal) for a plan."""
    c = [None if v is None else v / 1000 for v in row.coords]
    ox, oy = sld.ox, sld.oy

    if sld.kind in ("x", "y"):
        a1, a2 = round_mm(c[0] - ox), round_mm(c[2] - ox)
        z1 = round_mm(c[1] - oy + params.z0)
        z2 = round_mm(c[3] - oy + params.z0)
        if abs(z1 - z2) > params.tol:
            issues.append(Issue("S16", "The bottom edge of the load is not level.", sld.name, row.index, row.cad))
            return []
        fix = "x" if sld.kind == "x" else "y"
        return [Line(fix, sld.v, min(a1, a2), max(a1, a2), (z1, z2))]

    def m(*vals: float) -> float:
        return sum(vals) / len(vals)

    # plan: points 1,2 bottom edge; 4,3 top edge (bounding box order)
    vx = round_mm(m(c[0], c[2]) - ox)
    vy = (round_mm(m(c[1], c[3]) - oy), round_mm(m(c[5], c[7]) - oy))
    hy = round_mm(m(c[1], c[7]) - oy)
    hx = (round_mm(m(c[0], c[6]) - ox), round_mm(m(c[2], c[4]) - ox))
    return [
        Line("x", vx, min(vy), max(vy), (sld.v,)),
        Line("y", hy, min(hx), max(hx), (sld.v,)),
    ]


def _match_line(line: Line, frames: list[Frame], params: SldParams) -> list[Match]:
    tol, end_tol = params.tol, params.end_tol
    k_perp, k_p = (0, 1) if line.fix_dir == "x" else (1, 0)
    found: list[Match] = []

    for f in frames:
        zi, zj = f.i[2], f.j[2]
        if abs(zi - zj) > tol or any(abs(zi - z) > tol or abs(zj - z) > tol for z in line.z):
            continue
        ei, ej = f.i[k_perp], f.j[k_perp]
        if abs(ei - ej) > tol or abs(ei - line.perp) > tol or abs(ej - line.perp) > tol:
            continue
        pi, pj = f.i[k_p], f.j[k_p]
        if min(pi, pj) > line.a_lo + end_tol or max(pi, pj) < line.a_hi - end_tol:
            continue

        if pi < pj:
            a, b = line.a_lo - pi, line.a_hi - pi
        else:
            a, b = pi - line.a_hi, pi - line.a_lo
        a, b = min(max(a, 0.0), f.length), min(max(b, 0.0), f.length)
        found.append(Match(f, line.fix_dir, a, b))
    return found


def match_rect(
    sld: SldFile, row: SldRow, frames: list[Frame], params: SldParams, issues: list[Issue]
) -> Match | None:
    """The single frame carrying the load; M01 / M02 are reported otherwise."""
    lines = build_lines(sld, row, params, issues)
    if not lines:
        return None

    found = [m for line in lines for m in _match_line(line, frames, params)]
    if not found:
        issues.append(Issue("M01", "No frame found under this load.", sld.name, row.index, row.cad))
        return None
    if len(found) > 1:
        names = ", ".join(m.frame.name for m in found)
        issues.append(
            Issue("M02", f"More than one frame found ({names}).", sld.name, row.index, row.cad)
        )
        return None
    return found[0]
