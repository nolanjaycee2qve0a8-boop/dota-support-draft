# DOTA-005 — Async draft-dependent pair evidence refresh

Completed scope: event-driven manual-draft pair enrichment for a deterministic top-eight preliminary shortlist. `DraftPairEvidenceService` is synchronous and provider-neutral; Qt is isolated in a dedicated debounced controller and worker thread.

Each semantic draft change immediately rerenders local Meta/Personal recommendations and schedules a 250 ms pair refresh when related picks exist. A stable context includes patch, role, ordered ally/enemy IDs, shortlist IDs, and rank scope. At most one worker is active and only the newest pending snapshot survives. In-flight HTTP is cooperative rather than forcibly cancelled; stale completed results are discarded.

Only matching, current contexts atomically replace the Counter/Synergy overlay. Partial failures retain the successful polarity; complete failures preserve Meta/Familiarity. Search and table selection remain presentation-only and issue no pair work. There is no polling, GSI, OCR, overlay, automation, or scoring-weight retuning.
