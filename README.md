# Structure Lab

Integrated engineering desktop software for Windows (Python + PySide6) for about 30 users. It gradually replaces scattered MATLAB and Excel-VBA tools. Each tool is a plugin.

First real tool: **Auto Design**, automatic structural section optimization (Genetic Algorithm + SAP2000 OAPI).

Design context lives in two docs in the project knowledge:

* `claude/engineering-platform-decisions.md`: bootstrap / runtime / app layers, auto-update from the server, IT constraints.
* `claude/project-plan-structural-optimization.md`: Auto Design plan (Phase 1 GA, Phase 2 ML surrogate lab, Phase 3 general model).

The user's tested MATLAB program that drives SAP2000 (`connectToSAP.m`, `openSapModel.m`, `modelingOneLine.m`, `designOneLine.m`, `getDesignResultsType1.m`, `modifyProfilesType1.m`, `modifySapModelType1.m`) is also in the project knowledge. It is the reference for SAP2000 API calls; the user can extract the exact method signatures from the DLL in MATLAB on request.

## Layout

```text
StructureLab/
├── bootstrap/          launcher.py, installer.iss (kept stable; contract in docs/contract.md)
├── runtime/            embedded Python 3.12.10 x64 + requirements.txt
├── src/
│   ├── __main__.py     entry point: main(), ping_app()
│   ├── version.py      single source of the version (1.0.0; pyproject.toml must match)
│   ├── core/           app-wide services
│   │   ├── paths.py, config.py, logging_setup.py, storage.py   (small helpers / stubs)
│   │   ├── sap_client.py       SAP2000 connection (pythonnet), shared by all SAP plugins
│   │   └── vendor/sap2000_v23/SAP2000v1.dll    bundled OAPI assembly (user must place it)
│   ├── ui/             shell only: main_window, navigation, home_page, widgets, theme, assets/icons/
│   └── plugins/        base.py, registry.py, placeholder.py, <plugin>/
│       └── auto_design/
│           ├── plugin.py       registers the plugin; create_widget() returns AutoDesignWizard
│           ├── params.py       AutoDesignParams (step 1), SectionPermission (step 2)
│           └── ui/
│               ├── wizard.py           QStackedWidget that moves between the steps and keeps the collected data
│               ├── page.py             step 1: GA settings form
│               └── sections_page.py    step 2: allowed-sections table
├── tools/              build.py, publish.py   (build.py is still only a TODO stub)
├── server_sim/  tests/  docs/  pyproject.toml
```

## How the app works

* `__main__.main()`: QApplication → `apply_theme` → `register_builtin_plugins()` → `MainWindow` → `app.exec()`.
* **Plugin contract** (`plugins/base.py`): `name` (unique key), `title`, `icon`, `description`, `available` (False = planned, not built), and `create_widget() -> QWidget`.
* **Registry** (`plugins/registry.py`): explicit and simple. `register_builtin_plugins()` lists all plugins in navigation order; `load_plugins()` returns them. No auto-discovery yet.
* **Shell** (`ui/`): `MainWindow` reads the registry and passes the plugins to `Navigation` (sidebar) and `HomePage` (one clickable card per plugin). Clicking a sidebar item or a card calls `MainWindow.show_page(key)`. Home is built at startup; each plugin page is created lazily on first open and kept in a `FadeStackedWidget` (a `QStackedWidget` that fades the new page in). If `create_widget()` fails, the error is logged and the current page stays.
* **Not implemented yet:** Auto CPS, SLD to SAP, PDMS to SAP are `PlaceholderPlugin` instances (they open an "Under development" page).
* **Visual language** ("structural drawing sheet"): all colors are tokens at the top of `ui/theme.py` (blueprint-ink surfaces, drafting-cyan linework, amber as the single signal color for active/hover/focus). Titles use Bahnschrift, body uses Segoe UI. Most widgets are styled by `objectName` in the stylesheet; cards, the hero banner and the sidebar marker are painted in code (`ui/widgets.py`, `ui/home_page.py`, `ui/navigation.py`) and read the same tokens. Available tools get large cards, planned tools get dashed rows.

