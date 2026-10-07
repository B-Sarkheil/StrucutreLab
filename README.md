# Structure Lab

Integrated engineering desktop software for Windows (Python + PySide6) for about 30 users. It gradually replaces scattered MATLAB and Excel-VBA tools. Each tool is a plugin.

First real tool: **Auto Design**, automatic structural section optimization (Genetic Algorithm + SAP2000 OAPI).

Design context lives in two docs in the project knowledge:

* `claude/engineering-platform-decisions.md`: bootstrap / runtime / app layers, auto-update from the server, IT constraints.
* `claude/project-plan-structural-optimization.md`: Auto Design plan (Phase 1 GA, Phase 2 ML surrogate lab, Phase 3 general model).

## Layout

```text
StructureLab/
├── bootstrap/          launcher.py, installer.iss (kept stable; contract in docs/contract.md)
├── runtime/            embedded Python 3.12.10 x64 + requirements.txt
├── src/
│   ├── __main__.py     entry point: main(), ping_app()
│   ├── version.py      single source of the version (1.0.0; pyproject.toml must match)
│   ├── core/           app-wide services (not started yet)
│   ├── ui/             shell only: main_window, navigation, home_page, widgets, theme, assets/icons/
│   └── plugins/        base.py, registry.py, placeholder.py, <plugin>/
│       └── auto_design/    plugin.py (stub), later ui/ and services/
├── tools/              build.py, publish.py
├── server_sim/  tests/  docs/  pyproject.toml
```

## How the app works

* `__main__.main()`: QApplication → `apply_theme` → `register_builtin_plugins()` → `MainWindow` → `app.exec()`.
* **Plugin contract** (`plugins/base.py`): `name` (unique key), `title`, `icon`, `description`, `available` (False = planned, not built), and `create_widget() -> QWidget`.
* **Registry** (`plugins/registry.py`): explicit and simple. `register_builtin_plugins()` lists all plugins in navigation order; `load_plugins()` returns them. No auto-discovery yet.
* **Shell** (`ui/`): `MainWindow` reads the registry and passes the plugins to `Navigation` (sidebar) and `HomePage` (one clickable card per plugin). Clicking a sidebar item or a card calls `MainWindow.show_page(key)`. Home is built at startup; each plugin page is created lazily on first open and kept in a `FadeStackedWidget` (a `QStackedWidget` that fades the new page in). If `create_widget()` fails, the error is logged and the current page stays.
* **Not implemented yet:** Auto CPS, SLD to SAP, PDMS to SAP are `PlaceholderPlugin` instances (they open an "Under development" page). Auto Design also shows the placeholder page until its real UI exists.
* **Visual language** ("structural drawing sheet"): all colors are tokens at the top of `ui/theme.py` (blueprint-ink surfaces, drafting-cyan linework, amber as the single signal color for active/hover/focus). Titles use Bahnschrift, body uses Segoe UI. Most widgets are styled by `objectName` in the stylesheet; cards, the hero banner and the sidebar marker are painted in code (`ui/widgets.py`, `ui/home_page.py`, `ui/navigation.py`) and read the same tokens. Available tools get large cards, planned tools get dashed rows.

## Rules

* The shell (`src/ui/`) never contains plugin-specific logic; a plugin never controls the shell. Plugin UI lives in `plugins/<name>/ui/`, business logic in `plugins/<name>/services/`.
* Do not remove or rename `main()` and `ping_app()` without updating the launcher contract (`ping_app()` is the post-update self-check).
* Create planned files (e.g. Auto Design `services/`) only when they are actually implemented.
* Always use the project runtime; `python` / `py` may not exist globally.

## Development

* Windows, VSCode, project Python: `D:\Python Library\StructureLab\runtime\python\python.exe`.
* Run (or F5 with the "Structure Lab" launch config, module `src`): `.\runtime\python\python.exe -m src`
* Install deps: `.\runtime\python\python.exe -m pip install -r .\runtime\requirements.txt`
* Tests / lint: `.\runtime\python\python.exe -m pytest` and `.\runtime\python\python.exe -m ruff check .`

## Status

Done: project structure, embedded runtime, VSCode debugging, dark-themed shell (title bar, sidebar, Home), plugin registry, page switching, Auto Design stub registered.

Known technical issues to fix next:

* `TitleBar`: `self.window` shadows `QWidget.window()`; dragging should use `startSystemMove()`; no edge resizing.
* Dead `about_name` label in `navigation.py`.
* `plugins/` uses absolute `src.` imports while `ui/` uses relative ones; unify (launcher runs the app from `app\<version>\`).
* Dependencies are listed in both `pyproject.toml` and `runtime/requirements.txt`; dev tools (pytest, ruff, mypy, scikit-learn) must not ship in the release runtime.
* Text glyph icons (⚙ ◈ ⇄ ◇) are inconsistent with the PNG icons; no logging setup yet; `QApplication([])` should receive `sys.argv`.

Next: replace glyph icons with the user's own icon set and add the app logo (title bar, About card, window icon); check the new look on a real display (it was written without a visual check); then Auto Design UI (`plugins/auto_design/ui/page.py`), then its optimization logic (see the plan doc).

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