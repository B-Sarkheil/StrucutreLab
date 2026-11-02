# Structure Lab

Integrated engineering desktop software for Windows (Python + PySide6) for about 30 users. It gradually replaces scattered MATLAB and Excel-VBA tools. Each tool is a plugin.

First real tool: **Auto Design**, automatic structural section optimization (Genetic Algorithm + SAP2000 OAPI). Development resumed on 2026-10-27: it is **enabled** (`AUTO_DESIGN_ENABLED = True` in `plugins/registry.py`). Its wizard has three input pages and a live run page; the run executes GA steps 5 to 9 (the generation loop is written; `classify_frame` and `fitness_calculator` are still missing, and step 10 is still to be described; see "Auto Design"). Second tool: **SLD to SAP**, loading the SAP2000 model from piping SLD files exported from AutoCAD.

Design context lives in these docs in the project knowledge:

* `claude/engineering-platform-decisions.md`: bootstrap / runtime / app layers, auto-update from the server, IT constraints.
* `docs/contract.md`: the frozen contract between the launcher and the app (layout on the user machine, server share, update rules, the update question).
* `claude/project-plan-structural-optimization.md`: Auto Design plan (Phase 1 GA, Phase 2 ML surrogate lab, Phase 3 general model). Written in Persian. Key rules: the GA only calls `evaluate(x)`; save every evaluation from day one (training data for the ML phase); the final answer is always confirmed with the real engine; ML never becomes a dependency of the GA.
* `docs/sld_to_sap_algorithm.md`: the SLD to SAP algorithm guide. The code is the reference; if they disagree, the guide must be fixed (or, after a decision, the code).
* A complete document of the implemented Auto Design algorithm will be written at the end of the work (planned, `docs/` folder; not created yet). Until then the user describes the GA to Claude step by step, and this README only keeps what is needed to continue the work.

### MATLAB references (project knowledge)

The user's tested MATLAB code is the reference for SAP2000 API calls; method signatures in it can be trusted (the user can extract exact signatures from the DLL on request). It belongs to the **Auto CPS** tool (planned, not built in Python), not to Auto Design, but the API patterns apply:

* `connectToSAP.m`, `openSapModel.m` (ported in `core/sap_client.py`).
* `runAll.m`, `modelingOneLine.m`, `designOneLine.m`: open model, change sections, `File.Save(path)`, `Analyze.RunAnalysis()`, then read results.
* `modifyProfilesType1.m`: `SetModelIsLocked(false)` then `FrameObj.SetSection(name, section)`.
* `modifySapModelType1.m`: geometry/loads/mass source/seismic coefficients through the API (`EditPoint`, `PointObj`, `FrameObj.SetLoadDistributed`, `SourceMass`, `AutoSeismic`, `StaticLinear` load cases).
* `getDesignResultsType1.m` (the function inside is named `getDesignResultsType2`): `DesignSteel.StartDesign()`, `DesignSteel.GetSummaryResults`, `Setup.SetComboSelectedForOutput`, `AnalysisResults.JointDispl`, `JointReact`. Useful when `fitness_calculator` is written.
* `SLD2SAP.m` (v1.4) with `SLD2SAP.lsp`: reference of SLD to SAP.

## Layout

```text
StructureLab/
├── bootstrap/          launcher.py (1.1.0), installer.iss (kept stable; contract in docs/contract.md)
├── runtime/            embedded Python 3.12.10 x64 (runtime/python/, libraries in Lib/site-packages) + requirements.txt
├── src/
│   ├── __main__.py     entry point: main() (calls setup_logging first), ask_update() (update window, called by the launcher), ping_app()
│   ├── version.py      THE single place to change the version (now 1.2.1); pyproject.toml will show the same value automatically
│   ├── release_notes.json   hand-written release notes of every version (shown after an update and in the update window)
│   ├── core/           app-wide services
│   │   ├── paths.py, config.py, logging_setup.py, storage.py   (small helpers / stubs)
│   │   ├── release_notes.py    reads release_notes.json, decides which notes the user has not seen (no Qt)
│   │   ├── sap_client.py       SAP2000 connection (pythonnet), shared by all SAP plugins
│   │   └── vendor/sap2000_v23/SAP2000v1.dll    bundled OAPI assembly (user must place it)
│   ├── ui/             shell only: main_window, navigation, home_page, about_page, widgets, theme, loading_overlay, assets/icons/
│   │   ├── sheet_dialog.py          base of the small modal windows (drawing-sheet look, framed version cards with colored tags, busy bar)
│   │   ├── release_notes_dialog.py  "What's new" window after an update (Got it button)
│   │   └── update_dialogs.py        "Update available" window shown by the launcher (Update now / Later / Exit)
│   └── plugins/        base.py, registry.py, placeholder.py, <plugin>/
│       │
│       ├── auto_design/
│       │   ├── plugin.py       registers the plugin; create_widget() returns AutoDesignWizard
│       │   ├── params.py       AutoDesignParams (GA settings, step 3), SectionPermission (step 2 table + materialType from GA step 5)
│       │   ├── services/       pure logic, no Qt
│       │   │   ├── sections_excel.py     Excel import / export of the sections table
│       │   │   ├── sap_tables.py         pick_field(): case-insensitive field of a SAP database-table row
│       │   │   ├── run_monitor.py        RunMonitor (status / progress / generation reports, cooperative cancel), RunCancelled, GenerationStats
│       │   │   ├── ga_run.py             GAContext, prepare_database_folder, step5..step9 functions, _make_member, run_ga
│       │   │   ├── section_materials.py  GA step 5: Material Type of every section
│       │   │   ├── frame_assignments.py  GA step 6: section assigned to every frame
│       │   │   ├── model_geometry.py     GA step 7: joint coordinates and frame connectivity
│       │   │   ├── population.py         GA step 8: Individual, frame roles, allowed sections per frame, random genes
│       │   │   ├── genetic_operators.py  GA step 9: tournament_parents, random_cut_points, three_point_crossover, select_survivors (pure, no SAP)
│       │   │   ├── fitness.py            fitness_calculator (STUB, returns None), fitness_value (temporary: a number, larger = better)
│       │   │   └── database_folder.py    check / describe / clear the database folder, generation_folder, copy_member_model
│       │   └── ui/
│       │       ├── wizard.py             QStackedWidget: moves between the pages, keeps the collected data, owns the run worker thread (_RunWorker)
│       │       ├── page.py               step 1: SAP2000 reference file (drop zone)
│       │       ├── sections_page.py      step 2: allowed-sections table
│       │       ├── ga_settings_page.py   step 3: GA settings form + Simulate Evolution button
│       │       ├── run_page.py           live view of the run (progress bar, tiles, chart, status log); no GA logic
│       │       ├── fields.py             form widgets shared by the pages (Field, FancyCheckBox, parse_int, parse_float, FORM_STYLE)
│       │       └── icons.py              vector icons drawn in code (evolution_run_icon)
│       └── sld_to_sap/
│           ├── plugin.py       SldToSapPlugin; create_widget() returns SldToSapPage (lazy import)
│           ├── params.py       SldParams (z0, tolerance_mm, end_tolerance_mm, eqz_coef, friction_coef)
│           ├── assets/         SLD2SAP.lsp and "Rules of SLD2SAP.pdf" (offered by the page's download buttons)
│           ├── templates/      "SAP2000 Joint Coordinates.xlsx" and "SAP2000 Distributed Loads.xlsx" (output templates, copied from the MATLAB tool)
│           ├── services/       pure logic, no Qt (one module per step of the algorithm guide)
│           │   ├── issues.py       Issue (code, message, file, Index, CAD coordinates, severity)
│           │   ├── geometry.py     round_mm (MATLAB-style rounding), CAD to model conversion
│           │   ├── sld_reader.py   CSV reading, number/word rule, origin row detection
│           │   ├── connectivity.py frames and joints from the SAP2000 Excel export (cached per file)
│           │   ├── matcher.py      frame under a load rectangle (elevation and plan)
│           │   ├── load_rules.py   token table (V/FV/HS/LS/HT/LT) to load records
│           │   ├── pipeline.py     convert(), check_structure(), ConversionResult
│           │   └── exporter.py     the two SAP2000 import tables (.xlsx), written into the templates
│           └── ui/
│               ├── page.py         single page: inputs, automatic checks, issue table, Convert
│               └── icons.py        small vector icons drawn in code (document, folder, trash, convert, message)
│
├── tools/              build.py, publish.py, release_config.json (server_dir, channel, min_bootstrap_version, optional icon)
├── dist/               generated by build.py (never edit): publish/ (files for the server), stage/ (installer input), StructureLab-Setup.exe
├── docs/
├── tests/
│    ├── auto_design/
│    │   ├── test_genetic_operators.py   tournament, cut points, three-point crossover, select_survivors (no SAP, no Qt)
│    │   ├── test_database_folder.py     copy_member_model (temp folder)
│    │   └── preview_run_page.py         progree page preview
│    ├── bootstrap/
│    │   └── test_launcher.py        update flow of the launcher with a fake server (no Qt, no Windows needed)
│    ├── core/
│    │   └── test_release_notes.py
│    ├── sld_to_sap/
│    │   └── test_sld_to_sap.py
│    └── test_plugins.py
│
├── pyproject.toml
├── .gitignore
├── get-pip.py
└── README.md

```