## Auto Design (current state)

A wizard inside the plugin; the shell knows nothing about its steps.

1. **Step 1 – settings form** (`ui/page.py`). Fields and the variable each is stored in: Population Size `popSize`, Tournament Size `tournamentSize`, Number of Generation `genSize` (positive integers); Mutation Percent (%) `mutationPercent` (0–100); Penalize Level Coefficient `penalizeLevel`; Tolerance to Detect Member as Beam or Column (cm) `tolerance` (positive decimals); SAP2000 Reference File `sapPath` (Browse, `.sdb`). Validation runs on Next with inline errors; extra rule: `tournamentSize <= popSize`. Next emits `AutoDesignParams`.
2. **Step 2 – allowed sections** (`ui/sections_page.py`). In a worker thread: connect to SAP2000 (attach to a running instance, else start one) → open `sapPath` → read frame section names (`PropFrame.GetNameList`). Table columns: Section, Is Allowed for Column, Is Allowed for Beam, Is Allowed for Brace. Each cell toggles No/Yes on click or Space/Enter; default No. Loading shows a progress bar; failure shows the message and a Retry button. Next requires at least one Yes and emits `list[SectionPermission]`. A Back button returns to step 1.
3. **Wizard state** (`ui/wizard.py`): `params` (AutoDesignParams), `sections` (the list from step 2, the variable the user asked for), `sap` (the live `SapClient`). Going Back and Next again with the **same** `sapPath` reuses the loaded page (no reconnect, choices kept); a **different** `sapPath` rebuilds step 2 from scratch.
4. **Next steps of the wizard:** not built yet (`_on_sections_accepted` only logs; see its TODO).

### SAP2000 connection decisions (`core/sap_client.py`)

* Uses `pythonnet` with the .NET Framework runtime (`pythonnet.load("netfx")`) and loads `SAP2000v1.dll` directly, like `NET.addAssembly` in the MATLAB code.
* **Only SAP2000 v23 is supported** (company rule: everyone has it). The DLL is bundled in `src/core/vendor/sap2000_v23/SAP2000v1.dll`, so the install path and signature differences between versions do not matter. After connecting, the running SAP version is checked and anything other than v23 gives a clear error. SAP2000 itself must still be installed.
* The DLL is small, so it ships inside the app update package; running it from `%LocalAppData%` is not a problem (confirmed by the user). `build.py`, when written, must copy all files under `src/`, not only `.py`, and `.gitignore` must not exclude this `.dll`.
* `openSapModel.m` also deletes non-`.sdb` files in the model folder; this was **deliberately not ported**.
* The SAP2000 imports are lazy, so the app starts even if `pythonnet` is missing.

### Unverified (never run against a real SAP2000)

* `pythonnet` has to be added to `runtime/requirements.txt` (and `pyproject.toml`).
* `api.cHelper(api.Helper())` (the equivalent of `NET.explicitCast`) in pythonnet.
* Python binding of `ref`/`out` parameters: `PropFrame.GetNameList(0, None)` is assumed to return `(ret, count, names)`; `SapModel.GetVersion("", 0.0)` is assumed to return `(ret, version, number)`. If `GetVersion` fails, the version check only logs a warning.
* `helper.GetObject` behaviour when SAP is not running (the code handles both `None` and an exception).
* The UI of both steps was written without being seen on a real display. Threading: the SAP calls run in a `QThread`; check that SAP's COM/.NET objects work from it.

## Rules

* The shell (`src/ui/`) never contains plugin-specific logic; a plugin never controls the shell. Plugin UI lives in `plugins/<name>/ui/`, business logic in `plugins/<name>/services/`. Code shared by several plugins (like the SAP connection) lives in `src/core/`.
* Do not remove or rename `main()` and `ping_app()` without updating the launcher contract (`ping_app()` is the post-update self-check).
* Create planned files (e.g. Auto Design `services/`) only when they are actually implemented.
* Always use the project runtime; `python` / `py` may not exist globally.
* After changing any code, state which file changed and its exact folder location (project instruction).

