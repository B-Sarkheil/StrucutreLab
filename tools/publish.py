"""Copy dist/publish to the server share. The zips go first, latest.json LAST.

Usage:
  .\\runtime\\python\\python.exe tools\\publish.py
  .\\runtime\\python\\python.exe tools\\publish.py --server \\\\fs\\Software\\StructureLab

The server folder comes from tools/release_config.json (server_dir) unless --server is given.
Users only need read access; the publisher needs write access.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISH = ROOT / "dist" / "publish"
CONFIG = Path(__file__).with_name("release_config.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", help="server folder (overrides release_config.json)")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    server = Path(args.server or cfg["local_server_dir"])
    if "REPLACE" in str(server):
        sys.exit("Set server_dir in tools/release_config.json (or use --server).")
    latest_files = sorted(PUBLISH.glob("latest*.json"))
    if not latest_files:
        sys.exit("dist/publish has no latest.json. Run tools/build.py first.")
    server.mkdir(parents=True, exist_ok=True)

    for latest in latest_files:
        info = json.loads(latest.read_text(encoding="utf-8"))
        for part in (info["app"], info["runtime"]):
            src, dst = PUBLISH / part["file"], server / part["file"]
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                print(f"skip   {part['file']} (already on server)")
                continue
            tmp = server / (part["file"] + ".part")
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            print(f"copied {part['file']}")

    for latest in latest_files:  # last of all
        tmp = server / (latest.name + ".tmp")
        shutil.copyfile(latest, tmp)
        try:
            os.replace(tmp, server / latest.name)
        except OSError:  # share without rename/delete rights: overwrite in place
            shutil.copyfile(latest, server / latest.name)
            tmp.unlink(missing_ok=True)
        print(f"published {latest.name} -> {server}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
