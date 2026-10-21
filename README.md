# Structure Lab

Integrated engineering desktop software for Windows (Python + PySide6) for about 30 users. It gradually replaces scattered MATLAB and Excel-VBA tools. Each tool is a plugin.

First real tool: **Auto Design**, automatic structural section optimization (Genetic Algorithm + SAP2000 OAPI). Second tool: **SLD to SAP**, loading the SAP2000 model from piping SLD files exported from AutoCAD.

Design context lives in these docs in the project knowledge:

* `claude/engineering-platform-decisions.md`: bootstrap / runtime / app layers, auto-update from the server, IT constraints.
* `claude/project-plan-structural-optimization.md`: Auto Design plan (Phase 1 GA, Phase 2 ML surrogate lab, Phase 3 general model).
* `docs/sld_to_sap_algorithm.md`: the SLD to SAP algorithm guide (draft 0.1). It is the reference: the code must match it; if they disagree, one of them must be fixed.

The user's tested MATLAB program that drives SAP2000 (`connectToSAP.m`, `openSapModel.m`, `modelingOneLine.m`, `designOneLine.m`, `getDesignResultsType1.m`, `modifyProfilesType1.m`, `modifySapModelType1.m`) is also in the project knowledge. It is the reference for SAP2000 API calls; the user can extract the exact method signatures from the DLL in MATLAB on request. The MATLAB reference of SLD to SAP is `SLD2SAP.m` (v1.4) with `SLD2SAP.lsp`.

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
│       ├── auto_design/
│       │   ├── plugin.py       registers the plugin; create_widget() returns AutoDesignWizard
│       │   ├── params.py       AutoDesignParams, SectionPermission (step 2: four roles)
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   └── sections_excel.py   Excel import / export of the sections table (no Qt)
│       │   └── ui/
│       │       ├── wizard.py           QStackedWidget that moves between the steps and keeps the collected data
│       │       ├── page.py             step 1: GA settings form
│       │       └── sections_page.py    step 2: allowed-sections table
│       └── sld_to_sap/
│           ├── plugin.py       SldToSapPlugin; create_widget() returns SldToSapPage (lazy import)
│           ├── params.py       SldParams (z0, tolerance_mm, end_tolerance_mm, eqz_coef, friction_coef)
│           ├── services/       pure logic, no Qt (one module per step of the algorithm guide)
│           │   ├── issues.py       Issue (code, message, file, Index, CAD coordinates, severity)
│           │   ├── geometry.py     round_mm (MATLAB-style rounding), CAD to model conversion
│           │   ├── sld_reader.py   CSV reading, number/word rule, origin row detection
│           │   ├── connectivity.py frames and joints from the SAP2000 Excel export
│           │   ├── matcher.py      frame under a load rectangle (elevation and plan)
│           │   ├── load_rules.py   token table (V/FV/HS/LS/HT/LT) to load records
│           │   ├── pipeline.py     convert(), check_structure(), ConversionResult
│           │   └── exporter.py     the two SAP2000 import tables (.xlsx)
│           └── ui/
│               └── page.py         single page: inputs, automatic checks, issue table, Convert
├── tools/              build.py, publish.py   (build.py is still only a TODO stub)
├── server_sim/  docs/  pyproject.toml
└── tests/
    ├── auto_design/
    └── sld_to_sap/
        └── test_sld_to_sap.py
