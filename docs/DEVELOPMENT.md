# Development

This is a `src/` layout project: `python -m dota_support_draft` needs an editable install (recommended) or `PYTHONPATH=src`; pytest's test-only path setting is not a runtime installation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:DOTA_SUPPORT_ACCOUNT_ID = "<steam32-id>" # optional
.\.venv\Scripts\python.exe -m dota_support_draft
```

Without verified STRATZ evidence, the workspace presents legal manual candidates rather than experimental scores. Personal values are all-time history with unknown role. Set `STRATZ_API_TOKEN` only in your local environment; it must never be committed. An optional `STRATZ_RANK_BRACKET` is preserved as scope, never inferred.

`STRATZ_RANK_BRACKET` accepts basic STRATZ values or fine values that map explicitly to their basic bucket. For an interactive live-only check, set the token locally and run `./.venv/Scripts/python.exe -m dota_support_draft.stratz_smoke`; never add the token or response payload to the repository.
