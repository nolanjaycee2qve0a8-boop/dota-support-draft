# Architecture

```text
Providers → Normalization → Repository → Domain → Draft Engine → Personal Model → Scoring → UI
```

Providers own transport DTOs and provider metadata. Normalization produces provider-neutral domain objects before repository or scoring code sees them. Repositories cache normalized objects locally in SQLite. The scoring engine only receives `DraftState` plus normalized, patch-aligned statistics.

DOTA-004 adds `STRATZ GraphQL transport → provider capability gate → P4/P5 RoleEvidenceBundles → position-aware EvidenceSet → ExperimentalEvidenceScoringEngine → UI`. STRATZ never leaks raw GraphQL dictionaries into domain/UI code, and OpenDota remains independent. Role switching selects a local immutable bundle and does not invoke the provider. `EvidenceSet` is preloaded/cached data, so candidate ranking is local and does not trigger request fan-out from UI clicks.

The manual UI refreshes immediately after a checked P4/P5 radio change, selecting only that role's local bundle. This preserves the Qt responsiveness boundary because refresh performs pure local presentation/scoring work.

DOTA-004R2's live branch is `STRATZ current-week role-meta batch → immutable P4/P5 bundles → local scoring`. Bootstrap makes at most two role-meta requests plus a freshness diagnostic. `laneOutcome` is provider capability only: aliases batch at most eight candidate profiles, cache independently of selected draft picks, and is not fetched from UI mutations. DOTA-005 owns asynchronous draft-dependent pair refresh orchestration.

DOTA-005 implements that boundary as `DraftMainWindow → PairEvidenceRefreshController → QTimer (250 ms) → dedicated QThread worker → DraftPairEvidenceService → STRATZ → queued GUI result`. The controller permits one active worker and one replaceable newest pending snapshot. Results must match both generation and semantic draft context before the GUI atomically replaces its context-keyed Counter/Synergy overlay.

For OpenDota, `HTTP transport → provider DTO/schema validation → normalization → domain + provenance → disk HTTP cache / SQLite` is the live read path. The raw disk cache is not a normalized repository.

```text
GSI ─────────────┐
Screen Recognition ├─> DraftStateCollector ─> DraftState
Manual Input ────┘
```

All collection methods share the same `DraftState` boundary. Nothing in scoring depends on whether a pick came from GSI, vision, or manual correction.

```text
Manual UI ───────┐
GSI (future) ────┼─> DraftState ─> Candidate Presenter / Recommendation Engine ─> Desktop UI
Vision (future) ─┘
```
