# DOTA-004 — Position-aware draft evidence engine

Completed scope: provider-neutral position-aware evidence objects; conservative sample confidence; explainable 0–100 experimental ranking; cache-safe synchronous GraphQL transport; current-week STRATZ P4/P5 data capability; and candidate-table support for evidence-backed rows.

No real statistic is substituted with fixture data. With no token, STRATZ remains unavailable and manual drafting still works. See `docs/STRATZ_INTEGRATION.md` for the exact boundary and `docs/RECOMMENDATION_EVIDENCE.md` for scoring.

DOTA-004R1 separates immutable P4/P5 evidence bundles, fixes fixed-weight and sample-shrunk recommendation semantics, prevents familiarity-only scores, and adds an opt-in compact schema probe. Draft-dependent pair evidence remains unavailable until the probe verifies a bounded, position-aware live contract.

DOTA-004R1.1 closes immediate role-switch refresh, zero-sample pair, and zero-public-weight edge cases. The schema probe now prints compact bounded root/type signatures but does not enable any live production capability.

DOTA-004R1.2 deepens the introspection type-reference selection and makes bounded type discovery multi-hop. It remains probe-only and does not authorize production query implementation.

DOTA-004R1.3 discovers the actual GraphQL query-root name before probing its fields, fixing STRATZ's `DotaQuery` root without hardcoding it.

DOTA-004R2 enables verified current-week STRATZ P4/P5 role meta, a non-blocking gameVersion freshness diagnostic, and bounded position-filtered `laneOutcome` provider methods. Current-week is not current-patch: it preserves opaque STRATZ week/rank/role scope. Pair effects are same-week baseline-adjusted and not bootstrapped or asynchronously refreshed; that UI orchestration remains DOTA-005.

Non-goals remain GSI, OCR, overlays, process access, game automation, ML, and calibrated win probabilities.