```

## How the app works

* `__main__.main()`: QApplication → `apply_theme` → `register_builtin_plugins()` → `MainWindow` → `app.exec()`.
* **Plugin contract** (`plugins/base.py`): `name` (unique key), `title`, `icon`, `description`, `available` (False = planned, not built), and `create_widget() -> QWidget`.
* **Registry** (`plugins/registry.py`): explicit and simple. `register_builtin_plugins()` lists all plugins in navigation order (Auto Design, SLD to SAP, then the placeholders); `load_plugins()` returns them. No auto-discovery yet.
* **Shell** (`ui/`): `MainWindow` reads the registry and passes the plugins to `Navigation` (sidebar) and `HomePage` (one clickable card per plugin). Clicking a sidebar item or a card calls `MainWindow.show_page(key)`. Home is built at startup; each plugin page is created lazily on first open and kept in a `FadeStackedWidget` (a `QStackedWidget` that fades the new page in). If `create_widget()` fails, the error is logged and the current page stays.
* **Not implemented yet:** Auto CPS and PDMS to SAP are `PlaceholderPlugin` instances (they open an "Under development" page).
* **Visual language** ("structural drawing sheet"): all colors are tokens at the top of `ui/theme.py` (blueprint-ink surfaces, drafting-cyan linework, amber as the single signal color for active/hover/focus). Titles use Bahnschrift, body uses Segoe UI. Most widgets are styled by `objectName` in the stylesheet; cards, the hero banner and the sidebar marker are painted in code (`ui/widgets.py`, `ui/home_page.py`, `ui/navigation.py`) and read the same tokens. Available tools get large cards, planned tools get dashed rows.

## Auto Design (current state)

A wizard inside the plugin; the shell knows nothing about its steps.

1. **Step 1 – settings form** (`ui/page.py`). Fields and the variable each is stored in: Population Size `popSize`, Tournament Size `tournamentSize`, Number of Generation `genSize` (positive integers); Mutation Percent (%) `mutationPercent` (0–100); Penalize Level Coefficient `penalizeLevel`; Tolerance to Detect Member as Beam or Column (cm) `tolerance` (positive decimals); SAP2000 Reference File `sapPath` (Browse, `.sdb`). Validation runs on Next with inline errors; extra rule: `tournamentSize <= popSize`. Next emits `AutoDesignParams`.
2. **Step 2 – allowed sections** (`ui/sections_page.py`). In a worker thread: connect to SAP2000 (attach to a running instance, else start one) → open `sapPath` → read frame section names (`PropFrame.GetNameList`). Table columns: Section, Is Allowed for Column, Is Allowed for Beam, Is Allowed for Horizontal Brace, Is Allowed for Vertical Brace (`SectionPermission` fields `allowedForColumn`, `allowedForBeam`, `allowedForHorizontalBrace`, `allowedForVerticalBrace`; the role list `ROLES` in `sections_page.py` and `HEADERS` in `sections_excel.py` must keep the same order). Each cell toggles No/Yes on click or Space/Enter; default No. Loading shows a progress bar; failure shows the message and a Retry button. Next requires at least one Yes and emits `list[SectionPermission]`. A Back button returns to step 1. Tools for editing long section lists (all of them work on the table data, never on SAP):
    * **Name filter** above the table. Plain text matches anywhere in the name; text with `*` / `?` must match the whole name (`IPE*` starts with IPE, `*300` ends with 300, `?` is one character); a comma or `;` separates several patterns (`HEA*, IPE*`). Case is ignored. The filter only hides rows.
    * **Apply to the shown sections**: choose a role (Column / Beam / Horizontal Brace / Vertical Brace) and press `Set Yes (N)` or `Set No (N)`; only the N rows that pass the filter change.
    * **Undo / Redo** (buttons, Ctrl+Z, Ctrl+Y / Ctrl+Shift+Z). Every click, every bulk action and every Excel import is one step. The history is cleared when the sections are reloaded from SAP. While the filter box has focus, Ctrl+Z undoes its text instead.
    * **Live counters** under the table: `Allowed: Column n | Beam n | Horizontal Brace n | Vertical Brace n` and `Showing x of y`. Counters, Export and Next always use all rows, shown or hidden. There is deliberately no warning when a role has zero sections, because a user may legitimately not use a role.
    * **Excel export / import** (`Export…` / `Import…` buttons, logic in `services/sections_excel.py`, needs `openpyxl`, imported lazily). Export writes one sheet with the header `Section`, `Is Allowed for Column`, `Is Allowed for Beam`, `Is Allowed for Horizontal Brace`, `Is Allowed for Vertical Brace` and a Yes/No drop-down in the cells. Import matches rows by section name (all five header names must exist, so an old three-role file is rejected with a message naming the missing columns; Yes/No also accepts y/n/true/false/1/0/x, an empty cell means No). If any cell has another value, nothing is applied and the first bad cells are reported. Sections in the file but not in the model are ignored, sections in the model but not in the file stay unchanged, and both counts are shown. Import ignores the filter and is one undo step.
3. **Wizard state** (`ui/wizard.py`): `params` (AutoDesignParams), `sections` (the list from step 2, the variable the user asked for), `sap` (the live `SapClient`). Going Back and Next again with the **same** `sapPath` reuses the loaded page (no reconnect, choices kept, undo history kept); a **different** `sapPath` rebuilds step 2 from scratch.
4. **Next steps of the wizard:** not built yet (`_on_sections_accepted` only logs; see its TODO).

### SAP2000 connection decisions (`core/sap_client.py`)

* Uses `pythonnet` with the .NET Framework runtime (`pythonnet.load("netfx")`) and loads `SAP2000v1.dll` directly, like `NET.addAssembly` in the MATLAB code.
* **Only SAP2000 v23 is supported** (company rule: everyone has it). The DLL is bundled in `src/core/vendor/sap2000_v23/SAP2000v1.dll`, so the install path and signature differences between versions do not matter. After connecting, the running SAP version is checked and anything other than v23 gives a clear error. SAP2000 itself must still be installed.
* The DLL is small, so it ships inside the app update package; running it from `%LocalAppData%` is not a problem (confirmed by the user). `build.py`, when written, must copy all files under `src/`, not only `.py`, and `.gitignore` must not exclude this `.dll`.
* `openSapModel.m` also deletes non-`.sdb` files in the model folder; this was **deliberately not ported**.
* The SAP2000 imports are lazy, so the app starts even if `pythonnet` is missing.

### Unverified (never run against a real SAP2000)

* `pythonnet` has to be added to `runtime/requirements.txt` (and `pyproject.toml`). `openpyxl` is already in `pyproject.toml`; check that it is also in `runtime/requirements.txt` (it is listed twice there now; remove the duplicate).
* `api.cHelper(api.Helper())` (the equivalent of `NET.explicitCast`) in pythonnet.
* Python binding of `ref`/`out` parameters: `PropFrame.GetNameList(0, None)` is assumed to return `(ret, count, names)`; `SapModel.GetVersion("", 0.0)` is assumed to return `(ret, version, number)`. If `GetVersion` fails, the version check only logs a warning.
* `helper.GetObject` behaviour when SAP is not running (the code handles both `None` and an exception).
* The UI of both steps was written without being seen on a real display. Threading: the SAP calls run in a `QThread`; check that SAP's COM/.NET objects work from it.
* The step 2 editing tools: the filter patterns and the Excel export/import round trip (including a bad Yes/No cell and a missing header) were tested with plain Python, but the widgets themselves (layout with the two new tool rows at the minimum window height, Ctrl+Z / Ctrl+Y shortcuts, file dialogs) have not been run. Open the page with a model that has hundreds of sections and check them.

## SLD to SAP (current state)

Converts the piping SLD (CSV files written by `SLD2SAP.lsp` from the AutoCAD layer `TAGGED_LOADS`) into two SAP2000 import tables: joints (point loads, circles) and distributed frame loads (rectangles). It is a port of the user's working MATLAB tool `SLD2SAP.m` (v1.4). The full algorithm, file formats, token table, error codes and the verified differences from MATLAB are in `docs/sld_to_sap_algorithm.md`; this section only describes the code.

* **Inputs** (`ui/page.py`): `z0` (m), tolerance (mm), end tolerance (mm, default 5), EQ.Z coefficient, friction coefficient (default 0.15); a list of CSV files or folders; the SAP2000 Excel export (sheets `Connectivity - Frame` and `Joint Coordinates`); an output folder (default: next to the Excel file). `LISP` is not changed.
* **All problems are shown together, automatically.** Stage 1 (`check_structure`): every error that depends only on the CSV files (S codes) over all files, re-run (debounced 350 ms) whenever a file is added or removed. Stage 2 (`convert`): once the Excel file is given, the matching errors (M codes) are added and re-run when the Excel file or any parameter changes. Nothing stops at the first error.
* **All or nothing:** `Convert` is enabled only when there is no error, and `write_outputs` refuses to write when the result has errors. Warnings (W01: two points with the same coordinates) do not block.
* **Issue table:** sorted by file, then errors before warnings, then `Index`. Double-clicking a row copies its CAD coordinates (mm) to find the object in AutoCAD.
* **Outputs:** `SAP2000 Joint Coordinates.xlsx` (sheet `Joint Coordinates`) and `SAP2000 Distributed Loads.xlsx` (sheet `Frame Loads - Distributed`). Headers are fixed SAP strings and must not be changed. `relDist` / `absDist` are not rounded (bit-for-bit comparison with MATLAB is the goal). Frame names are written as numbers when they are digits only, else as text.
* **Behaviours that differ from MATLAB on purpose** (all confirmed in the guide): the "load inside the frame" test is correct for reversed frames (`lo = min(pI,pJ)`, `hi = max(pI,pJ)`), `endTolerance` is applied at the beam ends and the distances are clamped to `[0, Length]`, point names must be unique over all files (S10), `LS`/`LT` duplicates are checked in plans, a non-numeric value after `=` (S14) and a text that is only a number (S15) are errors, and halves are rounded away from zero (`round_mm`).
* **Not implemented:** warning W02 (file name does not match the origin row), plan rectangles that are not axis-aligned (never produced by the current LISP), graphical preview (declined), direct import into SAP2000 through OAPI (later phase).

### Unverified (SLD to SAP)

* The UI was never run on a real display. Only the services were run, through the tests.
* The tests use the worked examples of the guide (section 10) and synthetic files. The comparison with the real successful MATLAB run (second sample set, guide section 9.14: 5 joints and 116 load records, bit-for-bit) has **not** been done in this code: the sample files and the two MATLAB outputs must be supplied.
* The guide lists cases missing from the samples: reversed frame, `HT` / `LT`, point load in a plan with a height value, point with an extra value, `FV=`. A small complete sample set with MATLAB output is still needed (guide section 14).
* `pytest` could not be installed where the tests were written; they were run with a minimal stand-in. Run them once with real pytest on the project runtime.

## Rules

* The shell (`src/ui/`) never contains plugin-specific logic; a plugin never controls the shell. Plugin UI lives in `plugins/<name>/ui/`, business logic in `plugins/<name>/services/`. Code shared by several plugins (like the SAP connection) lives in `src/core/`.
* Do not remove or rename `main()` and `ping_app()` without updating the launcher contract (`ping_app()` is the post-update self-check).
* Create planned files (e.g. further Auto Design `services/` modules) only when they are actually implemented. Every package folder needs an `__init__.py`, otherwise `pyproject.toml` (`packages.find include = ["src*"]`) skips it.
* Always use the project runtime; `python` / `py` may not exist globally.
* Tests of a plugin live in `tests/<plugin name>/`.
* After changing any code, state which file changed and its exact folder location (project instruction).

## Development

* Windows, VSCode, project Python: `D:\Python Library\StructureLab\runtime\python\python.exe`.
* Run (or F5 with the "Structure Lab" launch config, module `src`): `.\runtime\python\python.exe -m src`
* Install deps: `.\runtime\python\python.exe -m pip install -r .\runtime\requirements.txt`
* Tests / lint: `.\runtime\python\python.exe -m pytest` (one plugin: `.\runtime\python\python.exe -m pytest tests\sld_to_sap`) and `.\runtime\python\python.exe -m ruff check .`

## Status

Done: project structure, embedded runtime, VSCode debugging, dark-themed shell (title bar, sidebar, Home), plugin registry, page switching, Auto Design step 1 (settings form) and step 2 (sections table with filter, bulk Yes/No, undo/redo, counters and Excel import/export), SAP2000 connection layer (untested), SLD to SAP services (complete algorithm, tested on the guide's examples) and its single-page UI with automatic, collected error checking (UI not yet run on a display).

Known technical issues to fix next:

* `TitleBar`: `self.window` shadows `QWidget.window()`; dragging should use `startSystemMove()`; no edge resizing.
* Dead `about_name` label in `navigation.py`.
* `plugins/` uses absolute `src.` imports while `ui/` uses relative ones; unify (launcher runs the app from `app\<version>\`). The new Auto Design files, `core/sap_client.py` and the SLD to SAP plugin follow the absolute style.
* Dependencies are listed in both `pyproject.toml` and `runtime/requirements.txt`; dev tools (pytest, ruff, mypy, scikit-learn) must not ship in the release runtime.
* Text glyph icons (⚙ ◈ ⇄ ◇) are inconsistent with the PNG icons; `QApplication([])` should receive `sys.argv`. `logging_setup.py` exists but `setup_logging()` is not called from `main()` yet, so the `logger.info/exception` calls in the new code go nowhere.
* Step 2 does not stop its worker thread if the app closes while loading.
* Step 2 has no automated test yet. `compile_name_filter` (in `sections_page.py`) and `services/sections_excel.py` are pure logic and easy to cover in `tests/auto_design/`.
* SLD to SAP runs its checks synchronously on the UI thread; this is fine for the expected file sizes, but move it to a worker thread if a large model feels slow.

## Next session

1. Put `SAP2000v1.dll` (from the v23 install) in `src/core/vendor/sap2000_v23/`, add `pythonnet` to the runtime requirements, and run Auto Design step 2 against a real SAP2000. Send any traceback.
2. Ask the user to extract from the v23 DLL (MATLAB `methodsview`): `cPropFrame.GetNameList`, `cFile.OpenFile`, `cSapModel.GetVersion`, `cHelper.GetObject`; fix `sap_client.py` to match.
3. SLD to SAP: run the page on the real display and send any problem; supply the second sample set (CSV files, Connectivity, the two MATLAB outputs) so a test compares the 5 joints and 116 load records bit-for-bit; then a small complete sample set for the missing cases (guide section 14).
4. Build the next Auto Design wizard step after the sections table (the user will describe it). Eventually: GA logic in `plugins/auto_design/services/`, evaluation behind `evaluate(x)`, storing every evaluation from day one (see the plan doc).
5. Write `tools/build.py` (zip `src/` including non-`.py` files, runtime zip, `latest.json` last).
6. Ideas the user declined for Auto Design step 2, do not build unless asked again: smart grouping by section family or dimensions, remembering the last choice per section name, saved templates, a warning when a role has no section.

## Change log
* [1.1.5] - (2026-10-21):
    - version no. is mentioning to SLD2SAP.m last ver. as v1.4
    - SLD to SAP plugin: `SldToSapPlugin` replaces the placeholder in `plugins/registry.py`; services `issues.py`, `geometry.py`, `sld_reader.py`, `connectivity.py`, `matcher.py`, `load_rules.py`, `pipeline.py`, `exporter.py` and `params.py` written from `docs/sld_to_sap_algorithm.md`
    - SLD to SAP page (`ui/page.py`): parameters, CSV list, Excel model, output folder; stage 1 (CSV only) and stage 2 (with the Excel model) checks re-run automatically and list all errors together, sorted by file; `Convert` enabled only without errors; double-click on an issue copies its CAD coordinates
    - SLD to SAP tests in `tests/sld_to_sap/test_sld_to_sap.py`

* [1.0.0] - (2026-10-20): 
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
    - Auto Design UI enhancements.
    - Auto Design editing tools (`ui/sections_page.py`): name filter with `*` / `?`, `Set Yes / Set No` for the shown rows per role, Undo / Redo, live counters
    - Auto Design excel import/export of the sections table (new `services/sections_excel.py`, `services/__init__.py`); `openpyxl` added to `pyproject.toml`
    - brace split in two: `SectionPermission.allowedForBrace` replaced by `allowedForHorizontalBrace` and `allowedForVerticalBrace` (`params.py`); step 2 table, bulk apply, counters (`ui/sections_page.py`), Excel (`services/sections_excel.py`) and the log line in `ui/wizard.py` updated; role columns now size to their titles