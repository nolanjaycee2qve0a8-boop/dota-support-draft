# Architecture

```text
Providers → Normalization → Repository → Domain → Draft Engine → Personal Model → Scoring → UI
```

Providers own transport DTOs and provider metadata. Normalization produces provider-neutral domain objects before repository or scoring code sees them. Repositories cache normalized objects locally in SQLite. The scoring engine only receives `DraftState` plus normalized, patch-aligned statistics.

DOTA-004 adds `STRATZ GraphQL transport → provider capability gate → position-aware EvidenceSet → ExperimentalEvidenceScoringEngine → UI`. STRATZ never leaks raw GraphQL dictionaries into domain/UI code, and OpenDota remains independent. `EvidenceSet` is preloaded/cached data, so candidate ranking is local and does not trigger request fan-out from UI clicks.

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