## Development

* Windows, VSCode, project Python: `D:\Python Library\StructureLab\runtime\python\python.exe`.
* Run (or F5 with the "Structure Lab" launch config, module `src`): `.\runtime\python\python.exe -m src`
* Install deps: `.\runtime\python\python.exe -m pip install -r .\runtime\requirements.txt`
* Tests / lint: `.\runtime\python\python.exe -m pytest` and `.\runtime\python\python.exe -m ruff check .`

## Status

Done: project structure, embedded runtime, VSCode debugging, dark-themed shell (title bar, sidebar, Home), plugin registry, page switching, Auto Design step 1 (settings form) and step 2 (sections table), SAP2000 connection layer (untested).

Known technical issues to fix next:

* `TitleBar`: `self.window` shadows `QWidget.window()`; dragging should use `startSystemMove()`; no edge resizing.
* Dead `about_name` label in `navigation.py`.
* `plugins/` uses absolute `src.` imports while `ui/` uses relative ones; unify (launcher runs the app from `app\<version>\`). The new Auto Design files and `core/sap_client.py` follow the absolute style.
* Dependencies are listed in both `pyproject.toml` and `runtime/requirements.txt`; dev tools (pytest, ruff, mypy, scikit-learn) must not ship in the release runtime.
* Text glyph icons (⚙ ◈ ⇄ ◇) are inconsistent with the PNG icons; `QApplication([])` should receive `sys.argv`. `logging_setup.py` exists but `setup_logging()` is not called from `main()` yet, so the `logger.info/exception` calls in the new code go nowhere.
* Step 2 does not stop its worker thread if the app closes while loading.

## Next session

1. Put `SAP2000v1.dll` (from the v23 install) in `src/core/vendor/sap2000_v23/`, add `pythonnet` to the runtime requirements, and run step 2 against a real SAP2000. Send any traceback.
2. Ask the user to extract from the v23 DLL (MATLAB `methodsview`): `cPropFrame.GetNameList`, `cFile.OpenFile`, `cSapModel.GetVersion`, `cHelper.GetObject`; fix `sap_client.py` to match.
3. Build the next wizard step after the sections table (the user will describe it). Eventually: GA logic in `plugins/auto_design/services/`, evaluation behind `evaluate(x)`, storing every evaluation from day one (see the plan doc).
4. Write `tools/build.py` (zip `src/` including non-`.py` files, runtime zip, `latest.json` last).
5. Possible small additions the user has not asked for: column "set all Yes/No" and a search box in the sections table.

## Change log

* [1.0.0] - (2026-10-07): 
    - initial shell (PySide6, embedded Python 3.12.10, dark theme, title bar, sidebar)
    - initial plugin architecture
    - plugin registry wired to navigation and Home
    - clickable cards
    - `QStackedWidget` page switching with lazy page creation; `PlaceholderPlugin`
    - new theme with color tokens, Bahnschrift titles
    - drawing-sheet hero banner with a one-time frame draw-in
    - tool cards with hover/focus corner marks
    - dashed rows for planned tools
    - amber marker on the active sidebar item, page fade; `Plugin.available`; nav icon box 40px (fixes clipped 52px button);     duplicate QSS rule removed.
    - Auto Design step 1: GA settings form with validation (`ui/page.py`, `params.py`)
    - Auto Design step 2: allowed-sections table, SAP2000 loaded in a worker thread (`ui/sections_page.py`)
    - `AutoDesignWizard` container (`ui/wizard.py`); `plugin.py` now returns it instead of the placeholder page
    - `core/sap_client.py`: SAP2000 OAPI through pythonnet and a bundled v23 DLL, with a version check