"""Token table: text inside a rectangle to SAP load records (docs section 6)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..params import SldParams
from .issues import Issue
from .sld_reader import is_number

_TOKEN = re.compile(r"^([A-Za-z]+)\s*=\s*(.*)$")
VERTICAL = ("V", "FV")
LATERAL = ("HS", "LS", "HT", "LT")

# (token, fix_dir) -> (LoadPat, Dir). fix_dir "y": beam along X; "x": beam along Y.
_ANCHOR = {
    ("HS", "y"): ("ANC.OCCY", "Y"),
    ("HS", "x"): ("ANC.OCCX", "X"),
    ("LS", "y"): ("ANC.OCCX", "X"),
    ("LS", "x"): ("ANC.OCCY", "Y"),
    ("HT", "y"): ("ANC.OPY", "Y"),
    ("HT", "x"): ("ANC.OPX", "X"),
    ("LT", "y"): ("ANC.OPX", "X"),
    ("LT", "x"): ("ANC.OPY", "Y"),
}


@dataclass(frozen=True)
class LoadToken:
    token: str  # upper case
    value: float  # kgf/m


@dataclass(frozen=True)
class LoadRecord:
    frame: str
    load_pat: str
    direction: str  # Gravity | X | Y
    rel_a: float
    rel_b: float
    abs_a: float
    abs_b: float
    value: float  # Tonf/m


def parse_texts(
    texts: list[str], file: str, index: int, cad, issues: list[Issue]
) -> list[LoadToken] | None:
    """Tokens of one rectangle in text order; None (with issues) when invalid."""
    tokens: list[LoadToken] = []
    before = len(issues)

    for text in texts:
        if not text:
            continue
        if is_number(text):
            issues.append(Issue("S15", f"'{text}' is only a number; write e.g. V={text}.", file, index, cad))
            continue
        m = _TOKEN.match(text)
        if not m or m.group(1).upper() not in VERTICAL + LATERAL:
            issues.append(Issue("S13", f"Invalid abbreviation: '{text}'.", file, index, cad))
            continue
        token, raw = m.group(1).upper(), m.group(2).strip()
        if not is_number(raw):
            issues.append(Issue("S14", f"The value after '=' is not a number: '{text}'.", file, index, cad))
            continue
        tokens.append(LoadToken(token, float(raw)))

    n_v = sum(t.token in VERTICAL for t in tokens)
    if n_v != 1 and len(issues) == before:
        issues.append(Issue("S11", "V= (or FV=) must appear exactly once.", file, index, cad))
    for name in LATERAL:
        if sum(t.token == name for t in tokens) > 1:
            issues.append(Issue("S12", f"{name}= is repeated.", file, index, cad))

    return None if len(issues) > before else tokens


def records_for(
    tokens: list[LoadToken],
    frame: str,
    fix_dir: str,
    abs_a: float,
    abs_b: float,
    length: float,
    params: SldParams,
) -> list[LoadRecord]:
    rel_a, rel_b = abs_a / length, abs_b / length

    def rec(pat: str, direction: str, value: float) -> LoadRecord:
        return LoadRecord(frame, pat, direction, rel_a, rel_b, abs_a, abs_b, value)

    out: list[LoadRecord] = []
    for t in tokens:
        if t.token in VERTICAL:
            out += [
                rec("PIPE.OPER1", "Gravity", t.value / 1000),
                rec("PIPE.OPER2", "Gravity", t.value / 1000),
                rec("EQ.Z", "Gravity", params.eqz_coef * t.value / 1000),
                rec("FRX", "X", params.friction_coef * t.value / 1000),
                rec("FRY", "Y", params.friction_coef * t.value / 1000),
            ]
        else:
            pat, direction = _ANCHOR[(t.token, fix_dir)]
            out.append(rec(pat, direction, t.value / 1000))
    return out
