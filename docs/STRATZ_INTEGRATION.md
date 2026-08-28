# STRATZ integration

This milestone uses the official `https://api.stratz.com/graphql` GraphQL endpoint. The live authenticated contract was manually verified for current-week position stats, game versions, and lane outcomes. This document distinguishes that contract from unverified global/reference operations.

- Endpoint: `https://api.stratz.com/graphql` (official GraphQL Explorer).
- Transport: POST JSON body, `User-Agent: DotaSupportDraft/0.1`; an Authorization header is added only when `STRATZ_API_TOKEN` is non-empty, as `Bearer <token>`.
- The code maps 401/403 to explicit authentication failure and 429 to rate-limit failure; no token is persisted or emitted.
- Hero identity: Dota numeric hero ID, normalized against OpenDota's catalog.
- Positions: only `POSITION_4` and `POSITION_5` are accepted as distinct domain roles. Generic `Support` is never converted to either position.
- Rank scope: optional `STRATZ_RANK_BRACKET`; unset means no bracket is claimed. It is never displayed as a specific bracket.

Cache keys are SHA-256 hashes of operation variables only. The authorization token is neither a key component nor written to disk. Expired data is not silently returned as fresh.

## Schema probe

Run `python -m dota_support_draft.stratz_schema_probe` only after configuring `STRATZ_API_TOKEN` in the interactive environment. Phase 1 first asks `__schema` for the server's actual query-root name, then probes that name through a GraphQL variable—there is no `Query`/`DotaQuery` fallback or hardcode. It prints relevant fields (including `constants`) with six fixed `ofType` wrapper levels. Phase 2 uses a bounded breadth-first traversal of reachable relevant named input/object types: at most 12 type probes, depth 3, and 14 fields per type; duplicate names are queried once. It uses normal transport/error mapping, never prints the token, and neither persists nor dumps the schema response. A missing or malformed root name is a probe failure. Its output must be reviewed before adding any production role/meta/pair query.

## DOTA-004R2 production contract

The verified root is `DotaQuery`. Current-week role meta uses `dota.heroStats.stats` with a single candidate-ID batch, `groupByTime:false`, `groupByPosition:true`, and `groupByBracket:false`; omitted `week` means STRATZ current week. Returned week is opaque, and `time` has no calendar meaning. `POSITION_4` and `POSITION_5` map directly, while fine rank input maps to `RankBracketBasicEnum` (`HERALD/GUARDIAN`, `CRUSADER/ARCHON`, `LEGEND/ANCIENT`, `DIVINE/IMMORTAL`). Empty rank omits the filter; `ALL` and `FILTERED` are rejected.

Current-week evidence is never called current-patch or patch-isolated. `constants.gameVersions` is a separately cached six-hour freshness diagnostic: catalog lag warns but never blocks current-week statistics. Role-meta and raw lane profiles have a 45-minute TTL. Pair evidence uses alias-batched `laneOutcome` (maximum eight candidates per request) and locally filters allies/enemies; global `matchUp` is position-unfiltered reference data and is excluded from P4/P5 scoring.

DOTA-005 invokes `laneOutcome` only for the event-driven top-eight shortlist. A cold refresh with both polarities is bounded to one role-meta, one friendly profile, and one against profile request (three maximum); selecting different related heroes with the same role/rank/shortlist reuses cached profiles without extra transport calls. There is no periodic polling.
