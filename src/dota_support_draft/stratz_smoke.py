"""Explicit, opt-in STRATZ smoke boundary; never run by pytest or bootstrap."""

from __future__ import annotations

from dota_support_draft.config import Settings
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.stratz import StratzProvider


def main() -> int:
    settings = Settings.from_environment()
    if not settings.stratz_api_token:
        print("STRATZ smoke: NOT RUN / TOKEN NOT CONFIGURED")
        return 2
    provider = StratzProvider(DiskJsonCache(settings.cache_directory), settings.stratz_api_token)
    if provider.configured:
        print("STRATZ smoke: NOT RUN / schema capability not yet verified")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
