# Development

This is a `src/` layout project: `python -m dota_support_draft` needs an editable install (recommended) or `PYTHONPATH=src`; pytest's test-only path setting is not a runtime installation.

```powershell
cd 'C:\Users\22908\Documents\ChatGPT\野生dota+\dota-support-draft'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m dota_support_draft
```

Use the desktop `Configure Player` action to save a public numeric Steam32/OpenDota account ID locally. On Windows it is stored in current-user QSettings, never in the workspace; restart the app before bootstrap loads or removes Personal history. The environment variable `DOTA_SUPPORT_ACCOUNT_ID` remains an optional higher-priority development/CI override. Personal values are all-time history with unknown role. Set `STRATZ_API_TOKEN` only through the local launcher or your local environment; it must never be committed. An optional `STRATZ_RANK_BRACKET` is preserved as scope, never inferred.

Named manual draft snapshots also use current-user QSettings, outside the workspace. They are local-only and stored only after an explicit Save click; they contain a name plus draft patch/role/pick/ban IDs, never a Token, account, evidence, cache, provider data, path, manual ally context, or history. Snapshot metadata is not applied automatically at startup; Preview then Confirm is required to load it.

`STRATZ_RANK_BRACKET` accepts basic STRATZ values or fine values that map explicitly to their basic bucket. For an interactive live-only check, set the token locally and run `./.venv/Scripts/python.exe -m dota_support_draft.stratz_smoke`; never add the token or response payload to the repository.

For desktop validation, launch the app with a local STRATZ token, rapidly add/remove allies or enemies, and verify that the interface remains responsive while pair status progresses through updating/ready/partial/error. Shutdown is cooperative: pending/debounced work is cancelled, while an already-running synchronous HTTP call can finish before its worker thread exits.
