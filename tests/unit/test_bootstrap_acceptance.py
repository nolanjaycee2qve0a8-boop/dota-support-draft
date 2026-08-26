from datetime import UTC, date, datetime

import pytest

from dota_support_draft.domain import (
    DataProvenance,
    Hero,
    Patch,
    PersonalHeroStat,
    PlayerAvailability,
    PlayerProfile,
    PlayerProfileState,
)
from dota_support_draft.draft.bootstrap import DraftBootstrapService
from dota_support_draft.draft.presentation import build_candidate_rows, filter_candidates
from dota_support_draft.draft.session import ManualDraftSession
from dota_support_draft.providers.errors import (
    ProviderTransportError,
)


class CountingProvider:
    def __init__(self) -> None:
        self.calls = {name: 0 for name in ("patch", "heroes", "profile", "stats")}
        self.patch = Patch("p", "7.40", date(2026, 1, 1))
        self.heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 5))
        self.failure: Exception | None = None
        self.fail_at: str | None = None
        self.provenance = DataProvenance(
            "fake", datetime.now(UTC), "test", None, data_kind="TEST/FIXTURE"
        )

    def _call(self, name: str) -> None:
        self.calls[name] += 1
        if self.fail_at == name and self.failure is not None:
            raise self.failure

    def get_current_patch(self) -> Patch:
        self._call("patch")
        return self.patch

    def get_heroes(self) -> tuple[Hero, ...]:
        self._call("heroes")
        return self.heroes

    def get_player_profile_state(self, profile: PlayerProfile) -> PlayerProfileState:
        self._call("profile")
        return PlayerProfileState(profile, PlayerAvailability.PUBLIC, self.provenance)

    def get_player_hero_stats(
        self, profile: PlayerProfile, patch: Patch | None = None
    ) -> tuple[PersonalHeroStat, ...]:
        self._call("stats")
        return (PersonalHeroStat(self.heroes[0], 2, 1, 0.5, None, self.provenance),)


def test_bootstrap_core_loads_patch_and_heroes_once() -> None:
    provider = CountingProvider()
    data = DraftBootstrapService(provider).load()
    assert (
        data.patch is provider.patch
        and data.heroes is provider.heroes
        and provider.calls == {"patch": 1, "heroes": 1, "profile": 0, "stats": 0}
    )


def test_bootstrap_personal_loads_profile_and_stats_once() -> None:
    provider = CountingProvider()
    data = DraftBootstrapService(provider).load("synthetic")
    assert (
        data.player is not None
        and data.personal_stats
        and provider.calls == {"patch": 1, "heroes": 1, "profile": 1, "stats": 1}
    )


def test_profile_provider_error_degrades_core_bootstrap() -> None:
    provider = CountingProvider()
    provider.fail_at = "profile"
    provider.failure = ProviderTransportError("offline")
    data = DraftBootstrapService(provider).load("synthetic")
    assert (
        data.patch is provider.patch and data.heroes and data.personal_error and data.player is None
    )


def test_stats_provider_error_preserves_profile() -> None:
    provider = CountingProvider()
    provider.fail_at = "stats"
    provider.failure = ProviderTransportError("offline")
    data = DraftBootstrapService(provider).load("synthetic")
    assert data.player is not None and data.personal_error and not data.personal_stats


@pytest.mark.parametrize("failure_at", ["patch", "heroes"])
def test_core_provider_failure_propagates(failure_at) -> None:
    provider = CountingProvider()
    provider.fail_at = failure_at
    provider.failure = ProviderTransportError("offline")
    with pytest.raises(ProviderTransportError):
        DraftBootstrapService(provider).load()


def test_unexpected_personal_bug_propagates() -> None:
    provider = CountingProvider()
    provider.fail_at = "profile"
    provider.failure = AttributeError("bug")
    with pytest.raises(AttributeError):
        DraftBootstrapService(provider).load("synthetic")


def test_draft_interactions_make_zero_provider_calls_after_bootstrap() -> None:
    provider = CountingProvider()
    data = DraftBootstrapService(provider).load("synthetic")
    before = provider.calls.copy()
    session = ManualDraftSession(data.heroes, data.patch)
    session.set_role(__import__("dota_support_draft.domain", fromlist=["Role"]).Role.POSITION_5)
    session.add_ally(data.heroes[0])
    session.add_enemy(data.heroes[1])
    session.ban(data.heroes[2])
    session.remove_ally(data.heroes[0])
    session.remove_enemy(data.heroes[1])
    session.unban(data.heroes[2])
    filter_candidates(build_candidate_rows(session.candidates, data.personal_stats), "hero")
    session.clear()
    session.to_draft_state()
    assert provider.calls == before
