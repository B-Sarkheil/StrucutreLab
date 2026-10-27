"""Tests of the update flow in bootstrap/launcher.py (fake server, no Qt, no Windows needed).

Each test builds a throw-away install root and a fake server share, loads a fresh copy of
launcher.py for it, and runs `maybe_update` / `ask_user`. The runtime "python.exe" is replaced
by the Python that runs the tests, and the installed app is a tiny fake `src` package.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

LAUNCHER_FILE = Path(__file__).resolve().parents[2] / "bootstrap" / "launcher.py"
RUNTIME_ID = "rt1"

FAKE_APP_MAIN = '''
import os, time

def ping_app():
    return True

def ask_update(path):
    answer = os.environ.get("FAKE_ANSWER", "")
    if answer:
        print(answer, flush=True)
    if answer == "UPDATE":
        time.sleep(60)  # like the real window: stays open until the launcher closes it
    return 0 if answer else 3
'''


def load_launcher(root: Path):
    """A fresh copy of launcher.py bound to `root` (ROOT is read at import time)."""
    os.environ["STRUCTURELAB_ROOT"] = str(root)
    spec = importlib.util.spec_from_file_location(f"launcher_{abs(hash(str(root)))}", LAUNCHER_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.runtime_python = lambda runtime_id, gui: Path(sys.executable)
    return module


def make_app_zip(path: Path, marker: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("src/__init__.py", "")
        zf.writestr("src/__main__.py", FAKE_APP_MAIN + f"\nMARKER = {marker!r}\n")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_world(tmp_path: Path, installed="1.1.5", server="1.1.6", **latest_extra):
    """Install root with `installed`, server share with `server`. Returns (launcher, state, latest, settings)."""
    root, share = tmp_path / "root", tmp_path / "share"
    for d in (root, share):
        d.mkdir()

    app = root / "app" / installed / "src"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("")
    (app / "__main__.py").write_text(FAKE_APP_MAIN)
    (root / "runtime" / RUNTIME_ID).mkdir(parents=True)

    app_zip = share / f"app-{server}.zip"
    make_app_zip(app_zip, server)
    latest = {
        "channel": "stable",
        "min_bootstrap_version": "1.0.0",
        "app": {"version": server, "file": app_zip.name, "sha256": sha256_of(app_zip)},
        "runtime": {"id": RUNTIME_ID, "file": "unused.zip", "sha256": "0"},
        **latest_extra,
    }
    state = {"app": installed, "runtime": RUNTIME_ID, "previous": None, "rejected": [],
             "notified_min_bootstrap": ""}
    settings = {"server_dir": str(share), "channel": "stable", "network_timeout_sec": 5}
    return load_launcher(root), state, latest, settings


def test_accepted_update_switches_version(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    asked = []
    launcher.ask_user = lambda s, l, v, m: asked.append((v, m)) or ("update", None)

    state, go = launcher.maybe_update(state, latest, settings)

    assert go is True
    assert asked == [("1.1.6", False)]
    assert state["app"] == "1.1.6" and state["previous"]["app"] == "1.1.5"


def test_later_keeps_installed_version(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    launcher.ask_user = lambda *a: ("later", None)

    state, go = launcher.maybe_update(state, latest, settings)

    assert go is True
    assert state["app"] == "1.1.5"
    assert not launcher.app_dir("1.1.6").exists()  # nothing was downloaded


def test_mandatory_exit_does_not_start_the_app(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path, mandatory=True)
    asked = []
    launcher.ask_user = lambda s, l, v, m: asked.append(m) or ("exit", None)

    state, go = launcher.maybe_update(state, latest, settings)

    assert asked == [True]  # the window is told the update is mandatory
    assert go is False
    assert state["app"] == "1.1.5"


def test_no_question_when_up_to_date(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path, installed="1.1.6", server="1.1.6")

    def boom(*args):
        raise AssertionError("must not ask")

    launcher.ask_user = boom

    state, go = launcher.maybe_update(state, latest, settings)

    assert go is True and state["app"] == "1.1.6"


def test_silent_mode_updates_without_asking(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)

    def boom(*args):
        raise AssertionError("must not ask")

    launcher.ask_user = boom

    state, go = launcher.maybe_update(state, latest, settings, silent=True)

    assert go is True and state["app"] == "1.1.6"


def test_broken_install_is_repaired_without_asking(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    launcher.shutil.rmtree(launcher.app_dir("1.1.5"))  # installed app folder is gone

    def boom(*args):
        raise AssertionError("must not ask")

    launcher.ask_user = boom

    state, go = launcher.maybe_update(state, latest, settings)

    assert go is True and state["app"] == "1.1.6"


def test_bad_sha256_keeps_installed_version_and_closes_window(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    latest["app"]["sha256"] = "0" * 64

    class Window:
        terminated = False

        def terminate(self):
            Window.terminated = True

        def wait(self, timeout=None):
            return 0

    launcher.ask_user = lambda *a: ("update", Window())

    state, go = launcher.maybe_update(state, latest, settings)

    assert go is True and state["app"] == "1.1.5"
    assert Window.terminated  # the "Updating..." window never stays open


def test_ask_user_protocol_update_keeps_window_alive(tmp_path):
    launcher, state, latest, settings = make_world(
        tmp_path, release_notes=[{"version": "1.1.6", "items": ["x"]}])
    os.environ["FAKE_ANSWER"] = "UPDATE"

    try:
        choice, window = launcher.ask_user(state, latest, "1.1.6", mandatory=True)

        assert choice == "update"
        assert window is not None and window.poll() is None  # still showing "Updating..."

        request = json.loads((launcher.TMP_DIR / "update_request.json").read_text("utf-8"))
        assert request["current"] == "1.1.5" and request["new"] == "1.1.6"
        assert request["mandatory"] is True
        assert request["notes"] == [{"version": "1.1.6", "items": ["x"]}]

        launcher.close_dialog(window)
        assert window.poll() is not None
    finally:
        os.environ.pop("FAKE_ANSWER", None)


def test_ask_user_protocol_later_and_exit(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)

    try:
        for answer, expected in (("LATER", "later"), ("EXIT", "exit")):
            os.environ["FAKE_ANSWER"] = answer
            choice, window = launcher.ask_user(state, latest, "1.1.6", mandatory=False)
            assert (choice, window) == (expected, None)
    finally:
        os.environ.pop("FAKE_ANSWER", None)


def test_ask_user_falls_back_when_the_window_cannot_run(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    os.environ["FAKE_ANSWER"] = ""  # the fake window exits with code 3 and prints nothing
    calls = []
    launcher.fallback_prompt = lambda cur, new, m: calls.append((cur, new, m)) or "later"

    try:
        choice, window = launcher.ask_user(state, latest, "1.1.6", mandatory=False)
    finally:
        os.environ.pop("FAKE_ANSWER", None)

    assert (choice, window) == ("later", None)
    assert calls == [("1.1.5", "1.1.6", False)]


def test_old_installed_app_without_ask_update_uses_fallback(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    old_main = launcher.app_dir("1.1.5") / "src" / "__main__.py"
    old_main.write_text("def ping_app():\n    return True\n")  # like 1.1.5: no ask_update
    launcher.fallback_prompt = lambda cur, new, m: "update"

    choice, window = launcher.ask_user(state, latest, "1.1.6", mandatory=False)

    assert (choice, window) == ("update", None)


def test_newer_bootstrap_required_blocks_the_update_and_the_question(tmp_path):
    launcher, state, latest, settings = make_world(tmp_path)
    latest["min_bootstrap_version"] = "9.0.0"
    launcher.message_box = lambda text: None

    def boom(*args):
        raise AssertionError("must not ask")

    launcher.ask_user = boom

    state, go = launcher.maybe_update(state, latest, settings)

    assert go is True and state["app"] == "1.1.5"
