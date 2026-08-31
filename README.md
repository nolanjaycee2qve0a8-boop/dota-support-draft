# Dota Support Draft Assistant

An explainable personal Dota 2 draft assistant for Position 4 and Position 5 players.

## Current milestone

DOTA-001 establishes domain contracts, local SQLite repositories, provider boundaries, a deliberately minimal deterministic scoring contract, and a PySide6 desktop shell. It does **not** connect to public APIs, read the Dota process, automate gameplay, or contain a production recommendation algorithm.

DOTA-002 adds a read-only OpenDota provider with explicit cache/provenance and unknown-role safeguards. It has no recommendation weighting or automatic draft collection.

DOTA-003 adds manual picks/bans and an immediately updating legal candidate list. Candidate ordering may reflect all-time personal familiarity; it is not recommendation scoring.

DOTA-004 adds a position-aware experimental evidence/scoring boundary. STRATZ is optional: current-week P4/P5 meta is loaded only with a token, remains explicitly non-patch-isolated, and failures preserve manual drafting. Draft-dependent pair refresh remains DOTA-005 work. See [STRATZ integration](docs/STRATZ_INTEGRATION.md) and [recommendation evidence](docs/RECOMMENDATION_EVIDENCE.md).

DOTA-005 adds event-driven, debounced background pair enrichment for a bounded top-8 preliminary shortlist. Draft edits remain immediately local; stale pair work is ignored and Meta/Familiarity stays available while pair data loads or fails.

DOTA-006 makes the existing pair-refresh boundary observable: the UI shows the current role, ally/enemy scope, deterministic shortlist, and Counter/Synergy availability. It adds no manual refresh action, provider call, or scoring change.

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

## Optional STRATZ smoke

This performs compact live current-week P4/P5 and laneOutcome checks only when a token is supplied. It does not print a token or raw payloads.

```powershell
python -m dota_support_draft.stratz_smoke
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
