"""Helpers for rows read from SAP2000 database tables (no Qt)."""
from __future__ import annotations

from src.core.sap_client import SapError


def pick_field(row: dict[str, str], key: str, table: str) -> str:
    """Value of field `key` (case-insensitive) in a table row."""

    for name, value in row.items():
        if name.lower() == key.lower():
            return value.strip()

    raise SapError(
        f"Field '{key}' not found in table '{table}'. "
        f"Available fields: {', '.join(row)}"
    )