# Project State

## Product

Dota Support Draft Assistant is a personal Windows Dota 2 draft assistant for explainable Position 4 and Position 5 hero selection.

Its architecture is intentionally layered:

```text
Providers → Normalization → Domain → Draft / Scoring → UI
```

## Closed milestones

| Milestone | Main commit / release status |
| --- | --- |
| DOTA-001 | `55f3df0` |
| DOTA-002 | `8517fd0` |
| DOTA-003 | `30a7ac7` |
| DOTA-004 | `e2a6c0a` |
| DOTA-005 | `46f978a` |
| DOTA-006 | `8f71ebc` |
| DOTA-007 | `6c55551` |
| DOTA-008 | `8f971f1` |
| DOTA-009 | `48d4ab1` |
| DOTA-010 | `9cf4e0b` (management-state sync, PR #10) |
| DOTA-011 | `6cb149d` (local player profile configuration, PR #11) |
| DOTA-012 | `8532745` (composition/lane-fit research, PR #12) |
| DOTA-013 | `8532745` (manual ally position/planned-lane context, PR #12) |
| DOTA-014 | `8532745` (draft-action guardrails, PR #12) |
| DOTA-015 | `8532745` (typed local candidate display sorting, PR #12) |
| DOTA-016 | `8532745` (lane-fit provider gate research, PR #12) |
| DOTA-017 | Local pre-merge integration validation only; no standalone release |
| DOTA-018 | `14f3c3a` (draft layout readability, PR #13) |
| DOTA-019 | `48f4c05` (durable management-state sync, PR #14) |
| DOTA-020 | `2090778` (candidate filter clarity, PR #15) |
| DOTA-021 | `6391e74` (Qt workflow regression, PR #17) |
| DOTA-022 | `ebd5e38` (candidate evidence readability, PR #16) |

DOTA-005 was merged to `main` at `46f978a` (`DOTA-005: async pair evidence refresh (#4)`). DOTA-006 was merged at `8f71ebc` with observable pair refresh context and the Qt worker-retirement fix. DOTA-007 was merged at `6c55551` with manual pair refresh. DOTA-008 was merged at `8f971f1` with the selected recommendation explanation. DOTA-009 was merged at `48d4ab1` with the local Windows Token launcher. DOTA-010 and DOTA-011 were merged through PRs #10 and #11. PR #12 merged DOTA-012 research, DOTA-013 manual context, DOTA-014 guardrails, DOTA-015 local sorting, and DOTA-016 research/gate together. DOTA-017 was the local integration candidate used to validate that set before its merge; it is not a separately released product milestone. DOTA-018 was merged through PR #13 at `14f3c3a`.

DOTA-019 synchronized post-merge management state. DOTA-020 added local candidate-filter visibility and clearing. DOTA-021 added the offscreen Qt workflow regression. DOTA-022 was merged through PR #16 at `ebd5e38` with the structured candidate-evidence panel; DOTA-021 was merged through PR #17 at `6391e74`. DOTA-001 through DOTA-022 are closed. There is no active product implementation task.

The pair-refresh milestones were verified with a 250 ms debounce, background `QThread` pair evidence refresh, latest-state-wins scheduling, a bounded top-8 shortlist, at most three cold requests, and cooperative deferred shutdown with safe worker/thread retirement. The local Windows launcher accepts a Token only through hidden terminal input for the launch process; it is temporary and never enters the repository.

## Durable semantics

- Position 4 and Position 5 remain distinct evidence and presentation contexts.
- STRATZ evidence is current-week data, not patch-isolated data.
- OpenDota personal totals are all-time and role-unknown.
- Experimental scoring is explanatory evidence, not a win-rate prediction.
- Pair effects do not change the established scoring formula.
- Manual pair refresh recalculates the current context through existing caches; it does not promise a new HTTP transport request.
- Pair workers close cooperatively and retire safely; shutdown never dispatches pending refresh work.
- The selected recommendation explanation consumes already calculated local evidence and makes no network request.
- The public numeric Steam32/OpenDota account ID is current-user local configuration, read on the next bootstrap; `DOTA_SUPPORT_ACCOUNT_ID` remains the higher-priority override. Personal history is all-time and role-unknown.
- Tokens are temporary local launch configuration and never enter the repository.
- Manual ally team-position/planned-lane values are local, non-persistent draft context. Unknown is valid; this context is neither auto-detected nor statistical lane-fit, does not affect scores, and does not schedule pair work.
- Manual draft guardrails preserve five ally/enemy slots and an unrestricted ban count. Invalid or no-op draft actions do not dispatch pair refresh work.
- Candidate-table sorting is typed local display order only. It cannot change scores, pair shortlists, requests, or cache behavior.
- The composition context, candidate table, and explanation are read-only/scrollable presentation areas in a local splitter; resizing them does not modify draft or pair state.
- The lane-fit/provider evidence gate remains closed: no statistical lane-fit value, recommendation effect, or provider capability claim is implemented or approved.
- Windows packaging is not yet a release capability. DOTA-023 records the conditional local-onedir gate; no installer, signed binary, or distributed executable is confirmed.
