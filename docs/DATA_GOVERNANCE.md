# Data governance

Formal statistics carry `DataProvenance`: provider, retrieval time, source scope, patch context, optional sample size, and source reference. Patch identity is checked against `DraftState` before a role statistic is scored.

- `REAL` means externally retrieved data with recorded provenance.
- `TEST/FIXTURE` is test-only synthetic data and may never be presented as live data.
- `MANUAL` is explicitly curated input, including capability assessments.

Provider-specific payloads remain in adapter DTOs. Sample size and provenance support future confidence handling; they must not be silently discarded.

