"""Tests for src/core/release_notes.py (pure logic, no Qt)."""
from __future__ import annotations

import json

from src.core import release_notes as rn


def _write(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _note(version: str, text: str = "x") -> rn.ReleaseNote:
    return rn.ReleaseNote(version, "", "", (rn.NoteItem("new", text),))


def test_parse_version():
    assert rn.parse_version("1.1.6") == (1, 1, 6)
    assert rn.parse_version("1.1.10") > rn.parse_version("1.1.9")
    assert rn.parse_version("garbage") == (0,)


def test_load_notes_sorted_and_tolerant(tmp_path):
    path = tmp_path / "notes.json"
    _write(
        path,
        {
            "releases": [
                {"version": "1.1.5", "items": ["plain string item"]},
                {
                    "version": "1.1.10",
                    "date": "2026-11-01",
                    "title": "T",
                    "items": [
                        {"tag": "NEW", "text": "  upper-case tag  "},
                        {"tag": "weird", "text": "unknown tag"},
                        {"tag": "fixed", "text": "   "},
                        42,
                    ],
                },
                {"version": "1.1.7", "items": []},  # no items: dropped
                {"items": ["no version"]},  # no version: dropped
                "not a dict",
            ]
        },
    )

    notes = rn.load_notes(path)

    assert [n.version for n in notes] == ["1.1.10", "1.1.5"]
    assert [(i.tag, i.text) for i in notes[0].items] == [
        ("new", "upper-case tag"),
        ("improved", "unknown tag"),
    ]
    assert notes[1].items[0].tag == rn.DEFAULT_TAG


def test_load_notes_broken_file(tmp_path):
    missing = tmp_path / "missing.json"
    assert rn.load_notes(missing) == []

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert rn.load_notes(bad) == []

    wrong = tmp_path / "wrong.json"
    _write(wrong, {"releases": "nope"})
    assert rn.load_notes(wrong) == []


def test_shipped_notes_file_is_valid():
    notes = rn.load_notes()

    assert notes
    assert all(n.items for n in notes)


def test_notes_to_show_range():
    notes = [_note("1.1.7"), _note("1.1.6"), _note("1.1.5"), _note("1.1.4")]

    shown = rn.notes_to_show(notes, current="1.1.6", last_seen="1.1.4")

    # newer than 1.1.4, not newer than 1.1.6; 1.1.7 is not installed yet
    assert [n.version for n in shown] == ["1.1.6", "1.1.5"]
    assert rn.notes_to_show(notes, "1.1.6", "1.1.6") == []


def test_fresh_install_shows_nothing_and_stores_version(tmp_path):
    state = tmp_path / "user_state.json"

    assert rn.pending_notes("1.1.6", [_note("1.1.6")], state) == []
    assert rn.read_last_seen(state) == "1.1.6"


def test_update_shows_notes_once(tmp_path):
    state = tmp_path / "user_state.json"
    notes = [_note("1.1.6"), _note("1.1.5")]
    rn.write_last_seen("1.1.5", state)

    shown = rn.pending_notes("1.1.6", notes, state)
    assert [n.version for n in shown] == ["1.1.6"]

    # not remembered until the user closed the window
    assert rn.read_last_seen(state) == "1.1.5"

    rn.mark_seen("1.1.6", state)
    assert rn.pending_notes("1.1.6", notes, state) == []


def test_mark_seen_never_goes_backwards(tmp_path):
    state = tmp_path / "user_state.json"
    rn.write_last_seen("1.1.8", state)

    rn.mark_seen("1.1.6", state)  # e.g. after a rollback

    assert rn.read_last_seen(state) == "1.1.8"


def test_state_keeps_other_keys(tmp_path):
    state = tmp_path / "user_state.json"
    _write(state, {"other": 1})

    rn.write_last_seen("1.1.6", state)

    data = json.loads(state.read_text(encoding="utf-8"))
    assert data == {"other": 1, rn.LAST_SEEN_KEY: "1.1.6"}


def test_parse_releases_from_latest_json_shape():
    raw = [
        {"version": "1.1.5", "items": ["a"]},
        {"version": "1.1.6", "items": [{"tag": "fixed", "text": "b"}]},
        {"version": "", "items": ["no version"]},
    ]

    notes = rn.parse_releases(raw)

    assert [n.version for n in notes] == ["1.1.6", "1.1.5"]
    assert rn.parse_releases(None) == []
    assert rn.parse_releases("nope") == []
