"""Whole conversion: CSV files + Connectivity + parameters to joints and loads."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..params import SldParams
from .connectivity import load_model_cached
from .geometry import to_model
from .issues import ERROR, WARNING, Issue
from .load_rules import LoadRecord, parse_texts, records_for
from .matcher import match_rect
from .sld_reader import SldFile, SldRow, discover_files, is_number, read_sld_csv

# Stage names passed to the optional `on_stage` callback (used by the UI to show progress).
STAGE_MODEL = "model"  # reading the SAP2000 Excel file
STAGE_SLD = "sld"  # reading the CSV files and matching the loads

# Connectivity problems after which no frame matching is attempted (the model is unusable);
# every rectangle would otherwise get a misleading "no frame found" (M01).
_MODEL_UNUSABLE = ("M03", "M04")


@dataclass(frozen=True)
class JointRow:
    name: str
    x: float
    y: float
    z: float


@dataclass
class ConversionResult:
    issues: list[Issue] = field(default_factory=list)
    joints: list[JointRow] = field(default_factory=list)
    loads: list[LoadRecord] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def ok(self) -> bool:
        """All or nothing: any error means no output."""
        return not self.errors


def _build_joint(
    sld: SldFile, row: SldRow, params: SldParams, issues: list[Issue]
) -> JointRow | None:
    texts = [t for t in row.texts if t]
    if any(row.texts[2:]):
        issues.append(Issue("S06", "A point may have at most 2 texts.", sld.name, row.index, row.cad))
        return None
    first2 = [t for t in row.texts[:2] if t]
    words = [t for t in first2 if not is_number(t)]
    numbers = [t for t in first2 if is_number(t)]
    if not words:
        issues.append(Issue("S07", "The point has no name.", sld.name, row.index, row.cad))
        return None
    if len(words) > 1:
        issues.append(Issue("S08", "Two names in one point.", sld.name, row.index, row.cad))
        return None
    if len(numbers) > 1:
        issues.append(Issue("S09", "Two values in one point.", sld.name, row.index, row.cad))
        return None

    assert row.cad is not None and texts
    v = float(numbers[0]) if numbers else sld.v
    x, y, z = to_model(
        sld.kind, row.cad[0] / 1000, row.cad[1] / 1000, sld.ox, sld.oy, v, params.z0
    )
    return JointRow(words[0], x, y, z)


def convert(
    params: SldParams,
    csv_paths: list[str | Path],
    connectivity_path: str | Path | None,
    structure_only: bool = False,
    on_stage: Callable[[str], None] | None = None,
) -> ConversionResult:
    """Run everything. With `structure_only`, only the checks that depend on the CSV
    files alone are done (no Connectivity file needed, no frame matching).

    `on_stage` (optional) is called with STAGE_MODEL / STAGE_SLD when a phase starts;
    it may be called from a worker thread."""
    result = ConversionResult()
    issues = result.issues

    def stage(name: str) -> None:
        if on_stage is not None:
            on_stage(name)

    frames = []
    have_model = False  # frames may be matched only when a usable model was read
    if structure_only:
        connectivity_path = None
    elif connectivity_path is None:
        issues.append(Issue("M03", "Connectivity file was not given."))
    else:
        stage(STAGE_MODEL)
        first_new = len(issues)
        frames = load_model_cached(connectivity_path, issues)
        have_model = not any(i.code in _MODEL_UNUSABLE for i in issues[first_new:])

    stage(STAGE_SLD)
    # point name (case-insensitive, like SAP2000) -> "file [Index n]"
    names: dict[str, str] = {}
    for path in discover_files(csv_paths):
        sld = read_sld_csv(path, issues)
        if sld is None:
            continue

        for row in sorted(sld.rows, key=lambda r: r.index):
            if row.cad is None:
                issues.append(Issue("S17", "Row has no coordinates.", sld.name, row.index))
            elif row.has_partial_rect:
                issues.append(Issue("S04", "Incomplete rectangle coordinates.", sld.name, row.index, row.cad))
            elif row.is_rect:
                _process_rect(sld, row, frames, params, result, have_model)
            else:
                joint = _build_joint(sld, row, params, issues)
                if joint is None:
                    continue
                where = f"{sld.name} [Index {row.index}]"
                key = joint.name.casefold()
                if key in names:
                    issues.append(
                        Issue("S10",
                              f"Point name '{joint.name}' is repeated (also in {names[key]}); "
                              "names are not case sensitive.",
                              sld.name, row.index, row.cad)
                    )
                    continue
                names[key] = where
                result.joints.append(joint)

    seen: dict[tuple[float, float, float], JointRow] = {}
    for j in result.joints:
        key = (j.x, j.y, j.z)
        if key in seen:
            issues.append(
                Issue("W01", f"Points {seen[key].name} and {j.name} have the same coordinates.",
                      severity=WARNING)
            )
        else:
            seen[key] = j
    return result


def check_structure(
    csv_paths: list[str | Path],
    on_stage: Callable[[str], None] | None = None,
    z0: float = 0.0,
) -> ConversionResult:
    """Stage 1: every problem that depends on the CSV files only, collected over all files.

    `z0` is the value the user typed; it is needed only so that warning W01 (two points with
    the same coordinates) compares the real coordinates of points of X / Y and Z files.
    """
    return convert(SldParams(z0=z0), csv_paths, None, structure_only=True, on_stage=on_stage)


def _process_rect(
    sld: SldFile,
    row: SldRow,
    frames: list,
    params: SldParams,
    result: ConversionResult,
    have_model: bool,
) -> None:
    issues = result.issues
    if not any(row.texts):
        issues.append(Issue("S05", "Rectangle without any text.", sld.name, row.index, row.cad))
        return
    tokens = parse_texts(row.texts, sld.name, row.index, row.cad, issues)
    if tokens is None or not have_model:
        return
    match = match_rect(sld, row, frames, params, issues)
    if match is None:
        return
    result.loads += records_for(
        tokens, match.frame.name, match.fix_dir, match.abs_a, match.abs_b,
        match.frame.length, params,
    )
