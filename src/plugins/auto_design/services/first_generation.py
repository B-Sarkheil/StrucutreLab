"""Auto Design - resume: the SAP2000 models of an existing first generation (no Qt, no SAP).

The first generation folder holds one sub folder per model, and every sub
folder holds one .sdb file. The sub folders can have any names; they are
ordered with a natural sort (Gen-13-2 before Gen-13-10), so for the folders
of an earlier run of this program the first one is the best member
(for example Gen-13-1).
"""
from __future__ import annotations

import re
from pathlib import Path

MIN_MODELS = 2  # the tournament needs two parents


def _natural_key(text: str) -> list:
    # Text and numbers always sit at the same positions, so the keys compare.
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def list_member_models(folder: str | Path) -> list[tuple[str, Path]]:
    """(sub folder name, .sdb path) of every model, in natural order of the
    sub folder names. Sub folders without an .sdb file are ignored. A sub
    folder with several .sdb files must have exactly one that is named like
    the folder. Raises ValueError (all problems together) when the folder
    cannot be used."""

    root = Path(folder)

    if not root.is_dir():
        raise ValueError(f"The first generation folder does not exist: {root}")

    members: list[tuple[str, Path]] = []
    problems: list[str] = []

    subfolders = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: _natural_key(p.name))

    for sub in subfolders:
        models = sorted(
            (f for f in sub.iterdir() if f.is_file() and f.suffix.lower() == ".sdb"),
            key=lambda f: _natural_key(f.name),
        )

        if not models:
            continue

        if len(models) > 1:
            named = [f for f in models if f.stem.casefold() == sub.name.casefold()]

            if len(named) != 1:
                problems.append(f"'{sub.name}' has {len(models)} .sdb files")
                continue

            models = named

        members.append((sub.name, models[0]))

    if problems:
        raise ValueError(
            "Each sub folder must hold one SAP2000 file: " + "; ".join(problems[:5]) + "."
        )

    if len(members) < MIN_MODELS:
        raise ValueError(
            f"The first generation folder needs at least {MIN_MODELS} sub folders "
            f"with a .sdb file (found {len(members)})."
        )

    return members