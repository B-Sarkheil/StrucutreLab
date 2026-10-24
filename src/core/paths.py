"""Central place for all paths (local data, logs, server). Uses platformdirs."""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "Structure Lab"


def data_dir() -> Path:
    # Installed copy: the launcher sets STRUCTURELAB_ROOT to %LocalAppData%\Structure Lab.
    env = os.environ.get("STRUCTURELAB_ROOT")
    p = Path(env) if env else user_data_path(APP_NAME, appauthor=False)
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    p = data_dir() / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p
