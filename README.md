# Dota Support Draft Assistant

An explainable personal Dota 2 draft assistant for Position 4 and Position 5 players.

## Current milestone

DOTA-001 establishes domain contracts, local SQLite repositories, provider boundaries, a deliberately minimal deterministic scoring contract, and a PySide6 desktop shell. It does **not** connect to public APIs, read the Dota process, automate gameplay, or contain a production recommendation algorithm.

DOTA-002 adds a read-only OpenDota provider with explicit cache/provenance and unknown-role safeguards. It has no recommendation weighting or automatic draft collection.

DOTA-003 adds manual picks/bans and an immediately updating legal candidate list. Candidate ordering may reflect all-time personal familiarity; it is not recommendation scoring.

## Run

Install Python 3.11+ dependencies, then run from this directory:

```powershell
python -m pip install -e ".[dev]"
python -m dota_support_draft
```

The window shows `Ready`; close it normally to exit. See [Windows packaging](docs/WINDOWS_PACKAGING.md) for the future executable contract.

## Optional OpenDota smoke

This does a live request only when you explicitly supply your own account ID; it never prints raw match data:

```powershell
$env:DOTA_SUPPORT_ACCOUNT_ID = "your-steam32-account-id"
python -m dota_support_draft.smoke
```

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