Every package folder needs an `__init__.py` (the Auto Design `services/` and `ui/` folders have one).

## How the app works

* `__main__.main()`: `setup_logging()` → QApplication → `apply_theme` → `register_builtin_plugins()` → `MainWindow` → 300 ms later `MainWindow.show_release_notes_if_needed()` → `app.exec()`.
* **Plugin contract** (`plugins/base.py`): `name` (unique key), `title`, `icon`, `description`, `available` (False = planned, not built), and `create_widget() -> QWidget`.
* **Registry** (`plugins/registry.py`): explicit and simple. `register_builtin_plugins()` lists all plugins in navigation order (Auto Design, SLD to SAP, PDMS to SAP, Auto CPS); `load_plugins()` returns them. No auto-discovery yet. **Release switch:** `AUTO_DESIGN_ENABLED` (currently `True`): the real `AutoDesignPlugin` is registered. When set to `False`, Auto Design is registered as a `PlaceholderPlugin` with the same name, title, icon and description, so it appears in the sidebar and on Home as a planned tool and opens the "Under development" page. The switch stays in the code to hide the tool again if needed (for example during a long development pause).
* **Shell** (`ui/`): `MainWindow` reads the registry and passes the plugins to `Navigation` (sidebar) and `HomePage`. Clicking a sidebar item or a card calls `MainWindow.show_page(key)`. Home is built at startup; each plugin page is created lazily on first open and kept in a `FadeStackedWidget` (a `QStackedWidget` that fades the new page in). If `create_widget()` fails, the error is logged and the current page stays. The About page is a shell page (not a plugin) opened from the About card at the bottom of the sidebar.
* **Home page caveat:** `home_page.py` has a fixed list `plugin_order = ["auto_design", "sld_to_sap", "pdms_to_sap", "auto_cps"]`; only plugins named there get a card or row. A new plugin must be added to that list until it is replaced by the registry order (see known issues).
* **Not implemented yet (shown as planned, open the "Under development" page):** Auto CPS and PDMS to SAP.
* **Visual language** ("structural drawing sheet"): all colors are tokens at the top of `ui/theme.py` (blueprint-ink surfaces, drafting-cyan linework, amber as the single signal color for active/hover/focus, plus `BLUE`, `DANGER`, `PAPER`, `STEEL`, `STEEL_DIM`, `RULE`, `RULE_HI`, `INK*`). Titles use Bahnschrift, body uses Segoe UI. Most widgets are styled by `objectName` in the stylesheet; cards, the hero banner and the sidebar marker are painted in code (`ui/widgets.py`, `ui/home_page.py`, `ui/navigation.py`) and read the same tokens. Available tools get large cards, planned tools get dashed rows. The hero banner fades its logo in once over 5 s (`HeroBanner.FADE_MS`), which is the only unprompted motion in the app; the About page logo emblem spins while visible. `ui/loading_overlay.py` is the shared loading overlay (delay 200 ms, minimum visible 450 ms, blocks input to the page below). New pages of a plugin follow the same look (see `run_page.py` for a page that paints its own widgets with these tokens).
* **Small modal windows** (`ui/sheet_dialog.py`): "What's new" and "Update available" are frameless dialogs drawn on the About page's `SheetCard` (same blueprint grid and corner marks). `SheetDialog` is the base (heading, divider, buttons, scrollable list of framed version cards that grows up to 300 px, drag by any free area, indeterminate `BusyBar` drawn in code); `ReleaseNotesDialog` and `UpdatePromptDialog` only fill it.

## Release notes

* **Source:** `src/release_notes.json`, written by hand for every release: `{"releases": [{"version", "date", "title", "items": [{"tag": "new|improved|fixed", "text"}]}]}`. An item may also be a plain string (tag `improved`). Entries without a version or without items are ignored. Write what a *user* needs to know, not the code changes (those go to the README change log). A version without an entry has no window.
* **After an update** (`core/release_notes.py`, `MainWindow.show_release_notes_if_needed()`): the last version whose notes the user has seen is stored in `<data dir>\user_state.json` (`last_seen_version`; not `state.json`, which belongs to the launcher). If `__version__` is higher, the notes of every version in between (newest first) open in `ReleaseNotesDialog`; **Got it** closes it and the version is stored. A fresh install shows nothing (the current version is just stored). The stored version never goes backwards (rollback safe). A broken notes file or any error shows nothing and never blocks the app.
* **Not in the update window:** the notes are shown once, after the update, in "What's new"; the update window only shows the two versions and the question. `build.py` still copies the newest 10 entries into `latest.json` (`release_notes`) and the launcher passes them to `ask_update()`, which ignores them for now (kept for a possible later use).
* **Look:** each version is a framed card titled with its version and date; the item tags are NEW (green), IMPROVED (blue) and FIXED (warm); colors are defined in `ui/sheet_dialog.py` (`TAG_STYLES`).

## Release and update system (done, first release 1.1.5 installed and started on the user's PC; update question added in launcher 1.1.0)

