from __future__ import annotations

from dataclasses import dataclass

from dota_support_draft.domain import (
    Hero,
    Patch,
    PersonalHeroStat,
    PlayerProfile,
    PlayerProfileState,
)
from dota_support_draft.providers.base import DotaDataProvider
from dota_support_draft.providers.errors import ProviderError


@dataclass(frozen=True, slots=True)
class DraftBootstrapData:
    patch: Patch
    heroes: tuple[Hero, ...]
    player: PlayerProfileState | None = None
    personal_stats: tuple[PersonalHeroStat, ...] = ()
    personal_error: str | None = None


class DraftBootstrapService:
    def __init__(self, provider: DotaDataProvider) -> None:
        self.provider = provider

    def load(self, account_id: str | None = None) -> DraftBootstrapData:
        patch, heroes = self.provider.get_current_patch(), self.provider.get_heroes()
        if not account_id:
            return DraftBootstrapData(patch, heroes)
        profile = PlayerProfile(account_id)
        try:
            player = self.provider.get_player_profile_state(profile)
        except ProviderError as error:
            return DraftBootstrapData(patch, heroes, personal_error=str(error))
        try:
            return DraftBootstrapData(
                patch, heroes, player, self.provider.get_player_hero_stats(profile)
            )
        except ProviderError as error:
            return DraftBootstrapData(patch, heroes, player, personal_error=str(error))
