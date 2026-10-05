# Structure Lab

Integrated engineering software (Python, Windows) for ~30 users.
First tool: **Auto Design** (automatic section optimization with SAP2000 and GA algorithm).

## Layers
- `bootstrap/`: launcher + installer (almost frozen, see `docs/contract.md`)
- runtime: Python + libraries (built from `runtime/requirements.txt`)
- `src/`: app code (updated often)

## Development
```
uv sync
uv run python -m src
uv run pytest
uv run ruff check .
```

## Folders
| Folder | Purpose |
|---|---|
| `bootstrap/` | launcher.py, installer.iss, assets |
| `src/` | application package (core, ui, plugins) |
| `tools/` | build.py, publish.py |
| `server_sim/` | simulated server folder for update tests |
| `tests/` | pytest |
| `docs/` | contract and notes |

## Change Log
[1.0] - 2026-09-??
    - 