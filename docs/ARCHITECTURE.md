# Architecture

```text
Providers → Normalization → Repository → Domain → Draft Engine → Personal Model → Scoring → UI
```

Providers own transport DTOs and provider metadata. Normalization produces provider-neutral domain objects before repository or scoring code sees them. Repositories cache normalized objects locally in SQLite. The scoring engine only receives `DraftState` plus normalized, patch-aligned statistics.

DOTA-004 adds `STRATZ GraphQL transport → provider capability gate → P4/P5 RoleEvidenceBundles → position-aware EvidenceSet → ExperimentalEvidenceScoringEngine → UI`. STRATZ never leaks raw GraphQL dictionaries into domain/UI code, and OpenDota remains independent. Role switching selects a local immutable bundle and does not invoke the provider. `EvidenceSet` is preloaded/cached data, so candidate ranking is local and does not trigger request fan-out from UI clicks.

The manual UI refreshes immediately after a checked P4/P5 radio change, selecting only that role's local bundle. This preserves the Qt responsiveness boundary because refresh performs pure local presentation/scoring work.

DOTA-004R2's live branch is `STRATZ current-week role-meta batch → immutable P4/P5 bundles → local scoring`. Bootstrap makes at most two role-meta requests plus a freshness diagnostic. `laneOutcome` is provider capability only: aliases batch at most eight candidate profiles, cache independently of selected draft picks, and is not fetched from UI mutations. DOTA-005 owns asynchronous draft-dependent pair refresh orchestration.

DOTA-005 implements that boundary as `DraftMainWindow → PairEvidenceRefreshController → QTimer (250 ms) → dedicated QThread worker → DraftPairEvidenceService → STRATZ → queued GUI result`. The controller permits one active worker and one replaceable newest pending snapshot. Results must match both generation and semantic draft context before the GUI atomically replaces its context-keyed Counter/Synergy overlay.

DOTA-006 renders that existing semantic context locally in the window: current P4/P5 role, allied/enemy counts, the deterministic pair shortlist, and explicit Counter/Synergy availability. The rendered context is derived from the same current `PairEvidenceInput`; it does not schedule work, fetch data, or preserve a stale overlay after a draft change.

DOTA-007 adds one user-triggered `refresh_now` entry to the same controller. It assigns a new generation to the current `PairEvidenceInput`, dispatches immediately only when no worker is active, and otherwise replaces the single pending snapshot. It neither bypasses provider caches nor creates a parallel worker; shutdown clears this manual pending work together with ordinary pending work.

DOTA-008's selected-candidate explanation panel consumes the already rendered local `CandidateRow`. It retains a candidate selection across a local rerender only when that hero remains legal and visible; otherwise it shows an explicit empty state. It has no provider or controller dependency: table selection, search, role changes, pair-result overlays, and reset only rerender local presentation data.

DOTA-013 stores manual ally team-position and planned-lane values in `ManualDraftSession` and immutable `DraftState` only. They are not part of `PairEvidenceContext`, so assignment edits do not create a worker, alter the current-week pair query, or invalidate its bounded request/cache contract. The composition panel renders local manual/Unknown/conflict context; it is not a statistical lane-fit or auto-detection feature.

DOTA-014 keeps manual draft actions at the same local boundary. The UI derives ally/enemy capacity and the unrestricted ban count from `ManualDraftSession`, and exposes a separate recoverable-action status without replacing bootstrap, player, or pair diagnostics. Only a successful `ManualDraftSession` mutation rerenders and calls the pair controller; disabled, unselected, capacity-full, or validation-failed actions do not create a worker or provider request.

DOTA-015 adds a local `CandidateSortColumn` display-order boundary after candidate rows have been built and filtered. It sorts typed `CandidateRow` numeric fields and evidence components rather than rendered strings; unavailable numeric values remain last for both directions, and stable ties retain the default recommendation order. Sorting neither changes the canonical candidate sequence passed to pair shortlist construction nor calls the pair controller.

DOTA-018 places the local composition context, candidate table, and selected-candidate explanation in a vertical Qt splitter. The composition and explanation text edits remain read-only and scrollable; divider movement and window resizing are strictly presentation operations with no dependency on the draft session, pair controller, provider, or scoring engine.

DOTA-020 derives the candidate result count, text-filter state, and typed display-sort description from the same local filtered `CandidateRow` sequence used to render the table. Clearing the search only emits the existing local text-change rerender; searching, clearing, sorting, and selection do not call the pair controller or any provider.

DOTA-022 formats the existing selected `CandidateRow` into structured read-only text within the same explanation widget. The formatting escapes dynamic display text and preserves the score disclaimer plus unavailable/neutral-zero component wording; it has no provider, scorer, or controller dependency.

DOTA-027 adds a local ordered comparison selection after `CandidateRow` values are built. The panel keeps at most three legal hero IDs, maps them to the current unfiltered local candidate rows, and prunes IDs after every rerender when draft changes make a candidate illegal. It displays the current role, score disclaimer, confidence, and component availability from those existing rows. Selection, add/remove/clear, filtering, sorting, and table interactions neither schedule pair work nor call a provider; role and pair-overlay rerenders only update local display values.

DOTA-031 adds keyboard focus handling only at that same local presentation boundary. `Ctrl+F` focuses the candidate search, search-scoped `Escape` clears it, and `Enter` moves focus to a visible candidate row for native arrow-key selection. A rerender preserves search focus, or table focus when a visible row remains, without invoking the pair controller. No keyboard shortcut invokes a draft mutation.

DOTA-032 locks this presentation boundary with one offscreen Qt regression matrix. Search/clear, sorting, table selection, comparison controls, keyboard focus/navigation, and explanation rerenders may change only local display, selection, comparison, or focus state. The matrix asserts that each leaves `DraftState`, canonical pair shortlist context, displayed score/evidence values, pair generation, worker count, and fake pair-service calls unchanged.

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
