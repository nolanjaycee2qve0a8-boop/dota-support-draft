# Project State

## Product

Dota Support Draft Assistant is a personal Windows Dota 2 draft assistant for explainable Position 4 and Position 5 hero selection.

Its architecture is intentionally layered:

```text
Providers → Normalization → Domain → Draft / Scoring → UI
```

## Closed milestones

| Milestone | Main commit |
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

DOTA-005 was merged to `main` at `46f978a` (`DOTA-005: async pair evidence refresh (#4)`). DOTA-006 was merged at `8f71ebc` with observable pair refresh context and the Qt worker-retirement fix. DOTA-007 was merged at `6c55551` with manual pair refresh. DOTA-008 was merged at `8f971f1` with the selected recommendation explanation. DOTA-009 was merged at `48d4ab1` with the local Windows Token launcher.

DOTA-005 through DOTA-009 are closed. There is no active product implementation task.

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
- Tokens are local-only, temporary configuration and never enter the repository.
