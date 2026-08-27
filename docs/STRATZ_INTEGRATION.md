# STRATZ integration

This milestone uses the official `https://api.stratz.com/graphql` GraphQL Explorer endpoint. STRATZ's public site describes its API as GraphQL and describes hero positions (Rank Roles), patch history, rank brackets, counters, and synergies. The public Explorer page was reachable during DOTA-004 research, but did not render schema documentation to an unauthenticated browser session; no local `STRATZ_API_TOKEN` was configured. This document therefore distinguishes verified public facts from capability gates.

- Endpoint: `https://api.stratz.com/graphql` (official GraphQL Explorer).
- Transport: POST JSON body, `User-Agent: DotaSupportDraft/0.1`; an Authorization header is added only when `STRATZ_API_TOKEN` is non-empty, as `Bearer <token>`.
- Authentication, current rate limits, enum spellings, `GameVersion` fields, and live schema output: **not live-verified in this checkout**. The code maps 401/403 to explicit authentication failure and 429 to rate-limit failure.
- Hero identity: Dota numeric hero ID, normalized against OpenDota's catalog.
- Positions: only `POSITION_4` and `POSITION_5` are accepted as distinct domain roles. Generic `Support` is never converted to either position.
- Rank scope: optional `STRATZ_RANK_BRACKET`; unset means no bracket is claimed. It is never displayed as a specific bracket.

The DTO normalizer records the currently documented `heroId`, `matchCount`, and `winCount` role-meta shape, but does not activate it as current-patch evidence until a live schema confirms both a game-version filter and its relationship to OpenDota's patch version. Pair matchups/synergy are also withheld because a role-aware, patch-aware pair query was not independently verified. This is intentional: a missing capability is safer than presenting rolling/global data as P4/P5 current-patch evidence.

`StratzProvider.resolve_patch` requires exactly one STRATZ game-version name equal to the OpenDota `Patch.version`; IDs are never assumed equal. Future schema verification may enable a bounded role-meta batch plus bounded pair operations. It must document operation name, variables, returned fields, rate limit, and position/patch semantics before removing these gates.

Cache keys are SHA-256 hashes of the operation label and canonical variables only. The authorization token is neither a key component nor written to disk. TTLs are centralized: identity 6h; meta/pair evidence 3h. Expired data is not silently returned as fresh.

## Schema probe

Run `python -m dota_support_draft.stratz_schema_probe` only after configuring `STRATZ_API_TOKEN` in the interactive environment. Phase 1 first asks `__schema` for the server's actual query-root name, then probes that name through a GraphQL variable—there is no `Query`/`DotaQuery` fallback or hardcode. It prints relevant fields (including `constants`) with six fixed `ofType` wrapper levels. Phase 2 uses a bounded breadth-first traversal of reachable relevant named input/object types: at most 12 type probes, depth 3, and 14 fields per type; duplicate names are queried once. It uses normal transport/error mapping, never prints the token, and neither persists nor dumps the schema response. A missing or malformed root name is a probe failure. Its output must be reviewed before adding any production role/meta/pair query.
