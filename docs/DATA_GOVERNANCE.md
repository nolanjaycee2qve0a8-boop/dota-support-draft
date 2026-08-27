# Data governance

Formal statistics carry `DataProvenance`: provider, retrieval time, source scope, patch context, optional sample size, and source reference. Patch identity is checked against `DraftState` before a role statistic is scored.

- `REAL` means externally retrieved data with recorded provenance.
- `TEST/FIXTURE` is test-only synthetic data and may never be presented as live data.
- `MANUAL` is explicitly curated input, including capability assessments.
- `UNKNOWN / UNAVAILABLE` marks an explicitly withheld provider capability; it is not a real statistic.

Provider-specific payloads remain in adapter DTOs. Sample size and provenance support future confidence handling; they must not be silently discarded.

`patch_version = None` explicitly means the evidence is not patch-specific, such as OpenDota all-time player hero totals; it must never be replaced with the current application patch.

DOTA-004 `RoleMetaEvidence`, `CounterEvidence`, and `SynergyEvidence` additionally preserve an explicit intended P4/P5 role and optional rank scope. They may be used only when the provider actually classified/filtered that role and the patch has been cross-provider reconciled.

Pair win rate is descriptive pair data, not automatically a matchup/synergy effect. Only an explicitly documented and provenance-bearing `effect` can enter recommendation scoring. P4 and P5 data are stored in separate immutable `RoleEvidenceBundle` instances; cross-role reuse is invalid.
