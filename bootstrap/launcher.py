"""Launcher (layer 1: bootstrap). Almost frozen: keep it small. Standard library only.

Runs with the small bootstrap Python (``bootstrap\\python\\pythonw.exe``). See docs/contract.md.

Every start:
  1. Read settings.json and latest.json from the server share (3-5 s timeout, fail-open:
     if the share is not reachable, skip the update and just start the installed version).
  2. If the server has a newer app: download the needed zips to a temp folder, verify sha256,
     extract next to the final folder, rename atomically, run the self-check
     (``src.__main__.ping_app()`` with the new runtime + new app). On failure the new folders
     are deleted and the old version stays (automatic rollback).
  3. Start the app with the runtime's pythonw.exe: ``src.__main__.main()``.
  4. The update log stays on the user's PC: ``<root>\\logs\\launcher.log``.

Layout (root = the folder that contains ``bootstrap``; normally %LocalAppData%\\StructureLab):
  bootstrap\\   python + launcher.py + initial.json
  runtime\\<id>\\   embedded Python + libraries (python.exe at the top of this folder)
  app\\<version>\\  contains the ``src`` package
  state.json, settings.json, logs\\, tmp\\
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

BOOTSTRAP_VERSION = "1.0.0"

ROOT = Path(os.environ.get("STRUCTURELAB_ROOT") or Path(__file__).resolve().parent.parent)
STATE_FILE = ROOT / "state.json"
SETTINGS_FILE = ROOT / "settings.json"
INITIAL_FILE = ROOT / "bootstrap" / "initial.json"
LOG_DIR = ROOT / "logs"
TMP_DIR = ROOT / "tmp"
LOCK_FILE = ROOT / "update.lock"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOCK_STALE_SEC = 15 * 60

log = logging.getLogger("launcher")


# ---------------------------------------------------------------- small helpers
def setup_logging() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_DIR / "launcher.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    except OSError:
        log.addHandler(logging.NullHandler())


def message_box(text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, "Structure Lab", 0x10)
    except Exception:  # not Windows, or no UI
        print(text, file=sys.stderr)


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", str(text))) or (0,)


def load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_settings() -> dict:
    cfg = {"server_dir": "", "channel": "stable", "network_timeout_sec": 5}
    cfg.update(load_json(SETTINGS_FILE) or {})
    return cfg


def runtime_python(runtime_id: str, gui: bool) -> Path:
    base = ROOT / "runtime" / runtime_id
    if gui and (base / "pythonw.exe").exists():
        return base / "pythonw.exe"
    return base / "python.exe"


def app_dir(version: str) -> Path:
    return ROOT / "app" / version


def is_installed(state: dict) -> bool:
    return app_dir(state["app"]).is_dir() and runtime_python(state["runtime"], False).exists()


# ---------------------------------------------------------------- state
def load_state() -> dict | None:
    state = load_json(STATE_FILE)
    if state is None:
        initial = load_json(INITIAL_FILE)
        if not initial:
            return None
        state = {"app": initial["app"], "runtime": initial["runtime"], "previous": None,
                 "rejected": [], "notified_min_bootstrap": ""}
        save_json_atomic(STATE_FILE, state)
        log.info("state.json created from initial.json: %s", state)
    state.setdefault("previous", None)
    state.setdefault("rejected", [])
    state.setdefault("notified_min_bootstrap", "")
    return state


# ---------------------------------------------------------------- server access
def read_latest(settings: dict) -> dict | None:
    """Read latest.json with a hard timeout (an unreachable UNC path can block for a long time)."""
    server = settings.get("server_dir")
    if not server:
        log.info("No server_dir in settings.json; update skipped")
        return None
    channel = settings.get("channel", "stable")
    name = "latest.json" if channel == "stable" else f"latest-{channel}.json"
    result: dict = {}

    def work() -> None:
        try:
            result["data"] = json.loads((Path(server) / name).read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - any failure means "no update now"
            result["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(float(settings.get("network_timeout_sec", 5)))
    if thread.is_alive():
        log.warning("Server did not answer in time (%s); update skipped", server)
        return None
    if "error" in result:
        log.warning("Cannot read %s from %s: %s; update skipped", name, server, result["error"])
        return None
    data = result.get("data")
    return data if isinstance(data, dict) else None


def fetch_and_verify(server: Path, entry: dict) -> Path:
    """Copy server\\<file> to tmp\\ while computing sha256; raise if the hash differs."""
    name = entry["file"]
    if Path(name).name != name:
        raise ValueError(f"bad file name in latest.json: {name}")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    dest = TMP_DIR / (name + ".part")
    digest = hashlib.sha256()
    with open(server / name, "rb") as src, open(dest, "wb") as out:
        while chunk := src.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest().lower() != str(entry["sha256"]).lower():
        dest.unlink(missing_ok=True)
        raise ValueError(f"sha256 mismatch for {name}")
    return dest


def extract_to(zip_path: Path, final_dir: Path) -> None:
    """Extract next to final_dir, then rename (atomic on the same drive)."""
    staging = final_dir.with_name(f"{final_dir.name}.tmp-{os.getpid()}")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    root = staging.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():  # zip-slip guard
            if not (staging / member).resolve().is_relative_to(root):
                raise ValueError(f"unsafe path in zip: {member}")
        zf.extractall(staging)
    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)
    os.replace(staging, final_dir)


# ---------------------------------------------------------------- self-check and start
_CHECK = ("import sys; sys.path.insert(0, sys.argv[1]); import src.__main__ as m; "
          "sys.exit(0 if m.ping_app() else 1)")
_RUN = ("import sys; sys.path.insert(0, sys.argv[1]); from src.__main__ import main; "
        "sys.exit(main())")


def child_env() -> dict:
    env = dict(os.environ)
    env["STRUCTURELAB_ROOT"] = str(ROOT)
    return env


def self_check(runtime_id: str, version: str) -> bool:
    exe = runtime_python(runtime_id, gui=False)
    folder = app_dir(version)
    try:
        proc = subprocess.run(
            [str(exe), "-c", _CHECK, str(folder)], cwd=folder, env=child_env(),
            capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("Self-check could not run: %s", exc)
        return False
    if proc.returncode != 0:
        log.error("Self-check failed (code %s): %s", proc.returncode, (proc.stderr or "")[-1500:])
        return False
    return True


def start_app(state: dict) -> int:
    folder = app_dir(state["app"])
    exe = runtime_python(state["runtime"], gui=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    err = open(LOG_DIR / "app_stderr.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [str(exe), "-c", _RUN, str(folder)], cwd=folder, env=child_env(),
        stdout=err, stderr=err, creationflags=NO_WINDOW,
    )
    log.info("App started: app %s, runtime %s, pid %s", state["app"], state["runtime"], proc.pid)
    try:
        code = proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        return 0  # still running after a few seconds: normal
    if code != 0:
        log.error("App exited at start with code %s (see app_stderr.log)", code)
        message_box(f"Structure Lab could not start (code {code}).\nLog: {LOG_DIR}")
    return code


# ---------------------------------------------------------------- update
def acquire_lock() -> bool:
    try:
        if LOCK_FILE.exists() and time.time() - LOCK_FILE.stat().st_mtime > LOCK_STALE_SEC:
            LOCK_FILE.unlink(missing_ok=True)
        os.close(os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except OSError:
        return False


def release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def cleanup(state: dict) -> None:
    """Keep the current and the previous app/runtime only; remove temp leftovers."""
    prev = state.get("previous") or {}
    for kind in ("app", "runtime"):
        keep = {state[kind], prev.get(kind)}
        base = ROOT / kind
        if base.is_dir():
            for d in base.iterdir():
                if d.name not in keep:
                    shutil.rmtree(d, ignore_errors=True)  # may fail if still in use: retried later
    shutil.rmtree(TMP_DIR, ignore_errors=True)


def maybe_update(state: dict, latest: dict, settings: dict) -> dict:
    try:
        app_t, rt_t = latest["app"], latest["runtime"]
        new_ver, new_rt = str(app_t["version"]), str(rt_t["id"])
    except (KeyError, TypeError):
        log.warning("latest.json has an unexpected structure; update skipped")
        return state

    if parse_version(latest.get("min_bootstrap_version", "0")) > parse_version(BOOTSTRAP_VERSION):
        need = str(latest["min_bootstrap_version"])
        log.warning("Update needs bootstrap >= %s (installed %s)", need, BOOTSTRAP_VERSION)
        if state.get("notified_min_bootstrap") != need:
            state["notified_min_bootstrap"] = need
            save_json_atomic(STATE_FILE, state)
            message_box("A new Structure Lab version needs a new installer.\n"
                        "Please ask IT to run the latest Setup.")
        return state

    local = parse_version(state["app"]) if is_installed(state) else (0,)
    if parse_version(new_ver) <= local:
        log.info("Up to date (app %s, server %s)", state["app"], new_ver)
        return state
    key = f"{new_ver}+{new_rt}"
    if key in state["rejected"]:
        log.info("Version %s was rejected by the self-check before; skipped", key)
        return state
    if not acquire_lock():
        log.info("Another instance is updating; skipped")
        return state

    server = Path(settings["server_dir"])
    created: list[Path] = []
    try:
        log.info("Updating: app %s -> %s, runtime %s -> %s", state["app"], new_ver,
                 state["runtime"], new_rt)
        rt_dir, ap_dir = ROOT / "runtime" / new_rt, app_dir(new_ver)
        if not runtime_python(new_rt, False).exists():
            extract_to(fetch_and_verify(server, rt_t), rt_dir)
            created.append(rt_dir)
        if not ap_dir.is_dir():
            extract_to(fetch_and_verify(server, app_t), ap_dir)
            created.append(ap_dir)

        if not self_check(new_rt, new_ver):
            for d in created:
                shutil.rmtree(d, ignore_errors=True)
            state["rejected"].append(key)
            save_json_atomic(STATE_FILE, state)
            log.error("Update %s rejected; rolled back to app %s", key, state["app"])
            return state

        state["previous"] = {"app": state["app"], "runtime": state["runtime"]}
        state["app"], state["runtime"] = new_ver, new_rt
        save_json_atomic(STATE_FILE, state)  # the switch itself: one atomic file replace
        log.info("Update done: app %s, runtime %s", new_ver, new_rt)
        cleanup(state)
    except Exception:
        log.exception("Update failed; keeping the installed version")
        for d in created:
            shutil.rmtree(d, ignore_errors=True)
    finally:
        release_lock()
    return state


# ---------------------------------------------------------------- entry point
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    setup_logging()
    try:
        state = load_state()
        if state is None:
            message_box("Structure Lab is not installed correctly.\nPlease run Setup again.")
            return 1
        if "--no-update" not in argv:
            settings = load_settings()
            latest = read_latest(settings)
            if latest:
                state = maybe_update(state, latest, settings)
        if "--update-only" in argv:
            return 0
        if not is_installed(state):
            prev = state.get("previous")
            if prev and is_installed(prev):
                log.error("Installed version is broken; falling back to %s", prev)
                state = {**state, **prev}
            else:
                message_box("Structure Lab files are damaged.\nPlease run Setup again.")
                return 1
        return start_app(state)
    except Exception:
        log.exception("Launcher crashed")
        message_box(f"Structure Lab could not start.\nLog: {LOG_DIR}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