Three layers (details and frozen rules in `docs/contract.md`). Installed copy: `%LocalAppData%\Structure Lab\` (with a space; `core/paths.py` has `APP_NAME = "Structure Lab"` and uses `STRUCTURELAB_ROOT` when the launcher sets it).

* **Installer** (`bootstrap/installer.iss`, Inno Setup 6 or 7): per-user, no admin rights, silent mode `/VERYSILENT`, no entry in Programs and Features (`Uninstallable=no`). Copies bootstrap (small Python + `launcher.py` + `initial.json`), the first runtime and the first app version, plus `settings.json` (server path; never overwritten by a re-install). Start Menu shortcut (and optional desktop) runs `bootstrap\python\pythonw.exe bootstrap\launcher.py`, with `AppUserModelID` `StructureLab.App` and the icon `app.ico`. The Setup.exe is given to users once; it is **not** part of the server folder.
* **Launcher** (`bootstrap/launcher.py`, `BOOTSTRAP_VERSION = "1.1.0"`, standard library only): on every start reads `latest.json` from the server share with a 5 s timeout (unreachable server: skip, start the installed version). If the server app version is higher (and not rejected before) it **asks the user**: it starts the installed app with `ask_update()` (`python.exe`, no console window), which shows the "Update available" window (installed version in the warm color → new version in cyan, the question, **Update now** / **Later**; for a mandatory update **Update now** / **Exit** and Esc is ignored) and prints `UPDATE`, `LATER` or `EXIT` on stdout. `LATER` starts the installed version (asked again next start); `EXIT` ends without starting; `UPDATE` switches the same window to "Updating…" while the launcher downloads the needed zips to `tmp\`, checks sha256, extracts beside the target, renames atomically, runs the self-check (`ping_app()` with the new runtime and the new app), switches `state.json` and then terminates the window. A failed self-check deletes the new folders and records the version in `rejected`; if any update step fails the installed version starts (even when mandatory). If the window cannot run (an old app without `ask_update`, a crash, no display) a plain Windows message box asks instead (Yes/No; mandatory: information, then update). No question is asked when the installed version is missing or damaged (repaired directly) or with `--update-only` / `--yes` (IT scripts). Keeps only the current and the previous app/runtime. A lock file prevents two instances updating at once. The app runs as a child process with the runtime's `pythonw.exe`; if it exits within 6 s a message box is shown. The update never restarts a running app: the new version starts at the next launch.
* **Logs** are local only: `%LocalAppData%\Structure Lab\logs\` (`launcher.log` for updates, `app.log` for the app, `app_stderr.log` and `update_prompt_stderr.log` for startup errors). `core/logging_setup.append_server_log` is an unused stub; `core/config.Settings` only has `server_dir` and `channel` (the contract's `network_timeout_sec` is read by the launcher, not by the app).
* **Server share:** `\\be-sarkheil\Share\Structure Lab` (read access for users). Holds `latest.json`, `app-<version>.zip`, `runtime-<id>.zip`. Old zips stay there (publish.py never deletes); only the ones in `latest.json` are needed.
* **`tools/build.py`:** reads the version from `src/version.py` (stops if `pyproject.toml` shows another one), zips all files under `src/`, builds the runtime zip from `runtime/python` only when the runtime id changes (id = hash of `runtime/requirements.txt` + Python DLL name; dev packages, `Scripts/` and `__pycache__` are left out; the dev `python312._pth` with `..\..` is replaced by a clean one), writes `latest.json` last. `latest.json` also carries `release_notes` (newest 10 entries of `src/release_notes.json`; a warning is printed when there is no entry for the version being built) and, with `--mandatory`, `"mandatory": true`. With `--installer` it also builds `dist\stage` and `dist\StructureLab-Setup.exe` (ISCC is found in the usual Inno Setup 6/7 folders or with `--iscc`).
* **`tools/publish.py`:** copies the zips from `dist\publish` to the server (skips files that are already there), `latest.json` last.
* **`min_bootstrap_version`** in `release_config.json` is the version of the *launcher* (`BOOTSTRAP_VERSION`), not of the app. It is now `1.1.0`. Change it only when `launcher.py` changes and a new Setup is required (users with an older launcher are then told once to ask IT).

How to release a new version (e.g. 1.2.1), no new Setup needed:

1. Change the code and test. 2. Set the new version in `src/version.py` (and `pyproject.toml` unless it reads the version from `version.py`); set `__release_date__` too. 3. Add the entry of the new version to `src/release_notes.json`. 4. `.\runtime\python\python.exe tools\build.py` (add `--mandatory` when users must not postpone it) 5. `.\runtime\python\python.exe tools\publish.py`. Users are asked at their next launch. A rejected version is not retried: publish a higher version to fix it. Going back means re-publishing the old code with a higher number. A mandatory flag applies to the newest version on the server only: a user who is several versions behind is forced only if the newest one is mandatory.

First release / new Setup: `.\runtime\python\python.exe tools\build.py --installer [--iscc "<path>\ISCC.exe"]`, then `publish.py`, then hand `dist\StructureLab-Setup.exe` to the users. If you add a library, install it into `runtime\python` first (`pip install -r runtime\requirements.txt`); the runtime id changes and users download the new runtime once. **Launcher 1.1.0 (the update question) reaches a PC only through a new Setup**; until then that PC still updates silently (launcher 1.0.0 stops updating once `min_bootstrap_version` is 1.1.0 and tells the user to ask IT).

## Auto Design (current state; enabled, see the release switch)

A wizard inside the plugin (`ui/wizard.py`, a `QStackedWidget`); the shell knows nothing about its steps. Field names are camelCase on purpose (`popSize`, `frameSections`, `materialType` ...), the same name from the form down to the GA code.

### The steps of the algorithm and what exists

The user described the algorithm to Claude a few steps at a time. The "20 steps" he mentioned (`TOTAL_STEPS = 20` in `ga_run.py`) **count the sub-steps too** (clarified on 2026-11-02): steps 1 to 9 with all their sub-steps are the whole described algorithm, and they are written. A separate **step 10** (typing / grouping of the selected member) still comes; the user will say what to do at the very end. Do not invent steps that the user has not described. In the code, `step5_...` to `step9_...` are the top-level steps; the sub-steps (for example 9.1.3) are numbered in the comments.

| Step | What | Where |
|---|---|---|
| 1 | SAP2000 reference file | `ui/page.py` |
| 2 | Allowed sections table | `ui/sections_page.py` |
| 3 | GA settings | `ui/ga_settings_page.py` |
| 4 | "Simulate Evolution" button (confirms the database folder, starts the run) | `ga_settings_page.py` + `wizard.py` |
| 5 | Material Type of every section → `ctx.sections[i].materialType` | `services/section_materials.py`, `step5_material_types` |
| 6 | Section assigned to every frame → `ctx.frameSections` (frame → section) | `services/frame_assignments.py`, `step6_frame_sections` |
| 7 | Joint coordinates and frame connectivity → `ctx.jointCoordinates`, `ctx.frameConnectivity` | `services/model_geometry.py`, `step7_geometry` |
| 8 | Initial population of `popSize` (made even) members, with fitness | `services/population.py`, `ga_run.step8_initial_population` |
| 9 | Loop of `genSize` generations: 9.1 children by tournament + three-point crossover, 9.2 the best N of the 2N members go to the next generation | `services/genetic_operators.py`, `ga_run.step9_generations` |
| 10 | Typing of the selected (best) member: **not described yet** (the user will say at the very end) | |

### Wizard pages (steps 1 to 3)

1. **Step 1 – SAP2000 reference file** (`ui/page.py`, `AutoDesignPage`). A big drop area (`DropZone`): drop a `.sdb` file or click to browse. Only `.sdb` is accepted. The SAP2000 logo is read from `ui/assets/icons/sap.png` (`sap.ico` and `sao.ico` are accepted too); a plain "SAP" lettering is drawn when none exists. Next checks that the file still exists and emits the path (`str`). The path is NOT part of `AutoDesignParams`; the wizard keeps it as `sap_path`.
2. **Step 2 – allowed sections** (`ui/sections_page.py`). In a worker thread (`_SectionsLoader`): connect to SAP2000 (attach to a running instance, else start one) → open the file → read frame section names (`PropFrame.GetNameList`). Table columns: Section, Is Allowed for Column, Is Allowed for Beam, Is Allowed for Horizontal Brace, Is Allowed for Vertical Brace (`SectionPermission` fields `allowedForColumn`, `allowedForBeam`, `allowedForHorizontalBrace`, `allowedForVerticalBrace`; the role list `ROLES` in `sections_page.py`, `HEADERS` in `sections_excel.py` and `ROLE_FIELDS` in `population.py` must keep the same roles). Each cell toggles No/Yes on click or Space/Enter; default No. Loading shows a progress bar; failure shows the message and a Retry button. Next requires at least one Yes and emits `list[SectionPermission]`. Tools for long section lists (all work on the table data, never on SAP):
    * **Name filter**: plain text matches anywhere in the name; text with `*` / `?` must match the whole name (`IPE*`, `*300`); a comma or `;` separates patterns. Case ignored. It only hides rows.
    * **Apply to the shown sections**: choose a role and press `Set Yes (N)` / `Set No (N)`; only the N rows that pass the filter change.
    * **Undo / Redo** (buttons, Ctrl+Z, Ctrl+Y / Ctrl+Shift+Z). Every click, bulk action and Excel import is one step. History is cleared when the sections are reloaded.
    * **Live counters** under the table (`Allowed: Column n | Beam n | ...`, `Showing x of y`). Counters, Export and Next always use all rows. No warning when a role has zero sections (a user may legitimately not use a role).
    * **Excel export / import** (`services/sections_excel.py`, needs `openpyxl`, imported lazily). Import matches rows by section name; all five header names must exist; Yes/No also accepts y/n/true/false/1/0/x, empty = No; any other value applies nothing and reports the first bad cells; sections not in the model are ignored, sections not in the file stay unchanged. One undo step.
3. **Step 3 – GA settings** (`ui/ga_settings_page.py`, `GASettingsPage`). Fields (defaults in brackets): `popSize` (100), `tournamentSize` (4), `genSize` (10), `mutationPercent` (0; range 0 to 100), `penalizeLevel` (1), `tolerance` (1, in **cm**: tolerance to detect a member as beam or column); the checkbox `updateSeismicLoads` (off) and `modelsFolder` (database folder for the generation models; default `<folder of the reference file>\SAP Models`, with a Browse button; once the user types or browses, a different reference file no longer changes it). Validation on **Simulate Evolution** (or Enter) with inline errors (`ui/fields.py`); extra rule **`2 <= tournamentSize <= popSize`** (two parents are needed; agreed on 2026-11-02, the UI check must be applied in `ga_settings_page.py` together with the placeholder "Integer, 2 or more"; the algorithm also raises its own error as a second guard); the folder text must not be empty or a file. The run button uses `ui/assets/icons/Run-Genetic.png` (falls back to `evolution_run_icon`). The page is created once, so typed values survive Back / Next. It emits `run_requested(AutoDesignParams)`.

`AutoDesignParams` (frozen): `popSize, tournamentSize, genSize, mutationPercent, penalizeLevel, tolerance, updateSeismicLoads, modelsFolder`. Used by the GA: `popSize`, `tournamentSize`, `genSize` (number of iterations of step 9, also the chart range of the run page), `modelsFolder`, `tolerance` (for `classify_frame`, not written yet). **Not used by the GA yet:** `mutationPercent`, `penalizeLevel`, `updateSeismicLoads`.

### Wizard state and the run lifecycle (`ui/wizard.py`)

* State: `sap_path`, `sections`, `params`, `sap` (the live `SapClient`, taken from the sections page), `context` (the last finished run), `_run_context`, `_run_worker`. Going Back and Next with the **same** `sap_path` reuses the loaded step 2 page; a **different** `sap_path` rebuilds it and clears `sections` and `sap`.
* **Simulate Evolution** → `_on_params_accepted` → `_confirm_database_folder`: `check_folder_usable` (refuses a drive root, the user's home folder, a file, or a folder that contains the reference file) and, when the folder is not empty, a Yes/No warning (default No) that **everything inside will be permanently deleted** → `_start_run`.
* `_start_run` creates `GAContext(sap, params, sections, sapPath)` and a `_RunWorker` (a `QThread`), connects its signals (`status`, `progress`, `generation`, `succeeded`, `failed`, `cancelled`) to the run page and shows `RunPage`.
* The worker calls `run_ga(ctx)`. `RunCancelled` → `cancelled`; any other exception → `failed(message)`; else `succeeded(ctx)`: the wizard keeps `context` and `sections` (now with `materialType`).
* **Cancel** is cooperative (`services/run_monitor.py`): `RunMonitor.cancel()` sets a flag; `monitor.status(...)` is a checkpoint that raises `RunCancelled` (step 9.2 also calls `raise_if_cancelled()` between the copies); a SAP2000 call already running cannot be interrupted. The run page confirms Cancel with a dialog and allows Back only after the run stopped.
* **Progress** is a temporary estimate: finished steps out of the steps from `FIRST_RUN_STEP` to `TOTAL_STEPS` (16), reported by `run_ga` after each step; `prepare_database_folder` is not counted. It does not match the real work any more (the 5 built steps give 5/16 = 31 % when step 9, the longest, finishes; the "20 steps" count sub-steps, see above), so **it must be replaced** (for example by the finished members out of all members of the whole run). The run page sets 100 % on `FINISHED`.
* **Run page** (`ui/run_page.py`, pure display, no SAP and no GA logic): state chip (Running / Cancelling / Cancelled / Finished / Failed), elapsed time, animated progress bar, four tiles (generation, best weight, change in weight, mean DCR), the evolution chart (switch buttons follow the list `METRICS`; to add an objective add a `MetricSpec` and the value in `GenerationStats`), and the status log (one line per `monitor.status`, newest at the bottom). It is fed by `start`, `add_status`, `set_progress`, `add_generation`, `set_state`. **`monitor.generation(GenerationStats)` is never called yet** (the weight and DCR come from `fitness_calculator`, which is not written), so the tiles and chart stay empty. `GenerationStats`: `generation` (0 = initial population), `bestWeight`, `meanWeight`, `meanRatio`, `maxRatio`.

### Run data (`GAContext`, `services/ga_run.py`)

`sap`, `params`, `sections`, `sapPath` (reference file, the original is never modified), `frameSections`, `jointCoordinates` (m), `frameConnectivity` (frame → (jointI, jointJ)), `population: list[Individual]` (the current generation; after the run it is the **final** generation, best member first), `offspring: list[Individual]` (children of the current iteration of step 9), `generation` (number of the generation held in `population`), `rng` (`random.Random()`, **unseeded** for now; add a seed setting if repeatable runs are needed), `monitor`. `Individual` (`population.py`): `name` (e.g. `Gen-1-3`), `path` (its `.sdb`), `genes` (frame → section), `fitness` (whatever `fitness_calculator` returns; `None` for now).

Read-only table access: `SapClient.read_table(key)` returns rows of a SAP database table as dicts (field → text); the table names used are in `section_materials.py` (`Frame Section Properties 01 - General`, `Material Properties 01 - General`), `frame_assignments.py` (`Frame Section Assignments`, field `AnalSect`) and `model_geometry.py` (`Joint Coordinates`, `Connectivity - Frame`). The model is read in N-m-C units (`open_model` sets them).

### Run start: database folder (`prepare_database_folder`, `services/database_folder.py`)

At the start of `run_ga` (before step 5) the run re-checks the folder, **opens the reference model first** (so SAP2000 does not hold the files of a previous run; the reference is outside the folder), then deletes everything inside `modelsFolder` (the folder itself stays). A file that cannot be deleted gives a clear error on the run page. Consequence: a cancelled or failed run leaves partial files until the next run.

### Step 8: initial population (decided with the user)

* Population size is always **even**: `N = popSize + popSize % 2` (members are paired later). The reference model is member 1; the loop `i = 1 .. N-1` builds the others.
* Folder layout (one `Generation-<g>` per generation, member folders inside, each with the SAP file of the same name):

  ```text
  <modelsFolder>\Generation-1\Gen-1-1\Gen-1-1.sdb       copy of the reference file
  <modelsFolder>\Generation-1\Gen-1-2\Gen-1-2.sdb       ... up to Gen-1-N (the parents)
  <modelsFolder>\Generation-1\Gen-1-(N+1) ... Gen-1-2N  children of iteration g = 1 (step 9.1)
  <modelsFolder>\Generation-2\Gen-2-1\Gen-2-1.sdb       the best N of the 2N (step 9.2) ... up to Gen-2-N
  ```
* **Gene = one frame** (not a section group). Genes are independent; the same section may appear in many genes. A random section for a frame is chosen from the sections that have **the same Material Type as the frame's reference section** and are **allowed for the frame's role** (column, beam, horizontalBrace, verticalBrace). The options are computed once before any folder is made (`build_gene_options`); a frame with no Material Type or no allowed section stops the run at the start with all problems listed together.
* Member i is built by `ga_run._make_member` (shared with step 9): open the reference model, `unlock_model`, assign the new section only to frames whose section differs from the reference, `save_model_as` the member's path, then `fitness_calculator(sap, path)`. The reference model is reopened every time (clean start, no old results). The reference member itself is evaluated too, on its **copy** `Gen-1-1.sdb`.
* **`classify_frame` is not written** (raises `NotImplementedError`): the user has not yet described the rule (beam / column / horizontal brace / vertical brace from the joint coordinates and the tolerance in cm). Until then the run stops in step 8 before any member folder is made.
* **`fitness_calculator` (`services/fitness.py`) is a stub** returning `None`: input is a SAP file (the open model), output the optimization objectives; the user will describe it later (weight, DCR from steel design, drift, deflection; see the project plan; the MATLAB `getDesignResultsType1.m` shows the design-results calls).

### Step 9: generation loop (decided with the user, written, not run on SAP2000)

Loop `g = 1 .. genSize`. Pure operators are in `services/genetic_operators.py` (no SAP), the loop is `ga_run.step9_generations`. The DNA of a member is its genes in the order of `ctx.frameSections` (SAP table order).

* **9.1** Loop `m = 1 .. N/2` (`0.5*(popSize + mod(popSize,2))` pairs). Per pair:
    * 9.1.1 / 9.1.2 **Tournament** (`tournament_parents`): `tournamentSize` **different** members are drawn at random from the population; the two with the highest fitness are the parents (ties: the first drawn). `tournamentSize` must be at least 2 (and at most the population size).
    * 9.1.3 **Cut points** (`random_cut_points`): three different random numbers between 1 and the number of genes (frames), sorted. Cut `c` means genes `1..c` stay before the cut. If `c3` equals the number of genes the fourth part is empty and the crossover is in fact two-point; this is allowed and does not fail. At least 3 genes are required (clear error otherwise).
    * 9.1.4 **Three-point crossover** (`three_point_crossover`): both parents are cut into four parts and parts 2 and 4 are exchanged: child 1 = `A1 B2 A3 B4`, child 2 = `B1 A2 B3 A4`.
    * 9.1.5 Both children are built and evaluated with `_make_member` **inside Generation-g**, next to their parents, as members `N+1 .. 2N` (`Gen-g-(N+1)` ... `Gen-g-2N`), so `Generation-g` holds 2N members.
* **9.2** (`_step9_2_next_generation`) The N members with the highest fitness among the 2N (parents first, so a parent wins a tie) are **copied** to `Generation-(g+1)` as `Gen-(g+1)-1 ... Gen-(g+1)-N`, best first, and become `ctx.population` for the next iteration (genes and fitness are carried over, nothing is re-evaluated). **Only the `.sdb` is copied** (`database_folder.copy_member_model`; it keeps the analysis results), the originals stay in `Generation-g`. Before copying, the reference model is reopened so SAP2000 does not lock the last evaluated file. There is **no Dominated folder** (an idea dropped on 2026-11-02).
* After the last iteration `Generation-(genSize+1)` holds the final population and `ctx.population[0]` is the best member (step 10 will work on it).
* **`fitness_value` (`services/fitness.py`) is temporary:** it accepts only a plain number and a larger value is better; it raises a clear error for `None`. When `fitness_calculator` is described (several objectives, penalty), the rule that makes one number from its result goes there.
* Disk: every generation keeps all its member folders with the files SAP2000 wrote while running; the size grows with `genSize * popSize`.

### SAP2000 connection decisions (`core/sap_client.py`)

* Uses `pythonnet` with the .NET Framework runtime (`pythonnet.load("netfx")`) and loads `SAP2000v1.dll` directly, like `NET.addAssembly` in the MATLAB code.
* **Only SAP2000 v23 is supported** (company rule: everyone has it). The DLL is bundled in `src/core/vendor/sap2000_v23/SAP2000v1.dll`. After connecting, the running SAP version is checked and anything other than v23 gives a clear error. SAP2000 itself must still be installed.
* The DLL ships inside the app update package; running it from `%LocalAppData%` is not a problem (confirmed by the user). `build.py` zips every file under `src/`, so the DLL is included; `.gitignore` must not exclude it.
* `openSapModel.m` also deletes non-`.sdb` files in the model folder; this was **deliberately not ported**.
* The SAP2000 imports are lazy, so the app starts even if `pythonnet` is missing.
* Methods: `connect`, `open_model` (OpenFile + N-m-C), `frame_section_names`, `read_table`, and since GA step 8: `unlock_model` (`SetModelIsLocked(False)`), `assign_frame_section` (`FrameObj.SetSection(frame, section, eItemType.Objects)`), `save_model_as` (`File.Save(path)`, as in `runAll.m`). Python binding of `ref` / `out` parameters returns tuples (`read_table`, `frame_section_names`, `_check_version`).
* **Verified by the user on a real SAP2000 v23 (2026-10-27):** connecting (attach or start), opening the model, `PropFrame.GetNameList` and the version check, with the calls running in a `QThread`.

### Unverified (Auto Design)

Written without running on a real SAP2000; check these first when the user reports a problem:

* `read_table` (`GetTableForDisplayArray` binding) and steps 5 to 7: the table and field names (`SectionName`, `Material`, `Type`, `Frame`, `AnalSect`, `Joint`, `GlobalX/Y/Z`, `JointI`, `JointJ`) come from the user's knowledge of SAP2000 database tables; the README of 2026-10-27 only recorded steps 1 to 3 as verified.
* The new `SapClient` methods of step 8 (`SetSection` with the `eItemType` argument, `File.Save(path)` as Save As).
* **Step 9 never ran** (it needs `classify_frame` and `fitness_calculator` first): the whole loop, the copy of the `.sdb` after reopening the reference model (a possible file lock on Windows), the status lines, and the time of a generation with real models.
* The same `SapClient`, created in the sections page's thread, is used from the run worker thread (a different `QThread`); COM/.NET apartment problems would show up as errors at the first SAP call of the run.
* The run page and its worker were not seen running on a display.
* `shutil.rmtree(onexc=...)` needs Python 3.12 (the runtime is 3.12.10).
* Automated tests exist only for the pure parts of step 9 (`tests/auto_design/test_genetic_operators.py`, `test_database_folder.py`), run on Linux with a stand-in `Individual`; run them once with the project runtime. Steps 5 to 8 have no tests.
* The UI check `tournamentSize >= 2` in `ga_settings_page.py` was given as a snippet (the file was not available to edit): make sure it was applied.

## SLD to SAP (current state)

Converts the piping SLD (CSV files written by `SLD2SAP.lsp` from the AutoCAD layer `TAGGED_LOADS`) into two SAP2000 import tables: joints (point loads, circles) and distributed frame loads (rectangles). It is a port of the user's working MATLAB tool `SLD2SAP.m` (v1.4). The full algorithm, file formats, token table, error codes and the verified differences from MATLAB are in `docs/sld_to_sap_algorithm.md`; this section only describes the code.

* **Inputs** (`ui/page.py`): `z0` (m, default 0), tolerance (mm, default 10), end tolerance (mm, default 5), EQ.Z coefficient (**default 1**, also the default of `SldParams.eqz_coef`), friction coefficient (default 0.15); a list of CSV files or folders; the SAP2000 Excel export (sheets `Connectivity - Frame` and `Joint Coordinates`). The output folder is asked in a dialog when **Convert** is pressed (the dialog starts next to the Excel file); existing output files with the same names are overwritten without asking. `LISP` is not changed.
* **Downloads on the page:** "Download LISP" saves `assets/SLD2SAP.lsp`; "Open Rules" opens `assets/Rules of SLD2SAP.pdf` from a copy in the temp folder (so a PDF viewer never locks a file inside the app folder and blocks updates).
* **All problems are shown together, automatically.** Any change of an input (file added or removed, Excel file, any parameter) re-runs the whole check in a background worker (debounced 350 ms; older results are dropped by a version counter; the loading overlay appears only if it takes longer than a moment). Without a valid Excel file only the structure check (`check_structure`, CSV files only, S codes) runs; with it, `convert` also adds the matching errors (M codes). The Excel file is read once and cached by (path, modification time, size). Nothing stops at the first error.
* **All or nothing:** `Convert` is enabled only when the full check has no error, and `write_outputs` refuses to write when the result has errors. Warnings (W01: two points with the same coordinates) do not block. Convert runs `convert` again (the Excel comes from the cache) before writing.
* **Issue table:** sorted by file, then errors before warnings, then `Index`. Double-clicking a row copies its CAD coordinates (mm) to find the object in AutoCAD.
* **Outputs:** `SAP2000 Joint Coordinates.xlsx` (sheet `Joint Coordinates`) and `SAP2000 Distributed Loads.xlsx` (sheet `Frame Loads - Distributed`), written from row 4 into the workbooks in `templates/`. Headers are fixed SAP strings and must not be changed. `relDist` / `absDist` are not rounded (bit-for-bit comparison with MATLAB is the goal). Frame names are written as numbers only when they are a canonical integer string (`9`, not `007`), else as text.
* **Behaviours that differ from MATLAB on purpose** (all confirmed in the guide): the "load inside the frame" test is correct for reversed frames (`lo = min(pI,pJ)`, `hi = max(pI,pJ)`), `endTolerance` is applied at the beam ends and the distances are clamped to `[0, Length]`, point names must be unique over all files (S10), `LS`/`LT` duplicates are checked in plans, a non-numeric value after `=` (S14) and a text that is only a number (S15) are errors, halves are rounded away from zero (`round_mm`), point names are compared case-insensitively (SAP is not case sensitive), a negative load value is an error (S18), `V=`/`FV=` twice in one rectangle is S11, a non-numeric `Index` is S17, a CSV with no data rows is S01, a frame with a non-positive `Length` is M06 and a joint with non-numeric coordinates is M07. When the Connectivity file is unusable (M03/M04) no frame matching runs, so there is no flood of M01. `check_structure` takes `z0` so W01 in stage 1 uses the user's value (`ui/page.py` passes `self.params.z0`).
* **Not implemented:** warning W02 (file name does not match the origin row), plan rectangles that are not axis-aligned (never produced by the current LISP), graphical preview (declined), direct import into SAP2000 through OAPI (later phase).

### Unverified (SLD to SAP)

* The UI was run only on the installed 1.1.5 start-up; the issue table and the conversion on real data were not reviewed with the user yet. Report any problem.
* The tests use the worked examples of the guide (section 10) and synthetic files. The comparison with the real successful MATLAB run (second sample set, guide section 9.14: 5 joints and 116 load records, bit-for-bit) has **not** been done in this code: the sample files and the two MATLAB outputs must be supplied.
* The guide lists cases missing from the samples: reversed frame, `HT` / `LT`, point load in a plan with a height value, point with an extra value, `FV=`. A small complete sample set with MATLAB output is still needed (guide section 14).
* `tests/sld_to_sap/test_sld_to_sap.py` was written where `pytest` could not be installed and was run with a minimal stand-in; run it once with real pytest on the project runtime (pytest is now installed in the dev runtime, see Development). If a test relies on the old `SldParams` default `eqz_coef = 0.2`, give it the value explicitly.
* The code-versus-guide review of 2026-10-25 is closed: the guide (now numbered with the app version, 1.1.6) matches the code. The new checks (S17 for `Index`, S18, case-insensitive S10, M06, M07, M01 suppression, frame-name rule) and the `eqz_coef` default of 1 may break the old `tests/sld_to_sap/test_sld_to_sap.py` (not reviewed); run it and update the expectations.

### Unverified (release system)

* The launcher's update flow (1.0.0) was tested with a fake server on Linux (good update, bad sha256, failed self-check with rollback, no server). On the user's PC only the installation and the first start were seen working. A real update (1.1.5 → next version) and a runtime update (new library) have **not** been tried on a user machine yet.
* **Not run yet (written without a display or Windows):** the update question of launcher 1.1.0 (`ask_user` / `ask_update` / `UpdatePromptDialog`, the stdout protocol, closing the "Updating…" window, the Windows message-box fallback) and the mandatory mode. `tests/bootstrap/test_launcher.py` covers the launcher logic with a fake server and a fake app (accepted, later, mandatory exit, silent mode, repair without a question, bad sha256 closes the window, protocol, fallbacks) and passed with a minimal stand-in runner; the real windows were never seen. Check: look of both windows, `Later` / `Exit` / `Update now`, the busy bar, the window really closing when the new app starts, and that a window opened by the installed app does not show a Python icon in the taskbar.
* The "What's new" window (`ReleaseNotesDialog`) was never seen on a display: check the transparent rounded corners, the notes area height with few and many notes, and dragging.
* The shortcut icon (`app.ico` in the installer, found by `build.py` as the first `.ico` under `src/`, or `"icon"` in `release_config.json`) needs a new Setup build to be checked.

## Rules

* The shell (`src/ui/`) never contains plugin-specific logic; a plugin never controls the shell. Plugin UI lives in `plugins/<name>/ui/`, business logic in `plugins/<name>/services/` (no Qt there). Code shared by several plugins (like the SAP connection) lives in `src/core/`.
* Do not remove or rename `main()`, `ping_app()` and `ask_update()` without updating the launcher contract (`ping_app()` is the post-update self-check; it must work without a display). Changes to `docs/contract.md` or `launcher.py` break installed copies and need a new Setup (and a higher `BOOTSTRAP_VERSION` / `min_bootstrap_version`).
* The version number lives in `src/version.py` only (plus `pyproject.toml`, checked by `build.py`). It is always the value written in the project files, unless the user explicitly says otherwise. Do not type it anywhere else. Every release gets an entry in `src/release_notes.json` (for users) and in the change log below (for developers). Dates already written in the change log are never changed.
* Create planned files only when they are actually implemented. Every package folder needs an `__init__.py`, otherwise `pyproject.toml` (`packages.find include = ["src*"]`) skips it.
* Always use the project runtime; `python` / `py` may not exist globally.
* Tests of a plugin live in `tests/<plugin name>/`; tests of shell services in `tests/core/`; tests of the launcher in `tests/bootstrap/`.
* **Working with Claude (project instructions):** after changing any code, state which file changed and its exact folder location. If a project file that is needed is not among the provided references (for example `home_page.py`, `main_window.py`, `widgets.py`, `registry.py`), say so before guessing. Say clearly what was written but not run.
* Auto Design: the GA only talks to the SAP model through small functions (`fitness_calculator`, `SapClient` methods) so the engine can be replaced later (surrogate); every evaluation should end up stored (see the project plan, `core/storage.py` is a stub); the reference file chosen by the user is never modified or saved.

## Development

* Windows, VSCode, project Python: `D:\Python Library\StructureLab\runtime\python\python.exe`.
* Run (or F5 with the "Structure Lab" launch config, module `src`): `.\runtime\python\python.exe -m src` (works because the dev `python312._pth` contains `..\..`; do not copy this file into a release).
* Install deps: `.\runtime\python\python.exe -m pip install -r .\runtime\requirements.txt`
* Dev tools (installed in the dev runtime only; they are in `DEV_ONLY` of `build.py`, so they never reach users and do not change the runtime id; do not add them to `runtime/requirements.txt`): `.\runtime\python\python.exe -m pip install pytest pytest-qt ruff` (behind the company proxy add `--proxy http://kerio:3128`).
* Tests / lint: `.\runtime\python\python.exe -m pytest` (one folder: `.\runtime\python\python.exe -m pytest tests\sld_to_sap`, `tests\auto_design`, `tests\core`, `tests\bootstrap`) and `.\runtime\python\python.exe -m ruff check .`
* To see the "What's new" window without a release: write `{"last_seen_version": "1.1.5"}` into `user_state.json` in the data folder (normally `%LocalAppData%\Structure Lab`) and start the app.
* To see the update window alone: call `ask_update(<request.json>)` from `src.__main__` with a file `{"current": "1.1.5", "new": "1.2.1", "mandatory": false, "notes": [...]}` (it prints the answer on stdout).
* Auto Design logs go to `app.log` (`Step 5 ...`, `Step 8 - initial population ...`, `Step 9.1 - g=.. m=..: parents .. x .., cuts ..`, `Step 9.2 - ...`, `Status: ...`); a failed run also shows its message on the run page.
* Release: see "Release and update system" above (`tools\build.py`, `tools\publish.py`; Inno Setup 6/7 only on the build PC, e.g. `C:\Users\b.sarkheil\AppData\Local\Programs\Inno Setup 7\ISCC.exe`).

