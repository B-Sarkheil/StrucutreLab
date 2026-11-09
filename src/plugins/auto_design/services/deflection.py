"""Auto Design - beam deflection constraint (no Qt).

For every beam (role Beam) the deflection RELATIVE TO THE CHORD in the
principal direction (local axis 2, bending moment M3) is computed from the
moment diagram of the analysis:  w'' = M3 / EI,  w(0) = w(L) = 0.
It does not depend on the end displacements.

    ratio = (max |w_rel| / L) * n        (n of the goal L / n)

A ratio of 1.0 is exactly the allowed deflection (same scale as the stress DCR).

The load combination chosen by the user is expanded: an Envelope is opened
into its members (recursively) and every non-envelope combination / case is
evaluated on its own; the largest ratio over all of them is kept. Results that
have no sign (StepType Max / Min: response spectrum, moving load, an envelope
that could not be opened) are skipped with a warning; the run goes on. If NO
usable result is found for any beam an error stops the run (otherwise a silent
0 would switch the constraint off).

EI = E * I33 * (I33 modifier). Constant along the beam; shear deformation is
ignored.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.sap_client import SapClient, SapError
from src.plugins.auto_design.services.frame_assignments import read_frame_sections
from src.plugins.auto_design.services.sap_tables import pick_field
from src.plugins.auto_design.services.section_materials import MATERIAL_TABLE, SECTION_TABLE

logger = logging.getLogger(__name__)

STIFFNESS_TABLE = SECTION_TABLE  # field I33 (m^4 in kgf-m-C)
E_TABLE = "Material Properties 02 - Basic Mechanical Properties"  # field E1


@dataclass(frozen=True)
class DeflectionSettings:
    combo: str  # combination (or case) chosen by the user
    divisor: int  # n of L / n
    beams: tuple[str, ...]  # frames with the role Beam
    segments: int = 20  # minimum output segments of every beam
    warned: set = field(default_factory=set, compare=False)  # messages already logged


def _warn(settings: DeflectionSettings, text: str) -> None:
    if text not in settings.warned:
        settings.warned.add(text)
        logger.warning("Deflection: %s", text)


def _to_float(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------------
# Pure numerics
# ---------------------------------------------------------------------


def relative_deflection(stations: list[float], moments: list[float], ei: float) -> float:
    """Largest |w| of the beam relative to its chord (same length unit as the
    stations), from the moments M at the stations (M piecewise linear):
    curvature M/EI is integrated twice (trapezoids) and the straight line
    that joins the two ends is removed."""

    count = len(stations)
    length = stations[-1] - stations[0]

    if count < 3 or length <= 0.0 or ei <= 0.0:
        return 0.0

    slope = [0.0]
    for i in range(1, count):
        dx = stations[i] - stations[i - 1]
        slope.append(slope[-1] + 0.5 * (moments[i - 1] + moments[i]) / ei * dx)

    deflection = [0.0]
    for i in range(1, count):
        dx = stations[i] - stations[i - 1]
        deflection.append(deflection[-1] + 0.5 * (slope[i - 1] + slope[i]) * dx)

    end = deflection[-1]

    return max(
        abs(deflection[i] - (stations[i] - stations[0]) / length * end) for i in range(count)
    )


# ---------------------------------------------------------------------
# Combination expansion
# ---------------------------------------------------------------------

def _has_unsigned_results(client: SapClient, name: str, probe: str) -> bool:
    """True when the combination, selected alone, gives Max / Min rows (an
    envelope). The API has no call for the type of a combination, so it is
    found from the results of one beam."""

    client.deselect_all_for_output()
    client.select_combo_for_output(name)

    return any(
        step.strip().lower() in ("max", "min")
        for _case, step, _station, _moment in client.frame_moments(probe)
    )


def expand_combination(
    client: SapClient, name: str, settings: DeflectionSettings
) -> tuple[list[str], list[str]]:
    """(combinations, load cases) to evaluate: an Envelope (found by its
    Max / Min results) is replaced by its members, everything else is
    evaluated as it is."""

    probe = settings.beams[0]
    combos: list[str] = []
    cases: list[str] = []
    seen: set[str] = set()

    def visit(current: str) -> None:
        if current in seen:
            return

        seen.add(current)

        if not _has_unsigned_results(client, current, probe):
            combos.append(current)
            return

        members = client.combo_members(current)

        if not members:
            _warn(settings, f"'{current}' gives Max/Min results and has no members")

        for is_combo, member in members:
            if is_combo:
                visit(member)
            elif member not in cases:
                cases.append(member)

    visit(name)

    if not combos and not cases:
        raise SapError(f"The deflection combination '{name}' has nothing to evaluate.")

    return combos, cases


# ---------------------------------------------------------------------
# EI of the beams
# ---------------------------------------------------------------------



def read_beam_stiffness(
    client: SapClient, settings: DeflectionSettings
) -> dict[str, float]:
    """Beam -> E * I33 * modifier (kgf-m units). A beam whose value cannot be
    found is left out with a warning."""

    sections = read_frame_sections(client)

    section_rows = client.read_table(STIFFNESS_TABLE)
    i33 = {
        pick_field(r, "SectionName", STIFFNESS_TABLE): _to_float(
            pick_field(r, "I33", STIFFNESS_TABLE)
        )
        for r in section_rows
    }
    material_of = {
        pick_field(r, "SectionName", STIFFNESS_TABLE): pick_field(r, "Material", STIFFNESS_TABLE)
        for r in section_rows
    }
    modulus = {
        pick_field(r, "Material", E_TABLE): _to_float(pick_field(r, "E1", E_TABLE))
        for r in client.read_table(E_TABLE)
    }

    result: dict[str, float] = {}

    for frame in settings.beams:
        section = sections.get(frame, "")
        inertia = i33.get(section)
        young = modulus.get(material_of.get(section, ""))

        if not inertia or not young:
            _warn(settings, f"beam '{frame}' (section '{section}'): no E or I33, skipped")
            continue

        result[frame] = young * inertia * client.frame_i33_modifier(frame)

    return result


# ---------------------------------------------------------------------
# The reader (element constraint: frame -> ratio)
# ---------------------------------------------------------------------


def read_deflection_ratios(client: SapClient, settings: DeflectionSettings) -> dict[str, float]:
    """Beam -> deflection ratio (1.0 = the allowed deflection). Needs the
    analysis to have run. Changes the output selection of the model."""

    combos, cases = expand_combination(client, settings.combo, settings)

    client.deselect_all_for_output()

    for name in combos:
        client.select_combo_for_output(name)

    for name in cases:
        client.select_case_for_output(name)

    stiffness = read_beam_stiffness(client, settings)
    result: dict[str, float] = {}

    for frame in settings.beams:
        ei = stiffness.get(frame)

        if ei is None:
            continue

        by_case: dict[str, list[tuple[float, float]]] = {}

        for case, step_type, station, moment in client.frame_moments(frame):
            if step_type.strip().lower() in ("max", "min"):
                _warn(
                    settings,
                    f"'{case}' has Max/Min results without sign (response spectrum, "
                    "moving load or an envelope): skipped",
                )
                continue

            by_case.setdefault(case, []).append((station, moment))

        best = None

        for case, points in by_case.items():
            points.sort(key=lambda p: p[0])
            stations = [p[0] for p in points]
            length = stations[-1] - stations[0]

            if length <= 0.0:
                continue

            ratio = relative_deflection(stations, [p[1] for p in points], ei) / length
            ratio *= settings.divisor
            best = ratio if best is None else max(best, ratio)

        if best is not None:
            result[frame] = best

    if not result:
        raise SapError(
            f"No usable deflection result for any beam (combination '{settings.combo}'). "
            "Check the combination and the output selection."
        )

    logger.info(
        "Deflection: %d beams, worst ratio %.3f", len(result), max(result.values())
    )

    return result