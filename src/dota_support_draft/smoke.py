"""Opt-in OpenDota smoke command; it never runs during pytest."""

from __future__ import annotations

import os

from dota_support_draft.config import Settings
from dota_support_draft.domain import PlayerProfile
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.opendota import OpenDotaProvider


def main() -> int:
    account_id = os.environ.get("DOTA_SUPPORT_ACCOUNT_ID")
    if not account_id:
        print("DOTA_SUPPORT_ACCOUNT_ID must be set to run the OpenDota smoke command.")
        return 2
    settings = Settings.from_environment()
    provider = OpenDotaProvider(DiskJsonCache(settings.cache_directory))
    try:
        patch = provider.get_current_patch()
        heroes = provider.get_heroes()
        profile = provider.get_player_profile_state(PlayerProfile(account_id))
        stats = provider.get_player_hero_stats(PlayerProfile(account_id))
        matches = provider.get_player_matches(PlayerProfile(account_id))
    except ProviderError as error:
        print(f"OpenDota smoke failed: {error}")
        return 1
    print("OpenDota connectivity: OK (responses may be NETWORK or CACHE)")
    print(f"Current patch: {patch.version}")
    print(f"Hero count: {len(heroes)}")
    print(f"Player availability: {profile.availability}")
    print(f"Top personal heroes: {len(stats[:3])}")
    print(f"Recent match count: {len(matches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
