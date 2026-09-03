# Dota Support Draft Assistant

An explainable personal Dota 2 draft assistant for Position 4 and Position 5 players.

## Current milestone

DOTA-001 establishes domain contracts, local SQLite repositories, provider boundaries, a deliberately minimal deterministic scoring contract, and a PySide6 desktop shell. It does **not** connect to public APIs, read the Dota process, automate gameplay, or contain a production recommendation algorithm.

DOTA-002 adds a read-only OpenDota provider with explicit cache/provenance and unknown-role safeguards. It has no recommendation weighting or automatic draft collection.

DOTA-003 adds manual picks/bans and an immediately updating legal candidate list. Candidate ordering may reflect all-time personal familiarity; it is not recommendation scoring.

DOTA-004 adds a position-aware experimental evidence/scoring boundary. STRATZ is optional: current-week P4/P5 meta is loaded only with a token, remains explicitly non-patch-isolated, and failures preserve manual drafting. Draft-dependent pair refresh remains DOTA-005 work. See [STRATZ integration](docs/STRATZ_INTEGRATION.md) and [recommendation evidence](docs/RECOMMENDATION_EVIDENCE.md).

DOTA-005 adds event-driven, debounced background pair enrichment for a bounded top-8 preliminary shortlist. Draft edits remain immediately local; stale pair work is ignored and Meta/Familiarity stays available while pair data loads or fails.

DOTA-006 makes the existing pair-refresh boundary observable: the UI shows the current role, ally/enemy scope, deterministic shortlist, and Counter/Synergy availability. It adds no manual refresh action, provider call, or scoring change.

DOTA-007 adds `Refresh pair evidence` for the current draft context. It explicitly retries/recalculates current pair evidence through the existing asynchronous boundary; it does not purge provider caches or promise a new external HTTP request. The action is unavailable until the draft has a legal shortlist and at least one allied or enemy pick.

DOTA-008 adds a read-only selected-candidate explanation panel. It presents the complete local Meta, Counter, Synergy, Personal, confidence, and Why evidence for the current P4/P5 context. Selecting or searching candidates does not request data; the panel explains already calculated experimental ordering evidence, not a win prediction.

DOTA-011 adds a `Configure Player` entry for a public numeric Steam32/OpenDota account ID. The ID is stored only in current-user Windows QSettings, outside the repository, and is read by bootstrap only after the next app restart. Personal history remains all-time and role-unknown. `DOTA_SUPPORT_ACCOUNT_ID` remains a higher-priority development/CI override. This setting does not store Tokens, cookies, or Steam credentials.

DOTA-013 adds manual context for each allied hero's team position and planned lane. It is an explicit draft note, defaults to Unknown, is not persistent, and is displayed as neither statistical lane-fit nor auto-detected data. It does not alter scores, providers, pair refresh requests, or cache behavior.

DOTA-014 adds manual-draft action guardrails: a local status display shows the five-slot ally/enemy limits, the current unrestricted ban count, and the next recoverable action. Disabled or invalid add/remove/reset interactions leave the draft unchanged and do not schedule pair evidence work. Valid draft mutations retain the existing asynchronous refresh behavior.

DOTA-015 adds local candidate-table sorting. Click a table heading to sort its displayed Hero, experimental evidence, or explanation values; click again to reverse it. Unavailable evidence is always displayed after available evidence. The sort indicator is display order only: it does not change recommendation evidence, scores, pair shortlists, or data requests.

DOTA-018 improves the draft window's local readability with a resizable vertical content area for the manual composition context, candidate table, and selected-candidate explanation. These are scrollable presentation areas only: resizing or moving their divider does not change draft state, request pair evidence, or alter recommendation data.

DOTA-020 adds local candidate-filter feedback and a one-click search clear action. The candidate area shows the displayed/legal count, text filter, and display sort; these controls only change local presentation and never alter recommendation evidence, pair shortlists, or requests.

DOTA-022 structures the selected-candidate explanation into Candidate, recommendation summary, Evidence, Why/availability, and Context sections. It presents already calculated values only; its experimental ordering score remains an explanation rather than a win prediction, and it never requests new data.

DOTA-027 adds a local candidate-comparison panel. Add up to three current legal candidates to compare their already calculated score, confidence, and Meta/Counter/Synergy/Personal evidence. Adding, removing, clearing, searching, sorting, and selecting candidates are display-only operations: they do not request pair evidence or change recommendations. A compared hero is removed automatically if a draft change makes it illegal; the experimental score remains an ordering explanation, not a win prediction.

DOTA-031 improves keyboard access to the local candidate display: `Ctrl+F` focuses search, `Escape` clears it while search is focused, `Enter` moves to the candidate table, and arrow keys move the table selection. These controls only filter or select already calculated candidates; they never add picks/bans, request data, or change recommendation evidence.

DOTA-033 adds an explicit manual draft-import flow for pasted `MANUAL_IMPORT/v1` JSON only. It is a low-frequency, default-collapsed panel: choose `Show import` before pasting. DOTA-034 adds `Insert template` (current patch/P4-P5 role, empty hero arrays) and `Clear import text`; both only edit local text and invalidate previews. Validate/Preview never changes the current draft; Cancel remains inert; only Confirm atomically replaces picks, bans, and P4/P5 role. The v1 input has no ally position/lane fields, so confirmation clearly warns and clears existing manual ally context. This is not file input, GSI, auto-detection, or a network source.

DOTA-035 adds `Copy current draft summary`. It writes a concise local manual-draft summary to the system clipboard only after the user clicks it; it contains patch, intended role, picks, bans, and any explicit ally context—never Tokens, player accounts, recommendation data, import JSON, or provider data.

DOTA-036 adds explicit local JSON file actions inside the collapsed import panel. `Export current draft JSON` writes only `MANUAL_IMPORT/v1` fields with `observed_at: "unknown"`; `Choose JSON import file` only fills the editor and still requires Validate/Preview and Confirm. No paths are remembered, scanned, watched, or transmitted.

DOTA-037 gives rejected manual imports safe repair guidance: JSON syntax reports line/column; schema, patch, role, timestamp, and hero-list problems report a field and next action; hero errors may show only the numeric ID. It never echoes pasted text, paths, Tokens, accounts, or provider details.

## Windows local Token launch

From the project root, run:

```powershell
cd 'C:\Users\22908\Documents\ChatGPT\野生dota+\dota-support-draft'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_dota_support_draft.ps1
```

The `Bypass` option applies only to this launch process; it does not change your computer's execution policy. When the local terminal prompts, paste the Token into its hidden input. Never paste it into chat or commit it to the repository. The existing `python -m dota_support_draft` command remains available for development without this launcher.

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
