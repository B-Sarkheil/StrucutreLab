"""Auto Design - frame classification (`classify_frame`, `classify_frames`) and
`build_gene_options` with the roles. Pure logic: no Qt, no SAP2000."""
from __future__ import annotations

import pytest

from src.plugins.auto_design.params import SectionPermission
from src.plugins.auto_design.services.population import (
    BEAM,
    COLUMN,
    HORIZONTAL_BRACE,
    VERTICAL_BRACE,
    build_gene_options,
    classify_frame,
    classify_frames,
)

TOL = 1.0  # cm  -> 0.01 m


def _classify(i, j, tolerance=TOL):
    """Classify a frame from joint 1 at `i` to joint 2 at `j` (x, y, z in m)."""

    return classify_frame("F", {"F": ("1", "2")}, {"1": i, "2": j}, tolerance)


# the eight cases of the agreed table (small = <= tolerance)
@pytest.mark.parametrize(
    ("j", "expected"),
    [
        ((0.0, 5.0, 0.0), BEAM),  # dz small, dx small, dy big
        ((5.0, 0.0, 0.0), BEAM),  # dz small, dx big, dy small
        ((5.0, 5.0, 0.0), HORIZONTAL_BRACE),  # dz small, dx big, dy big
        ((0.0, 0.0, 3.0), COLUMN),  # dx small, dy small, dz big
        ((0.0, 4.0, 3.0), VERTICAL_BRACE),  # in the yz plane
        ((4.0, 0.0, 3.0), VERTICAL_BRACE),  # in the xz plane
        ((4.0, 4.0, 3.0), VERTICAL_BRACE),  # outside both planes
    ],
)
def test_the_table(j, expected):
    assert _classify((0.0, 0.0, 0.0), j) == expected


def test_reversed_direction_gives_the_same_role():
    assert _classify((5.0, 0.0, 3.0), (5.0, 0.0, 0.0)) == COLUMN
    assert _classify((5.0, 5.0, 3.0), (0.0, 0.0, 3.0)) == HORIZONTAL_BRACE


def test_column_does_not_need_a_big_dz():
    # dx and dy small, dz also small but not zero length (dz = 2 cm > 1 cm)
    assert _classify((0.0, 0.0, 0.0), (0.0, 0.0, 0.02)) == COLUMN


def test_zero_length_is_an_error():
    with pytest.raises(ValueError, match="zero length"):
        _classify((1.0, 2.0, 3.0), (1.005, 2.0, 3.0))


def test_boundary_is_small_even_with_float_rounding():
    # 3.01 - 3.00 = 0.010000000000000009 in floating point: still "small"
    assert _classify((0.0, 0.0, 3.00), (0.0, 5.0, 3.01)) == BEAM
    # just above the tolerance is "big": a beam with dz = 1.1 cm is a brace
    assert _classify((0.0, 0.0, 3.00), (0.0, 5.0, 3.011)) == VERTICAL_BRACE


def test_tolerance_is_in_cm():
    j = (0.0, 5.0, 0.05)  # dz = 5 cm
    assert _classify((0.0, 0.0, 0.0), j, tolerance=1.0) == VERTICAL_BRACE
    assert _classify((0.0, 0.0, 0.0), j, tolerance=5.0) == BEAM


def test_unknown_frame_and_joint():
    with pytest.raises(ValueError, match="Frame 'X'"):
        classify_frame("X", {}, {}, TOL)

    with pytest.raises(ValueError, match="joint '2'"):
        classify_frame("F", {"F": ("1", "2")}, {"1": (0, 0, 0)}, TOL)


def test_classify_frames_keeps_order_and_reports_all_problems():
    connectivity = {"1": ("a", "b"), "2": ("a", "c"), "3": ("a", "a2"), "4": ("a", "zz")}
    joints = {
        "a": (0.0, 0.0, 0.0),
        "b": (0.0, 0.0, 3.0),
        "c": (6.0, 0.0, 0.0),
        "a2": (0.0, 0.0, 0.0),
    }

    roles = classify_frames(["1", "2"], connectivity, joints, TOL)
    assert list(roles.items()) == [("1", COLUMN), ("2", BEAM)]

    with pytest.raises(ValueError) as error:
        classify_frames(["1", "3", "4"], connectivity, joints, TOL)

    text = str(error.value)
    assert "2 frame(s)" in text and "Frame '3'" in text and "Frame '4'" in text


def test_build_gene_options_uses_role_and_material():
    sections = [
        SectionPermission("C1", allowedForColumn=True, materialType="Steel"),
        SectionPermission("B1", allowedForBeam=True, materialType="Steel"),
        SectionPermission("B2", allowedForBeam=True, materialType="Steel"),
        SectionPermission("CC", allowedForBeam=True, materialType="Concrete"),
    ]
    frame_sections = {"1": "C1", "2": "B1"}

    options = build_gene_options(frame_sections, {"1": COLUMN, "2": BEAM}, sections)
    assert options == {"1": ["C1"], "2": ["B1", "B2"]}

    # the user changed frame 1 to a beam on the Frame types page
    options = build_gene_options(frame_sections, {"1": BEAM, "2": BEAM}, sections)
    assert options["1"] == ["B1", "B2"]

    with pytest.raises(ValueError, match="no Steel section is allowed for horizontalBrace"):
        build_gene_options(frame_sections, {"1": HORIZONTAL_BRACE, "2": BEAM}, sections)
