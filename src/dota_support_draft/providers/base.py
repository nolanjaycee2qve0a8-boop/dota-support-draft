from __future__ import annotations

from abc import ABC, abstractmethod

from dota_support_draft.domain import (
    Hero,
    HeroPairStat,
    HeroRoleStat,
    MatchupStat,
    Patch,
    PersonalHeroStat,
    PlayerMatchSummary,
    PlayerProfile,
    PlayerProfileState,
    Role,
)


class DotaDataProvider(ABC):
    """External data boundary; production implementations are intentionally deferred."""

    @abstractmethod
    def get_heroes(self) -> tuple[Hero, ...]: ...

    @abstractmethod
    def get_current_patch(self) -> Patch: ...

    @abstractmethod
    def get_role_stats(self, role: Role, patch: Patch) -> tuple[HeroRoleStat, ...]: ...

    @abstractmethod
    def get_matchup_stats(self, hero: Hero, patch: Patch) -> tuple[MatchupStat, ...]: ...

    @abstractmethod
    def get_synergy_stats(self, hero: Hero, patch: Patch) -> tuple[HeroPairStat, ...]: ...

    @abstractmethod
    def get_player_profile_state(self, profile: PlayerProfile) -> PlayerProfileState: ...

    @abstractmethod
    def get_player_matches(self, profile: PlayerProfile) -> tuple[PlayerMatchSummary, ...]: ...

    @abstractmethod
    def get_player_hero_stats(
        self, profile: PlayerProfile, patch: Patch | None = None
    ) -> tuple[PersonalHeroStat, ...]: ...
