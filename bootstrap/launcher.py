"""Launcher (layer 1: bootstrap). Almost frozen: keep it tiny.

Responsibilities (see docs/contract.md):
  1. Read latest.json from the server (fail-open if unreachable).
  2. If app/runtime changed: download to temp, verify sha256, extract,
     atomic rename into place.
  3. Self-check the new version (ping_app); rollback automatically on failure.
  4. Run the app: src.__main__.main()
  5. Best-effort log to the server.

Only the standard library may be used here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP_NAME = "StructureLab"
SERVER_DIR = Path(r"\\fs\REPLACE\ME\StructureLab")  # TODO: real server path


def read_latest(server_dir: Path) -> dict | None:
    """Return parsed latest.json or None if the server is unreachable."""
    try:
        return json.loads((server_dir / "latest.json").read_text(encoding="utf-8"))
    except OSError:
        return None


def main() -> int:
    # TODO: implement update flow, rollback and app start
    latest = read_latest(SERVER_DIR)
    print("latest.json:", latest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
