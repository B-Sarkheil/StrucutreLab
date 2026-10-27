# Frozen contract: bootstrap <-> app

Changing anything here breaks every installed copy and needs a re-install by IT.

## Layout on the user machine
```
%LocalAppData%\Structure Lab\
  bootstrap\            python\ (small embedded Python, no libraries) + launcher.py + initial.json
  runtime\<id>\         embedded Python + libraries (python.exe, pythonw.exe at the top)
  app\<version>\        contains the `src` package
  state.json            {"app", "runtime", "previous", "rejected", ...}  (the switch between versions)
  settings.json         {"server_dir", "channel", "network_timeout_sec"}
  logs\                 launcher.log (update log, local only), app_stderr.log, update_prompt_stderr.log
  tmp\                  downloads and update_request.json (removed after an update)
```
The shortcut runs `bootstrap\python\pythonw.exe bootstrap\launcher.py`.
The launcher runs the app in a child process: `runtime\<id>\pythonw.exe -c "...main()"` with
`sys.path[0] = app\<version>` and the environment variable `STRUCTURELAB_ROOT` (the folder above).

## Functions called by the launcher
- `src.__main__.main() -> int`
- `src.__main__.ping_app() -> bool` (always True; self-check after update, run with the new runtime
  and the new app before the switch; importing `src.__main__` must work without a display)
- `src.__main__.ask_update(request_path: str) -> int` (launcher 1.1.0 and later; see "Asking the
  user" below). Optional: if it is missing or fails, the launcher asks with a Windows message box.

## Server share (read access for users)
```
<server_dir>\latest.json          (latest-<channel>.json for channels other than stable)
<server_dir>\app-<version>.zip    root of the zip = `src\`
<server_dir>\runtime-<id>.zip     root of the zip = contents of runtime\python
```
latest.json fields: `channel`, `min_bootstrap_version`, `app{version,file,sha256}`,
`runtime{id,file,sha256}`, and the optional `release_notes` (list, newest first, same entries as
`src\release_notes.json`) and `mandatory` (true = the user cannot postpone this update).
Versions are three-part numbers. Written last by the publish step.
`runtime.id` = first 12 hex chars of sha256 over the sorted lines of runtime\requirements.txt
and the Python DLL name; a new runtime is downloaded only when this id changes.

## Update rules
Every start: read latest.json with a 5 s timeout. If the server is unreachable: skip (fail-open),
start the installed version. An update is offered only when `app.version` is higher than the
installed one and was not rejected before.

Asking the user (launcher 1.1.0): the launcher writes `tmp\update_request.json`
(`current`, `new`, `mandatory`, `notes`) and starts the INSTALLED app with
`runtime\<id>\python.exe -c "...ask_update(<file>)"` (no console window, stdout piped). The app shows
the "Update available" window and prints ONE line to stdout: `UPDATE`, `LATER` or `EXIT`.
- `LATER`: the installed version starts as usual (asked again at the next start).
- `EXIT` (only possible for a mandatory update): the launcher ends without starting the app.
- `UPDATE`: the window stays open ("Updating...") while the launcher updates, and is terminated by
  the launcher when the update has finished (or failed).
- If the window process dies without an answer (an old app without `ask_update`, a crash, no
  display) the launcher asks with a Windows message box (Yes/No; for a mandatory update an
  information box, then it updates).
No question is asked when the installed version is missing or damaged (it is repaired directly),
or with the launcher argument `--update-only` / `--yes` (for IT scripts).

Then: download to tmp, verify sha256, extract beside the target folder, atomic rename, self-check,
then write state.json (one atomic file replace). Self-check failure deletes the new folders and
records `<app>+<runtime>` in `rejected` (not retried until a new version is published). If an update
fails for any reason, the installed version starts, even for a mandatory update.
Keeps the current and the previous app and runtime. A lock file avoids two instances updating at
once. The update log is local only (logs\launcher.log).
If `min_bootstrap_version` is higher than the installed bootstrap (launcher.py `BOOTSTRAP_VERSION`),
no update is done and the user is told once to ask IT for the new Setup.

## Open questions for IT
- Is server write permission Write Data only? (affects publishing; publish.py falls back to an
  in-place overwrite of latest.json when rename/delete is not allowed)
- AppLocker rules on .pyd / .dll in AppData.
