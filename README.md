# Dota Support Draft Assistant

An explainable personal Dota 2 draft assistant for Position 4 and Position 5 players.

## Current milestone

DOTA-001 establishes domain contracts, local SQLite repositories, provider boundaries, a deliberately minimal deterministic scoring contract, and a PySide6 desktop shell. It does **not** connect to public APIs, read the Dota process, automate gameplay, or contain a production recommendation algorithm.

## Run

Install Python 3.11+ dependencies, then run from this directory:

```powershell
python -m pip install -e ".[dev]"
python -m dota_support_draft
```

The window shows `Ready`; close it normally to exit. See [Windows packaging](docs/WINDOWS_PACKAGING.md) for the future executable contract.

## Quality gates

```powershell
pytest
ruff check .
ruff format --check .
mypy .
git diff --check
```

## Scope and data integrity

Only normalized domain objects move beyond providers. Public and personal statistics require provenance and patch context. Test fixtures are labelled as such and are never presented as real statistics.

