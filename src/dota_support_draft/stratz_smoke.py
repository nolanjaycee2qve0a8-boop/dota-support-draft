"""Explicit live-only STRATZ smoke; never invoked by pytest or desktop bootstrap."""

from __future__ import annotations

from dota_support_draft.config import Settings
from dota_support_draft.domain import Hero, Role
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.opendota import OpenDotaProvider
from dota_support_draft.providers.stratz import StratzEvidenceRequest, StratzProvider


def main() -> int:
    settings = Settings.from_environment()
    if not settings.stratz_api_token:
        print("STRATZ smoke: NOT RUN / TOKEN NOT CONFIGURED")
        return 2
    cache = DiskJsonCache(settings.cache_directory)
    provider = StratzProvider(cache, settings.stratz_api_token)
    patch = OpenDotaProvider(cache).get_current_patch()
    # Small public fixtures; values are live response data, never production constants.
    candidates = (Hero(1, "npc_dota_hero_antimage"), Hero(5, "npc_dota_hero_crystal_maiden"))
    try:
        p4 = provider.get_role_meta(
            StratzEvidenceRequest(
                patch, Role.POSITION_4, settings.stratz_rank_bracket, candidates, (), ()
            )
        )
        p5 = provider.get_role_meta(
            StratzEvidenceRequest(
                patch, Role.POSITION_5, settings.stratz_rank_bracket, candidates, (), ()
            )
        )
        diagnostic = provider.game_version_diagnostic(patch)
        friendly = provider.get_synergy_evidence(
            StratzEvidenceRequest(
                patch,
                Role.POSITION_5,
                settings.stratz_rank_bracket,
                candidates,
                (candidates[0],),
                (),
            )
        )
        against = provider.get_counter_evidence(
            StratzEvidenceRequest(
                patch,
                Role.POSITION_5,
                settings.stratz_rank_bracket,
                candidates,
                (),
                (candidates[0],),
            )
        )
    except ProviderError as error:
        print(f"STRATZ smoke: FAILED / {error}")
        return 1
    print("STRATZ auth/connectivity: OK")
    print(f"current STRATZ week id: {p4[0].scope.stratz_week_id if p4 else 'unavailable'}")
    print(f"P4 role meta: {'available' if p4 else 'unavailable'}")
    print(f"P5 role meta: {'available' if p5 else 'unavailable'}")
    print(f"P4/P5 samples are position-distinct: {p4 != p5}")
    latest_name = diagnostic.latest.name if diagnostic.latest else "unavailable"
    print(f"latest STRATZ gameVersion: {latest_name}")
    print(f"OpenDota current patch: {patch.version}")
    print(f"game-version freshness state: {diagnostic.state}")
    print(f"friendly laneOutcome normalization: {'available' if friendly else 'unavailable'}")
    print(f"against laneOutcome normalization: {'available' if against else 'unavailable'}")
    print(f"pair effect baseline-adjusted: {bool(friendly or against)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