## Status

Done: project structure, embedded runtime, VSCode debugging, dark-themed shell (title bar, sidebar, Home), plugin registry, page switching, **Auto Design**: wizard steps 1 to 3 (confirmed by the user on a real SAP2000 v23), the live run page with cooperative cancel, the run worker thread, the database-folder check/clear with the user warning, GA steps 5 to 9 written (steps 5 to 7 read the model through database tables; step 8 builds the initial population; step 9 is the generation loop with tournament selection, three-point crossover and the copy of the best N to the next generation) with `classify_frame` and `fitness_calculator` still missing and step 10 not described yet; SLD to SAP services (complete algorithm, tested on the guide's examples) and its single-page UI with automatic, collected error checking; about page; loading overlay; the full release system (installer, launcher with auto-update from the server share, build and publish tools). Version 1.1.5 was the first release; 1.1.6 is published and adds the release notes window, the update question with a mandatory mode (launcher 1.1.0, needs a new Setup) and the SLD to SAP check changes; `version.py` shows 1.2.1 (Auto Design development, not released yet).

Known technical issues to fix next:

* `TitleBar`: `self.window` shadows `QWidget.window()`; dragging should use `startSystemMove()`; no edge resizing.
* `HomePage` has a fixed `plugin_order` list of plugin names, which is plugin-specific knowledge inside the shell; it should follow the registry order (a new plugin not named there never appears on Home).
* Dead QSS rules in `ui/theme.py`: `QLabel#aboutName` (no such label any more) and `QFrame#aboutCard:pressed` (`QFrame` has no pressed state).
* `plugins/` uses absolute `src.` imports while `ui/` uses relative ones; unify (launcher runs the app from `app\<version>\`, with that folder first in `sys.path`, so both styles work). The Auto Design files, `core/sap_client.py` and the SLD to SAP plugin follow the absolute style.
* `auto_design/ui/ga_settings_page.py` imports `folder_icon` from `plugins/sld_to_sap/ui/icons.py` (a plugin importing another plugin); move the icon to `src/ui/` when convenient.
* Dependencies are listed in both `pyproject.toml` and `runtime/requirements.txt`. Dev packages are left out of the release runtime by `tools/build.py` (names listed in `DEV_ONLY`), but a cleaner fix is a separate dev requirements file.
* The sidebar and Home now use PNG icons; the only text-glyph fallback left is `◈` in `TitleBar` when `logo4.ico` is missing.
* Step 2 does not stop its worker thread if the app closes while loading; the run worker is not stopped either when the window closes during a run.
* Auto Design tests: only the pure parts of step 9 are covered. Still easy to cover in `tests/auto_design/`: `compile_name_filter` (in `sections_page.py`), `services/sections_excel.py`, the parsing helpers in `ui/fields.py`, `build_gene_options`, `random_genes`, `clear_folder` / `check_folder_usable` (use a temp folder), `RunMonitor`.
* The progress estimate of the run page does not match the real work (see "Wizard state and the run lifecycle").
* SLD to SAP runs its checks in a background worker; re-check on a large model.
* A mandatory update is decided by the newest version on the server only (see the release steps).

## Next session

1. **Auto Design:** the user will describe `classify_frame` (step 8.2.1.1: role of a frame from joint coordinates, `frameConnectivity` and `tolerance` in cm; coordinates are in meters), then `fitness_calculator` (then replace the temporary `fitness_value`), then **step 10** (typing of the selected member, `ctx.population[0]` after the run; the user will say at the very end what to do). Wire `monitor.generation(GenerationStats)` once the fitness has weight and DCR; replace the temporary progress estimate; use or drop the unused settings (`updateSeismicLoads`, `penalizeLevel`, `mutationPercent`). Apply the `tournamentSize >= 2` check in `ga_settings_page.py` if it is not applied yet.
2. Run Auto Design on the real SAP2000 v23 and report what fails (see "Unverified (Auto Design)"). Until `classify_frame` is written the run stops in step 8 with `NotImplementedError`.
3. Check `pythonnet` in `pyproject.toml` and remove the duplicate `openpyxl` line in `runtime/requirements.txt`.
4. Look at the two new windows (What's new, Update available; both modes) and fix whatever the display shows (see "Unverified (release system)").
5. Build a new Setup (launcher 1.1.0, `min_bootstrap_version` 1.1.0) with `build.py --installer`, install it on the user's PC, then release the next version with `build.py` + `publish.py` (add an entry to `src/release_notes.json` first) and check on a user PC that the question appears at the next launch and the update works (`logs\launcher.log`). Try a mandatory release (`--mandatory`) and one runtime change (new library).
6. Check the Start Menu / taskbar icon of the new Setup.
7. SLD to SAP: run `tests/sld_to_sap/test_sld_to_sap.py` with real pytest and fix expectations changed by the 2026-10-25 code changes.
8. SLD to SAP: supply the second sample set (CSV files, Connectivity, the two MATLAB outputs) so a test compares the 5 joints and 116 load records bit-for-bit; then a small complete sample set for the missing cases (guide section 14).
9. Ideas the user declined for Auto Design step 2, do not build unless asked again: smart grouping by section family or dimensions, remembering the last choice per section name, saved templates, a warning when a role has no section. Also declined for now: a background "new version is ready, restart" notice while the app is open. Dropped for step 9.2: a `Dominated` folder (the best N are copied to the next generation instead).
10. At the end of the Auto Design work: write the complete document of the implemented algorithm (`docs/`), and keep this README short on algorithm details.

## Change log
* [1.2.1] - (2026-11-??):
    - Auto Design development resumed: `AUTO_DESIGN_ENABLED` set to `True` in `plugins/registry.py` (Auto Design is a normal tool again on Home and in the sidebar)
    - Auto Design wizard: step 1 SAP2000 file drop area (`ui/page.py`), step 2 sections table (`ui/sections_page.py`), step 3 GA settings (new `ui/ga_settings_page.py`, shared form widgets in new `ui/fields.py`); `AutoDesignParams` no longer holds the SAP file path; SAP2000 connection and these three steps confirmed by the user on a real SAP2000 v23
    - (2026-10-28) GA settings gained `updateSeismicLoads` and `modelsFolder` (`params.py`, `ui/ga_settings_page.py`); Simulate Evolution button with its icon (`ui/icons.py`, `Run-Genetic.png`)
    - (2026-10-28) run page (`ui/run_page.py`): progress bar, live tiles, evolution chart, status log, Cancel / Back; `services/run_monitor.py` (`RunMonitor`, `RunCancelled`, `GenerationStats`); `ui/wizard.py` runs the GA in `_RunWorker` (QThread) and feeds the page
    - (2026-10-28) GA steps 5 to 7 in `services/ga_run.py` (`GAContext`, `run_ga`) with `section_materials.py` (Material Type per section), `frame_assignments.py` (section per frame), `model_geometry.py` (joint coordinates, frame connectivity), `sap_tables.py`; `SectionPermission.materialType` added; `SapClient.read_table` added
    - (2026-11-01) GA step 8 (initial population): new `services/population.py` (`Individual`, role constants, `classify_frame` stub, `build_gene_options`, `random_genes`) and `services/fitness.py` (`fitness_calculator` stub); `ga_run.py` (`GAContext.sapPath`, `population`, `rng`, `step8_initial_population`); `wizard.py` passes `sapPath`
    - (2026-11-01) database folder is cleared at the start of every run: new `services/database_folder.py`, `ga_run.prepare_database_folder`, warning dialog in `wizard.py` (`_confirm_database_folder`)
    - (2026-11-01) `core/sap_client.py`: `unlock_model`, `assign_frame_section`, `save_model_as`
    - README rewritten to match (layout, Auto Design section, unverified list, next session)
    - (2026-11-02) GA step 9 (generation loop): new `services/genetic_operators.py` (`tournament_parents`, `random_cut_points`, `three_point_crossover`, `select_survivors`); `ga_run.py` (`step9_generations`, `_step9_2_next_generation`, `_make_member` shared with step 8, `GAContext.offspring` and `generation`); `database_folder.py` (`generation_folder`, `copy_member_model`); `fitness.py` (`fitness_value`, temporary); children are built inside `Generation-g` as members N+1..2N and the best N are copied (`.sdb` only) to `Generation-(g+1)`; no Dominated folder
    - (2026-11-02) tests: `tests/auto_design/test_genetic_operators.py`, `tests/auto_design/test_database_folder.py`
    - (2026-11-02) rule `2 <= tournamentSize <= popSize` agreed (UI check in `ui/ga_settings_page.py`, plus the algorithm's own error)
    - (2026-11-02) README updated: the "20 steps" count sub-steps, steps 1 to 9 are described, step 10 (typing of the selected member) is still to be described

* [1.1.6] - (2026-10-27):
    - version raised to 1.1.6 (`version.py`; `pyproject.toml` must show the same); `docs/sld_to_sap_algorithm.md` carries the app version number
    - `plugins/sld_to_sap/params.py`: default `eqz_coef` changed from 0.2 to 1.0 (same as the UI field)
    - `plugins/sld_to_sap/services/`: `sld_reader.py` (S17 for a bad `Index`, S01 for a file with no data rows), `connectivity.py` (M06, M07), `load_rules.py` (S18; `V`/`FV` twice is S11), `exporter.py` (frame name is a number only if canonical integer), `pipeline.py` (case-insensitive S10, no M01 when the model is unusable, `check_structure(z0)`); `ui/page.py` passes `z0` to `check_structure`
    - `docs/sld_to_sap_algorithm.md` updated to match the code (code is the reference)
    - README updated to match the code (release switch `AUTO_DESIGN_ENABLED`, layout of `sld_to_sap`, Home `plugin_order` caveat, hero banner fade, SLD to SAP behaviour)
    - release notes: `src/release_notes.json` (hand-written, per version), `core/release_notes.py` (what the user has not seen yet, `user_state.json`), `ui/sheet_dialog.py` (shared base of the small windows), `ui/release_notes_dialog.py` ("What's new" with Got it), `MainWindow.show_release_notes_if_needed()` called from `__main__.main()` 300 ms after the window is shown
    - update question: `ui/update_dialogs.py` (`UpdatePromptDialog`: Update now / Later, or Update now / Exit when mandatory, switches to "Updating…"), `__main__.ask_update()` and `_create_app()`, `bootstrap/launcher.py` 1.1.0 (asks before updating, stdout protocol `UPDATE`/`LATER`/`EXIT`, Windows message-box fallback, `--update-only` / `--yes` skip the question), `tools/build.py` (`--mandatory`, `release_notes` in `latest.json`, warning for a missing notes entry), `tools/release_config.json` (`min_bootstrap_version` 1.1.0), `docs/contract.md` updated (new frozen part: `ask_update`, `latest.json` fields, the question protocol); needs a new Setup
    - update window polish: both version boxes have the same width, installed = warm and new = cyan, a drawn gradient arrow between them (`FlowArrow`), bold larger question, no release notes in the update window (shown once after the update); What's new: one framed card per version titled with version and date, NEW green / IMPROVED blue / FIXED warm tags
    - tests: `tests/core/test_release_notes.py`, `tests/bootstrap/test_launcher.py`

* [1.1.5] - (2026-10-24):
    - version no. is mentioning to SLD2SAP.m last ver. as v1.4
    - SLD to SAP plugin: `SldToSapPlugin` replaces the placeholder in `plugins/registry.py`; services `issues.py`, `geometry.py`, `sld_reader.py`, `connectivity.py`, `matcher.py`, `load_rules.py`, `pipeline.py`, `exporter.py` and `params.py` written from `docs/sld_to_sap_algorithm.md`
    - SLD to SAP page (`ui/page.py`): parameters, CSV list, Excel model, output folder; stage 1 (CSV only) and stage 2 (with the Excel model) checks re-run automatically and list all errors together, sorted by file; `Convert` enabled only without errors; double-click on an issue copies its CAD coordinates
    - SLD to SAP tests in `tests/sld_to_sap/test_sld_to_sap.py`
    - SLD to SAP plugin: UI/UX improvements
    - SLD to SAP plugin: backgroundworker for multi threading to prevent lags
    - add overlay loading
    - about page
    - release system: `bootstrap/installer.iss` (per-user Inno Setup installer into `%LocalAppData%\Structure Lab`, no Programs and Features entry, shortcuts with icon and `AppUserModelID`), `bootstrap/launcher.py` (auto-update from `\\be-sarkheil\Share\Structure Lab`, fail-open, sha256 check, self-check with automatic rollback, lock file, local log only), `tools/build.py`, `tools/publish.py`, `tools/release_config.json`, `docs/contract.md` updated
    - `core/paths.py`: `APP_NAME` is now `Structure Lab`; uses `STRUCTURELAB_ROOT` when set by the launcher
    - `__main__.py`: `setup_logging()` is now called at the start of `main()`
    - `server_sim/` removed

* [1.0.0] - (2026-10-20):
    - initial shell (PySide6, embedded Python 3.12.10, dark theme, title bar, sidebar)
    - initial plugin architecture
    - plugin registry wired to navigation and Home
    - clickable cards
    - `QStackedWidget` page switching with lazy page creation; `PlaceholderPlugin`
    - new theme with color tokens, Bahnschrift titles
    - drawing-sheet hero banner with a one-time logo fade-in
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