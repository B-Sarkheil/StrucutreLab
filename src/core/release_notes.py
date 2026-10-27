"""Release notes: read them from release_notes.json and decide which ones
the user has not seen yet. Pure logic, no Qt.

``src/release_notes.json`` is written by hand for every release and ships
inside the app package. The last version whose notes the user has seen is
kept in ``<data_dir>/user_state.json`` (not ``state.json``: that file
belongs to the launcher).

Rules:
* Fresh install (no stored version): nothing is shown, the current version
  is stored.
* After an update: every note newer than the stored version and not newer
  than the running version is shown, newest first.
* A version without an entry in the JSON simply has nothing to show.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from src.core.paths import data_dir

logger = logging.getLogger(__name__)

# src/release_notes.json
NOTES_FILE = Path(__file__).resolve().parent.parent / "release_notes.json"
STATE_FILE_NAME = "user_state.json"
LAST_SEEN_KEY = "last_seen_version"

TAGS = ("new", "improved", "fixed")
DEFAULT_TAG = "improved"


@dataclass(frozen=True)
class NoteItem:
    tag: str  # one of TAGS
    text: str


@dataclass(frozen=True)
class ReleaseNote:
    version: str
    date: str
    title: str
    items: tuple[NoteItem, ...]


def parse_version(text: object) -> tuple[int, ...]:
    """'1.1.6' -> (1, 1, 6); anything without digits -> (0,)."""
    return tuple(int(n) for n in re.findall(r"\d+", str(text))) or (0,)


# ---------------------------------------------------------------- reading the notes
def _parse_item(raw: object) -> NoteItem | None:
    if isinstance(raw, str):
        text, tag = raw, DEFAULT_TAG
    elif isinstance(raw, dict):
        text, tag = raw.get("text"), str(raw.get("tag", DEFAULT_TAG)).lower()
    else:
        return None

    text = str(text or "").strip()

    if not text:
        return None

    return NoteItem(tag if tag in TAGS else DEFAULT_TAG, text)


def _parse_entry(raw: object) -> ReleaseNote | None:
    if not isinstance(raw, dict) or not raw.get("version"):
        return None

    raw_items = raw.get("items")
    items = tuple(
        item
        for item in map(_parse_item, raw_items if isinstance(raw_items, list) else [])
        if item is not None
    )

    if not items:
        return None

    return ReleaseNote(
        version=str(raw["version"]),
        date=str(raw.get("date") or ""),
        title=str(raw.get("title") or ""),
        items=items,
    )


def parse_releases(releases: object) -> list[ReleaseNote]:
    """Turn the raw ``releases`` list (from the JSON file or from
    ``latest.json``) into notes, newest first. Bad entries are dropped."""

    if not isinstance(releases, list):
        return []

    notes = [note for note in map(_parse_entry, releases) if note is not None]
    notes.sort(key=lambda note: parse_version(note.version), reverse=True)

    return notes


def load_notes(path: Path = NOTES_FILE) -> list[ReleaseNote]:
    """All release notes, newest first. A broken file gives an empty list."""

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        releases = data["releases"]
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("Cannot read release notes from %s", path, exc_info=True)
        return []

    return parse_releases(releases)


# ---------------------------------------------------------------- what the user has seen
def _state_path() -> Path:
    return data_dir() / STATE_FILE_NAME


def _read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def read_last_seen(state_path: Path | None = None) -> str | None:
    value = _read_state(state_path or _state_path()).get(LAST_SEEN_KEY)

    return str(value) if value else None


def write_last_seen(version: str, state_path: Path | None = None) -> None:
    path = state_path or _state_path()
    state = _read_state(path)
    state[LAST_SEEN_KEY] = str(version)

    tmp = path.with_name(path.name + ".tmp")

    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        logger.warning("Cannot write %s", path, exc_info=True)


def notes_to_show(
    notes: list[ReleaseNote], current: str, last_seen: str
) -> list[ReleaseNote]:
    """Notes newer than `last_seen` and not newer than `current`."""

    low, high = parse_version(last_seen), parse_version(current)

    return [n for n in notes if low < parse_version(n.version) <= high]


def pending_notes(
    current: str,
    notes: list[ReleaseNote] | None = None,
    state_path: Path | None = None,
) -> list[ReleaseNote]:
    """Notes the user should see now (empty on a fresh install)."""

    last_seen = read_last_seen(state_path)

    if last_seen is None:  # fresh install: nothing is new to this user
        write_last_seen(current, state_path)
        return []

    return notes_to_show(
        load_notes() if notes is None else notes, current, last_seen
    )


def mark_seen(current: str, state_path: Path | None = None) -> None:
    """Remember that the user has seen everything up to `current`.

    Never moves the stored version backwards (e.g. after a rollback)."""

    last_seen = read_last_seen(state_path)

    if last_seen is None or parse_version(current) > parse_version(last_seen):
        write_last_seen(current, state_path)
