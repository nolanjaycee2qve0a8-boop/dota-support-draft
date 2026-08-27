from __future__ import annotations

from dataclasses import dataclass

from dota_support_draft.domain import (
    EvidenceSet,
    Hero,
    Patch,
    PersonalHeroStat,
    PlayerProfile,
    PlayerProfileState,
    Role,
    RoleEvidenceBundle,
    RoleEvidenceBundles,
)
from dota_support_draft.providers.base import DotaDataProvider
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.stratz import (
    GameVersionDiagnostic,
    StratzEvidenceRequest,
    StratzProvider,
)


@dataclass(frozen=True, slots=True)
class DraftBootstrapData:
    patch: Patch
    heroes: tuple[Hero, ...]
    player: PlayerProfileState | None = None
    personal_stats: tuple[PersonalHeroStat, ...] = ()
    personal_error: str | None = None
    evidence_by_role: RoleEvidenceBundles = RoleEvidenceBundles(
        RoleEvidenceBundle(Role.POSITION_4), RoleEvidenceBundle(Role.POSITION_5)
    )
    stratz_freshness: GameVersionDiagnostic | None = None
    stratz_freshness_error: str | None = None


class DraftBootstrapService:
    def __init__(
        self,
        provider: DotaDataProvider,
        stratz_provider: StratzProvider | None = None,
        stratz_rank_bracket: str | None = None,
    ) -> None:
        self.provider = provider
        self.stratz_provider = stratz_provider
        self.stratz_rank_bracket = stratz_rank_bracket

    def load(self, account_id: str | None = None) -> DraftBootstrapData:
        patch, heroes = self.provider.get_current_patch(), self.provider.get_heroes()
        personal_stats: tuple[PersonalHeroStat, ...] = ()
        player: PlayerProfileState | None = None
        personal_error: str | None = None
        if account_id:
            profile = PlayerProfile(account_id)
            try:
                player = self.provider.get_player_profile_state(profile)
            except ProviderError as error:
                personal_error = str(error)
            else:
                try:
                    personal_stats = self.provider.get_player_hero_stats(profile)
                except ProviderError as error:
                    personal_error = str(error)
        evidence_by_role = self._load_recommendation_evidence(patch, heroes)
        freshness: GameVersionDiagnostic | None = None
        freshness_error: str | None = None
        diagnostic = (
            getattr(self.stratz_provider, "game_version_diagnostic", None)
            if self.stratz_provider is not None
            else None
        )
        if callable(diagnostic):
            try:
                freshness = diagnostic(patch)
            except ProviderError as error:
                freshness_error = str(error)
        return DraftBootstrapData(
            patch,
            heroes,
            player,
            personal_stats,
            personal_error,
            evidence_by_role,
            freshness,
            freshness_error,
        )

    def _load_recommendation_evidence(
        self, patch: Patch, heroes: tuple[Hero, ...]
    ) -> RoleEvidenceBundles:
        return RoleEvidenceBundles(
            self._load_role_evidence(Role.POSITION_4, patch, heroes),
            self._load_role_evidence(Role.POSITION_5, patch, heroes),
        )

    def _load_role_evidence(
        self, role: Role, patch: Patch, heroes: tuple[Hero, ...]
    ) -> RoleEvidenceBundle:
        if self.stratz_provider is None:
            return RoleEvidenceBundle(
                role, error="Recommendation evidence unavailable: STRATZ not configured"
            )
        request = StratzEvidenceRequest(patch, role, self.stratz_rank_bracket, heroes, (), ())
        try:
            role_meta = self.stratz_provider.get_role_meta(request)
        except ProviderError as error:
            return RoleEvidenceBundle(role, error=f"Recommendation evidence unavailable: {error}")
        return RoleEvidenceBundle(role, EvidenceSet(role_meta=role_meta))
