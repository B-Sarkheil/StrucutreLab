"""Auto Design - the database folder of a run (no Qt): check, describe, clear.

The run starts by deleting everything inside the database folder (the
wizard asks the user first). Because a wrong folder would be a disaster,
`check_folder_usable` refuses the dangerous ones.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

GENERATION_PREFIX = "Generation-"


@dataclass(frozen=True)
class FolderState:
    exists: bool
    itemCount: int  # files and folders directly inside
    generationFolders: int  # "Generation-*" folders directly inside


def check_folder_usable(folder: str | Path, sap_path: str | Path) -> str | None:
    """None when the folder may be used (and cleared), else the reason why not."""

    path = Path(folder).resolve()

    if path.exists() and not path.is_dir():
        return "The database path is a file, not a folder."

    if path == Path(path.anchor):
        return "The database folder cannot be the root of a drive."

    if path == Path.home().resolve():
        return "The database folder cannot be your user folder."

    if sap_path:
        reference = Path(sap_path).resolve()

        if reference == path or path in reference.parents:
            return (
                "The SAP2000 reference file is inside the database folder, "
                "and the folder is cleared at the start of every run. "
                "Choose another database folder."
            )

    return None


def describe_folder(folder: str | Path) -> FolderState:
    path = Path(folder)

    if not path.is_dir():
        return FolderState(False, 0, 0)

    items = list(path.iterdir())
    generations = sum(
        1 for item in items if item.is_dir() and item.name.startswith(GENERATION_PREFIX)
    )

    return FolderState(True, len(items), generations)


def _make_writable_and_retry(function, path, _error) -> None:
    # Handler of shutil.rmtree: a read-only file is made writable, then retried.
    os.chmod(path, stat.S_IWRITE)
    function(path)


def clear_folder(folder: str | Path) -> None:
    """Delete everything inside `folder` (the folder itself stays; it is
    created when missing)."""

    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)

    for child in path.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, onexc=_make_writable_and_retry)
            else:
                try:
                    child.unlink()
                except PermissionError:
                    os.chmod(child, stat.S_IWRITE)
                    child.unlink()
        except OSError as exc:
            raise RuntimeError(
                f"Could not delete '{child}': {exc}. "
                "Close it (Explorer, SAP2000, Excel ...) and run again."
            ) from exc

    logger.info("Database folder cleared: %s", path)