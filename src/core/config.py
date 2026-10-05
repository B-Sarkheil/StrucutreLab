"""App settings (pydantic). TODO: load/save a JSON file in data_dir()."""
from __future__ import annotations

from pydantic import BaseModel


class Settings(BaseModel):
    server_dir: str = ""
    channel: str = "stable"  # stable | beta
