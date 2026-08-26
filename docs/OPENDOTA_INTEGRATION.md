# OpenDota integration

Checked 2026-08-26 against [OpenDota docs](https://docs.opendota.com/) and the maintained [dotaconstants](https://github.com/odota/dotaconstants) build data. Base URL: `https://api.opendota.com/api`.

| Endpoint | Consumed fields | Scope |
| --- | --- | --- |
| `/constants/heroes` | `id`, `name`, `localized_name`, `cm_enabled` | static hero identity; CM status remains provider metadata |
| `/constants/patch` | `id`, `name`, `date` | authoritative patch chronology |
| `/players/{account_id}` | `profile.personaname` | public availability/profile |
| `/players/{account_id}/heroes` | `hero_id`, `games`, `win` | all-time player hero totals |
| `/players/{account_id}/recentMatches` | match, hero, timing, side and result fields | recent summaries |

The basic GET path is anonymous. The documented historical free-tier guidance is rate limited; the transport maps HTTP 429 explicitly. An optional token is configuration-only and is not used or logged by this baseline.

Patch dates come from the constants source. A player hero total is all-time evidence, so its provenance has `patch_version = None`; it is never relabelled with the application current patch. Lane-role evidence remains raw numeric evidence and never becomes Position 4 or 5 in DOTA-002.

`cm_enabled` is Captains Mode availability, not general hero activity; it never sets `Hero.is_active` false. The disk HTTP cache keys a request path by SHA-256. Hero constants use a seven-day TTL, patch constants six hours, and player paths 15 minutes. A valid cache preserves its original retrieval time. Corrupt/expired entries refresh; no stale fallback is returned silently. Raw cache owns responses; SQLite remains the normalized persistence boundary.
