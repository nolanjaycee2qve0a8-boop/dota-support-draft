# Experimental recommendation evidence

DOTA-004 introduces a provider-neutral evidence model: `RoleMetaEvidence`, `CounterEvidence`, and `SynergyEvidence`. Each carries hero IDs, its explicit P4/P5 role, patch, optional rank bracket, sample count, metric, and provenance. `EvidenceSet` is preloaded data only: scoring it is local and never calls a provider.

## Confidence and score

Sample confidence is `n / (n + 100)`. It is 0.5 at 100 matches and approaches, but never reaches, 1. This deliberately gives a three-match result much less authority than a large sample.

The V0 experimental weights are centralized in `ExperimentalWeights`: meta 25%, counter 30%, synergy 25%, familiarity 20%. A component value is a sample-confidence-adjusted win-rate advantage over 50%; counter and synergy aggregate the weighted mean across all known enemies/allies. One extreme pair cannot replace the aggregate.

Available components are renormalized to their available weights. Missing evidence is neutral, never strongly negative, and adds an explicit unavailable reason. The rendered **Experimental Score** is `clamp(0, 100, 50 + weighted_advantage * 100)`. It is an internal ordering score, not a win probability or calibrated forecast.

Personal OpenDota history remains all-time and role unknown. It contributes only cautious familiarity: a 25-match confidence curve, a small experience term, and a heavily reduced win-rate term. It is never called P4/P5 performance or current-patch performance.

## Degradation and request budget

No STRATZ token, transport error, schema error, or unresolved patch makes manual drafting fail. The UI remains in legal/familiarity candidate mode and shows an explicit unavailable message with no synthetic experimental scores. Existing startup work stays on the R5 background worker; normal table refreshes run only pure local scoring.

The present verified capability gate issues **zero** STRATZ requests per candidate/draft update. When a schema-verified operation is enabled, it must be a bounded batch/preload rather than candidate × ally/enemy calls; the provider transport/cache boundary and `EvidenceSet` exist to enforce that design.
