# Experimental recommendation evidence

DOTA-004 introduces a provider-neutral evidence model: `RoleMetaEvidence`, `CounterEvidence`, and `SynergyEvidence`. Each carries hero IDs, its explicit P4/P5 role, patch, optional rank bracket, sample count, metric, and provenance. `EvidenceSet` is preloaded data only: scoring it is local and never calls a provider.

## Confidence and score

Sample confidence is `n / (n + 100)`. It is 0.5 at 100 matches and approaches, but never reaches, 1. This deliberately gives a three-match result much less authority than a large sample.

The V0 experimental weights are centralized and must sum to 1.0: meta 25%, counter 30%, synergy 25%, familiarity 20%. Every public component is magnitude-shrunk by confidence. Meta is `(win_rate - 0.5) × confidence`. For pairs, the raw aggregate is the confidence-weighted mean of **verified provider effects**, then the aggregate is multiplied by its mean confidence. One extreme pair cannot replace the aggregate.

Missing components retain their configured weight and contribute neutral zero; weights are never redistributed. The rendered **Experimental Score** is `clamp(0, 100, 50 + Σ(fixed_weight × adjusted_effect) × 100)`. It is an internal ordering score, not a win probability or calibrated forecast. A candidate receives that score only if it has at least one applicable public P4/P5 component; familiarity alone cannot unlock recommendation mode.

Personal OpenDota history remains all-time and role unknown. It contributes only cautious familiarity: a 25-match confidence curve, a small experience term, and a heavily reduced win-rate term. It is never called P4/P5 performance or current-patch performance. Overall evidence confidence is the fixed-public-weight average of each public component's reliability × coverage, so meta-only evidence reports lower coverage than complete meta/counter/synergy evidence.

`CounterEvidence` and `SynergyEvidence` keep `pair_win_rate` separate from `effect`. A raw pair win rate is not promoted to an advantage by subtracting 50%; only a provider-supplied or defensibly baseline-adjusted `effect` is scoreable. Fixtures may provide explicit `TEST/FIXTURE` effects.

## Degradation and request budget

No STRATZ token, transport error, schema error, or unresolved patch makes manual drafting fail. The UI remains in legal/familiarity candidate mode and shows an explicit unavailable message with no synthetic experimental scores. Existing startup work stays on the R5 background worker; normal table refreshes run only pure local scoring.

`RoleEvidenceBundles` holds distinct immutable P4 and P5 evidence/error states. Switching roles only selects the local bundle; it performs no provider/network call and never reuses P4 data as P5 data. The present verified capability gate issues **zero** STRATZ requests per candidate/draft update. When a schema-verified operation is enabled, it must be a bounded batch/preload rather than candidate × ally/enemy calls.

R1.1 also excludes verified-effect pair rows with zero matches from aggregation, coverage, and score gating. They are unavailable evidence, not a zero-strength observation. Public weights must sum to 1.0 and retain at least one positive public component; evidence in a component configured with weight zero cannot unlock experimental recommendation mode.

## Current-week STRATZ scope

Evidence now has an explicit statistical scope: `CURRENT_WEEK`, `GAME_VERSION`, or `TEST_FIXTURE`. `CURRENT_WEEK` carries an opaque STRATZ week ID and no patch version. It can score only for its requested P4/P5 role; it is not rejected merely because OpenDota's current patch is newer than the STRATZ game-version catalog. Game-version evidence still requires an exact version match.

For `laneOutcome`, `isWith:true` becomes synergy and `isWith:false` becomes counter evidence. Its scored effect is the current-week, role/rank-compatible candidate conditional match win rate (`matchWinCount / matchCount`) minus that candidate's same-week role-meta win rate. Different weeks, absent baselines, rank incompatibility, and zero samples are unavailable rather than fabricated effects.

## Event-driven pair enrichment

Only the deterministic `pair-enhanced shortlist` (at most eight legal candidates) receives draft-dependent Counter/Synergy enrichment. It is selected from base role Meta plus personal familiarity using the public-evidence gate, never from prior pair values. All legal candidates remain visible; non-shortlisted candidates score with Meta/Personal and neutral missing pair weights.

Pair work is debounced for 250 ms and latest-state-wins. An in-flight urllib call may finish naturally, but its result is discarded unless its generation and role/allies/enemies/shortlist/rank context exactly match. Partial capability failure retains the successful polarity; complete pair failure falls back to current-week Meta and personal evidence.

## Pair refresh observability

The desktop UI shows the current semantic pair context locally: P4/P5 role, allied and enemy pick counts, and the deterministic ordered shortlist (at most eight heroes). It also distinguishes Counter and Synergy as available, pending, not requested, or unavailable with the reported component error. With no related picks, or while a component is missing, the UI explicitly identifies Meta/Personal-only presentation rather than treating missing pair evidence as zero. Search and candidate-table selection do not alter this context or start pair transport work.

`Refresh pair evidence` is an explicit retry/recalculation for that same current semantic context. It is disabled without a legal shortlist or related pick, uses the normal provider cache path, and does not claim to force a new HTTP transport request. When work is already active, repeated clicks replace only the latest pending snapshot; they never create a second active worker.

DOTA-030 adds a local Pair action status that turns the existing state and per-component coverage into next-step guidance. It identifies updating, available, partial, unavailable, no-related-pick, and no-service states; it keeps Meta/Personal explicitly available when pair evidence is absent. Its retry guidance refers only to the existing `Refresh pair evidence` action, which recalculates the current context through normal caches and does not force transport. The label itself schedules no work and does not expose raw failure details.
