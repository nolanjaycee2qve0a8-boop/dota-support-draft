# Development

This is a `src/` layout project: `python -m dota_support_draft` needs an editable install (recommended) or `PYTHONPATH=src`; pytest's test-only path setting is not a runtime installation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:DOTA_SUPPORT_ACCOUNT_ID = "<steam32-id>" # optional
.\.venv\Scripts\python.exe -m dota_support_draft
```

The workspace presents legal manual candidates, not recommendations. Personal values are all-time history with unknown role.
