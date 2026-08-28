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

`main` is currently `46f978a` (`DOTA-005: async pair evidence refresh (#4)`). DOTA-005 is closed and there is no active product implementation task.

DOTA-005 was verified with a 250 ms debounce, background `QThread` pair evidence refresh, latest-state-wins scheduling, a bounded top-8 shortlist, at most three cold requests, cooperative deferred shutdown, 146 tests, and Windows live validation.

## Durable semantics

- Position 4 and Position 5 remain distinct evidence and presentation contexts.
- STRATZ evidence is current-week data, not patch-isolated data.
- OpenDota personal totals are all-time and role-unknown.
- Experimental scoring is explanatory evidence, not a win-rate prediction.
- Pair effects do not change the established scoring formula.
- Tokens are local-only configuration and never enter the repository.
