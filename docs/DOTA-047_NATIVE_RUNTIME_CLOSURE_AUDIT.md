# DOTA-047 — Windows PySide6 native-dependency closure audit

**Audit date: 2026-09-07.** This is Route A from [DOTA-042](DOTA-042_ONEDIR_RUNTIME_RESEARCH.md). It creates no EXE, onedir directory, installer, lock file, build script, or application change. It does not use a Token, account, application/provider HTTP request, PATH change, copied DLL, Qt SDK/IDE, Poppler/Codex runtime, or System32 dependency as a workaround. The one package-install attempt described below is the separately authorized official-PyPI audit download.

## Decision

**Route A has insufficient closure evidence. New build remediation is not approved.**

The one authorized installation attempt in a new dedicated Windows x64 audit venv did not reach a `Successfully installed` result and left neither `PySide6` nor `PyInstaller` importable. Therefore this audit has no installed-wheel manifest, no PE import table, and no restricted `import PySide6.QtCore` observation for the exact environment. It must not turn an absence of new evidence into a different version choice, a new download attempt, or an onedir build.

The precise stop condition is: **the exact official wheel artifacts were not available in the isolated audit environment for inspection.** The missing evidence is the current artifact hashes, installed layouts, PE imports, and proof that every non-system DLL has an official lock-managed source.

## Environment and source provenance

| Input | Required value | This audit | Provenance / hash | Classification |
| --- | --- | --- | --- | --- |
| CPython | 3.14.6 x64 | `Python 3.14.6` observed in a new, dedicated venv. | [Official Python 3.14.6 release page](https://www.python.org/downloads/release/python-3146/), accessed 2026-09-07. No Python distribution was downloaded in this audit, so no local artifact hash exists. | Engineering observation + official source. |
| PySide6 | 6.11.2 | Official PyPI resolver selected `pyside6-6.11.2-cp310-abi3-win_amd64.whl`; installation did not complete. | [Official PyPI JSON](https://pypi.org/pypi/PySide6/6.11.2/json), catalog SHA-256 `3201d67e3c10be2eaedd3910ff0f02351eca7e88c95a291cde5e7f2f55ef207f`, accessed 2026-09-07. No local wheel remained to verify against that hash. | Official metadata; local artifact absent. |
| PySide6 family | `PySide6_Essentials`, `PySide6_Addons`, `shiboken6` all 6.11.2 | Resolver requested all three exact versions; Addons download did not complete. | [PySide6 official metadata](https://pypi.org/pypi/PySide6/6.11.2/json) declares these exact requirements. No artifact/hash was materialized locally. | Official metadata; local artifact absent. |
| PyInstaller | 6.22.2 | Resolver selected 6.22.2; installation did not complete. | [Official PyPI JSON](https://pypi.org/pypi/PyInstaller/6.22.2/json), accessed 2026-09-07. No local wheel/hash was materialized. | Official metadata; local artifact absent. |

PySide6's official metadata states that the package is the alias for the Essentials and Addons wheels and declares the exact 6.11.2 family requirements. PyInstaller's official 6.22.2 metadata declares Windows support and Python 3.14 support. Those facts establish version availability metadata; they do **not** establish an installed Windows native-DLL closure.

## Controlled audit record

1. Created a new dedicated venv outside the repository and project `.venv`, using the locally available CPython 3.14.6. No project venv, global Python, PATH, registry, system DLL, Qt SDK, or user setting was modified.
2. Per the explicit authorization, made one `pip install` attempt with only `PySide6==6.11.2` and `PyInstaller==6.22.2`, using the official PyPI simple index and no cache.
3. Resolver output identified the expected PySide6 family and PyInstaller transitive package names. The output stopped while downloading `PySide6_Addons`; it did not report successful installation or a specific package-manager error.
4. A single read-only check then found no installed `PySide6` or `PyInstaller` modules. No retry was made. No wheel cache or bundle was used as substitute evidence.

This is an **engineering observation**, not an assertion about PyPI availability or a diagnosis of the interrupted download. The audit does not know why the attempt did not complete.

## Native closure evidence table

The table intentionally distinguishes current facts from DOTA-026 history. “Absent from audit” means no wheel was installed for inspection, not that the upstream wheel lacks the file.

| Consumer / candidate dependency | Current installed layout | Current PE-import evidence | Official wheel/source + hash | Closure result |
| --- | --- | --- | --- | --- |
| `PySide6/QtCore.pyd` | Absent from audit. | Not inspected; no PE tool or installed `pefile` dependency became available. | No local exact wheel artifact. | **Unknown / blocked.** |
| `PySide6/Qt6Core.dll` | Absent from audit. | Not inspected. | No local `PySide6_Essentials` artifact. | **Unknown / blocked.** |
| ICU dependency of `Qt6Core.dll` | Absent from audit. | Not inspected in this audit. | No local Qt wheel artifact. | **Unknown / blocked.** |
| PyInstaller Windows bootloader | Absent from audit. | Not inspected. | No local PyInstaller wheel artifact. | **Unknown / blocked.** |

### Historical context, not a replacement for this audit

[DOTA-026](DOTA-026_PYSIDE_WHEEL_ICU_GATE.md) recorded a prior isolated inspection of the same 6.11.2 Windows wheel: `Qt6Core.dll` imported `icuuc.dll`, while the wheel contained no `icu*.dll`. That remains a repository historical observation and a reason to require closure proof. It is **not** a fresh DOTA-047 PE result, an official root-cause statement, or permission to obtain ICU from a host machine.

## Source labels and unresolved questions

| Label | Fact | Consequence |
| --- | --- | --- |
| Official confirmation | Python.org publishes the requested 3.14.6 release; PyPI metadata lists PySide6 6.11.2 Windows x64 and its exact family requirements; PyInstaller 6.22.2 metadata supports Python 3.14. | The exact version tuple is a legitimate audit target, not a portable runtime approval. |
| Engineering observation | The one isolated installation attempt did not complete and installed neither target package. | No current manifest/layout/PE/import evidence exists. |
| Unknown | Which non-system DLLs the exact installed wheels import; whether each has an official, hash-lockable source; whether a no-workaround QtCore import succeeds. | Do not build or remediate. |

## Non-skippable admission gate

Any future build-remediation proposal needs a new explicit authorization and must first provide all of the following in a fresh isolated environment:

1. Downloaded official Windows x64 wheel artifacts for CPython 3.14.6 / PySide6 family 6.11.2 / PyInstaller 6.22.2, each with a locally calculated SHA-256 matching the official distribution metadata.
2. Installed-layout manifests and PE import tables for every non-system consumer/dependency edge, including `QtCore.pyd`, `Qt6Core.dll`, any ICU dependency, and the PyInstaller bootloader.
3. A provenance table mapping every non-system DLL to a lock-managed official source. PATH changes, `add_dll_directory`, System32, SDK/IDE, Poppler/Codex runtime, and manual DLL copies cannot satisfy an edge.
4. A no-workaround isolated `import PySide6.QtCore` test. Only after this closure gate may a separately authorized task consider any onedir build, plugin, close, or writable-data-root acceptance.

## Temporary environment cleanup

The dedicated directory for this attempt was `C:\Users\22908\Documents\ChatGPT\野生dota+\dota-047-native-audit-20260907-r2`. It contained only the audit venv created for this task and was deleted before this documentation commit. No project, user configuration, package cache, or prior audit directory was deleted.
