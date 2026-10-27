"""Build the release packages into dist/.

Usage (project runtime):
  .\\runtime\\python\\python.exe tools\\build.py             # packages only -> dist\\publish\\
  .\\runtime\\python\\python.exe tools\\build.py --mandatory # users must update (no "Later" button)
  .\\runtime\\python\\python.exe tools\\build.py --installer # + dist\\stage and Setup.exe (needs Inno Setup 6)

Outputs
  dist\\publish\\app-<version>.zip        src\\ (every file under src/, not only .py)
  dist\\publish\\runtime-<id>.zip         copy of runtime\\python (dev tools removed); rebuilt only
                                         when runtime\\requirements.txt or the Python version changes
  dist\\publish\\latest.json              written LAST, so a half-built release is never seen.
                                         Besides the packages it carries `release_notes` (the newest
                                         entries of src\\release_notes.json, shown in the update
                                         window) and, with --mandatory, `"mandatory": true`.
  dist\\stage\\                           what the installer puts in %LocalAppData%\\Structure Lab
  dist\\StructureLab-Setup.exe           with --installer

The folder dist\\publish is what publish.py copies to the server share.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PUBLISH = DIST / "publish"
STAGE = DIST / "stage"
RUNTIME_SRC = ROOT / "runtime" / "python"
CONFIG = Path(__file__).with_name("release_config.json")
NOTES_FILE = ROOT / "src" / "release_notes.json"
NOTES_IN_LATEST = 10  # newest entries copied into latest.json

# top-level names inside site-packages that must not ship to users
DEV_ONLY = ("pytest", "_pytest", "pytestqt", "pytest_qt", "pluggy", "iniconfig", "ruff",
            "mypy", "mypyc", "mypy_extensions", "sklearn", "scikit_learn", "coverage")


# The dev _pth contains "..\..\" (project root, so that `python -m src` works). Not for users.
PTH_PACKAGED = "python312.zip\r\n.\r\nimport site\r\n"


def pth_name() -> str:
    found = list(RUNTIME_SRC.glob("python3*._pth"))
    if not found:
        sys.exit("No python3xx._pth in runtime/python")
    return found[0].name


def read_config() -> dict:
    cfg = {"server_dir": "", "channel": "stable", "min_bootstrap_version": "1.1.0"}
    cfg.update(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
    return cfg


def read_version() -> str:
    text = (ROOT / "src" / "version.py").read_text(encoding="utf-8")
    m = re.search(r"""(?:__version__|VERSION|version)\s*(?::\s*\w+\s*)?=\s*["']([^"']+)["']""", text)
    if not m:
        sys.exit("Cannot find the version in src/version.py")
    version = m.group(1)
    pp = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    if pp and pp.group(1) != version:
        sys.exit(f"Version mismatch: src/version.py={version}, pyproject.toml={pp.group(1)}")
    return version


def version_key(text: object) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", str(text))) or (0,)


def read_release_notes(version: str) -> list[dict]:
    """The newest entries of src/release_notes.json, as they are written there.

    The file is optional for the build (an update window without notes is fine), but a missing
    entry for the version being built is reported, because it is usually a forgotten step."""
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8-sig"))
        releases = [r for r in data["releases"] if isinstance(r, dict) and r.get("version")]
    except (OSError, ValueError, KeyError, TypeError):
        print(f"notes    WARNING: cannot read {NOTES_FILE}; the update window will have no notes")
        return []
    releases.sort(key=lambda r: version_key(r["version"]), reverse=True)
    if not any(version_key(r["version"]) == version_key(version) for r in releases):
        print(f"notes    WARNING: src/release_notes.json has no entry for {version}")
    return releases[:NOTES_IN_LATEST]


def runtime_id() -> str:
    lines = (ROOT / "runtime" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    reqs = sorted({ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")})
    dlls = sorted(p.name for p in RUNTIME_SRC.glob("python3*.dll"))
    return hashlib.sha256("\n".join(reqs + dlls).encode()).hexdigest()[:12]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def skip_runtime(rel: Path) -> bool:
    parts = [p.lower() for p in rel.parts]
    if "__pycache__" in parts or rel.suffix == ".pyc":
        return True
    if parts[0] == "scripts" or rel.suffix.lower() == "._pth" or rel.name.lower().endswith("._pth"):
        return True  # pip launchers have absolute paths; _pth is replaced by PTH_PACKAGED
    if "site-packages" in parts:
        i = parts.index("site-packages")
        if i + 1 < len(parts):
            return parts[i + 1].startswith(DEV_ONLY)
    return False


def zip_tree(base: Path, out: Path, prefix: str = "", skip=lambda rel: False) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(base)
            if path.is_file() and not skip(rel) and "__pycache__" not in rel.parts \
                    and path.suffix != ".pyc":
                zf.write(path, (Path(prefix) / rel).as_posix())
    os.replace(tmp, out)


def build_packages(version: str, cfg: dict, mandatory: bool = False) -> tuple[Path, Path, str]:
    PUBLISH.mkdir(parents=True, exist_ok=True)
    for old in PUBLISH.glob("latest*.json"):
        old.unlink()  # a stale latest.json must never point at half-built files

    app_zip = PUBLISH / f"app-{version}.zip"
    zip_tree(ROOT / "src", app_zip, prefix="src")
    print(f"app      {app_zip.name}  {app_zip.stat().st_size / 1e6:.1f} MB")

    rid = runtime_id()
    rt_zip = PUBLISH / f"runtime-{rid}.zip"
    if rt_zip.exists():
        print(f"runtime  {rt_zip.name}  (unchanged, reused)")
    else:
        if not RUNTIME_SRC.is_dir():
            sys.exit(f"Runtime folder not found: {RUNTIME_SRC}")
        zip_tree(RUNTIME_SRC, rt_zip, skip=skip_runtime)
        with zipfile.ZipFile(rt_zip, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(pth_name(), PTH_PACKAGED)
        print(f"runtime  {rt_zip.name}  {rt_zip.stat().st_size / 1e6:.1f} MB")

    latest = {
        "channel": cfg["channel"],
        "min_bootstrap_version": cfg["min_bootstrap_version"],
        "app": {"version": version, "file": app_zip.name, "sha256": sha256_of(app_zip)},
        "runtime": {"id": rid, "file": rt_zip.name, "sha256": sha256_of(rt_zip)},
        "release_notes": read_release_notes(version),
    }
    if mandatory:
        latest["mandatory"] = True
        print("mandatory  users cannot postpone this update")
    name = "latest.json" if cfg["channel"] == "stable" else f"latest-{cfg['channel']}.json"
    (PUBLISH / name).write_text(json.dumps(latest, indent=2), encoding="utf-8")  # LAST
    print(f"{name} written")
    return app_zip, rt_zip, rid


def build_stage(version: str, cfg: dict, app_zip: Path, rt_zip: Path, rid: str) -> None:
    shutil.rmtree(STAGE, ignore_errors=True)
    boot = STAGE / "bootstrap"
    (boot / "python").mkdir(parents=True)
    for f in RUNTIME_SRC.iterdir():  # top-level files only: python.exe, dlls, stdlib zip
        if f.is_file() and not f.name.endswith("._pth"):
            shutil.copy2(f, boot / "python" / f.name)
    (boot / "python" / pth_name()).write_text(PTH_PACKAGED, encoding="ascii")
    shutil.copy2(ROOT / "bootstrap" / "launcher.py", boot / "launcher.py")
    icon = find_icon(cfg)
    if icon:
        shutil.copy2(icon, boot / "app.ico")  # shortcut + Setup.exe icon
        print(f"icon     {icon}")
    else:
        print("icon     NOT FOUND: set \"icon\" in tools/release_config.json")
    (boot / "initial.json").write_text(json.dumps({"app": version, "runtime": rid}), "utf-8")
    (STAGE / "settings.json").write_text(
        json.dumps({"server_dir": cfg["server_dir"], "channel": cfg["channel"],
                    "network_timeout_sec": 5}, indent=2), encoding="utf-8")
    with zipfile.ZipFile(rt_zip) as zf:
        zf.extractall(STAGE / "runtime" / rid)
    with zipfile.ZipFile(app_zip) as zf:
        zf.extractall(STAGE / "app" / version)
    print(f"stage    {STAGE}")


def find_icon(cfg: dict) -> Path | None:
    """release_config.json "icon" (relative to the project root), else the first .ico in src/."""
    if cfg.get("icon"):
        p = ROOT / cfg["icon"]
        return p if p.exists() else None
    found = sorted((ROOT / "src").rglob("*.ico"))
    return found[0] if found else None


def find_iscc(hint: str | None) -> str:
    candidates = [hint, shutil.which("ISCC"),
                  *[p for v in ("7", "6") for p in (
                      rf"C:\Program Files (x86)\Inno Setup {v}\ISCC.exe",
                      rf"C:\Program Files\Inno Setup {v}\ISCC.exe",
                      str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
                          / f"Inno Setup {v}" / "ISCC.exe"))]]
    for c in candidates:
        if c and Path(c).exists():
            return c
    sys.exit("ISCC.exe (Inno Setup 6) not found. Install it or pass --iscc <path>.")


def build_installer(version: str, rid: str, iscc: str | None) -> None:
    cmd = [find_iscc(iscc), f"/DAppVersion={version}", f"/DRuntimeId={rid}",
           f"/DStageDir={STAGE}", f"/O{DIST}", str(ROOT / "bootstrap" / "installer.iss")]
    subprocess.run(cmd, check=True)
    print(f"setup    {DIST / 'StructureLab-Setup.exe'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", action="store_true", help="also stage files and build Setup.exe")
    ap.add_argument("--mandatory", action="store_true",
                    help="users must update: the update window has no Later button")
    ap.add_argument("--iscc", help="path to ISCC.exe")
    args = ap.parse_args()

    cfg = read_config()
    version = read_version()
    print(f"Structure Lab {version}")
    app_zip, rt_zip, rid = build_packages(version, cfg, mandatory=args.mandatory)
    if args.installer:
        build_stage(version, cfg, app_zip, rt_zip, rid)
        build_installer(version, rid, args.iscc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
