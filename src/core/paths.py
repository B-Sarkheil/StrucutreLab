"""Central place for all paths (local data, logs, server). Uses platformdirs."""
from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "StructureLab"


def data_dir() -> Path:
    p = user_data_path(APP_NAME, appauthor=False)
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
