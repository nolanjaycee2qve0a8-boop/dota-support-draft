from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError

import pytest

from dota_support_draft.domain import PlayerAvailability, PlayerProfile
from dota_support_draft.providers import opendota
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import (
    PatchResolutionError,
    ProviderCapabilityUnavailable,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderTransportError,
)
from dota_support_draft.providers.opendota import OpenDotaProvider, UrllibJsonTransport


class FakeTransport:
    def __init__(self, values: dict[str, object]) -> None:
        self.values, self.calls = values, 0

    def get_json(self, path: str, timeout_seconds: float) -> object:
        self.calls += 1
        return self.values[path]


def provider(tmp_path, values: dict[str, object]) -> tuple[OpenDotaProvider, FakeTransport]:
    transport = FakeTransport(values)
    return OpenDotaProvider(DiskJsonCache(tmp_path), transport), transport


def test_heroes_normalize_and_sort_deterministically(tmp_path) -> None:
    instance, _ = provider(
        tmp_path,
        {
            "/constants/heroes": {
                "b": {"id": 2, "name": "axe", "localized_name": "Axe"},
                "a": {"id": 1, "name": "antimage"},
            }
        },
    )
    assert [hero.hero_id for hero in instance.get_heroes()] == [1, 2]


def test_cm_disabled_hero_stays_active_for_normal_draft(tmp_path) -> None:
    instance, _ = provider(
        tmp_path, {"/constants/heroes": {"1": {"id": 1, "name": "hero", "cm_enabled": False}}}
    )
    assert instance.get_heroes()[0].is_active


def test_malformed_hero_is_rejected(tmp_path) -> None:
    instance, _ = provider(tmp_path, {"/constants/heroes": {"bad": {"name": "missing"}}})
    with pytest.raises(Exception, match="hero"):
        instance.get_heroes()


def test_cache_hit_avoids_transport(tmp_path) -> None:
    instance, transport = provider(
        tmp_path, {"/constants/heroes": {"1": {"id": 1, "name": "hero"}}}
    )
    instance.get_heroes()
    instance.get_heroes()
    assert transport.calls == 1


def test_patch_selection_and_ambiguity(tmp_path) -> None:
    instance, _ = provider(
        tmp_path, {"/constants/patch": [{"id": 1, "name": "7.40", "date": "2020-01-01T00:00:00Z"}]}
    )
    assert instance.get_current_patch().version == "7.40"
    other, _ = provider(
        tmp_path / "future",
        {"/constants/patch": [{"id": 1, "name": "future", "date": "2099-01-01T00:00:00Z"}]},
    )
    with pytest.raises(PatchResolutionError):
        other.get_current_patch()


def test_personal_stats_are_all_time_and_role_unknown(tmp_path) -> None:
    instance, _ = provider(
        tmp_path,
        {
            "/players/synthetic/heroes": [{"hero_id": 1, "games": 0, "win": 0}],
            "/constants/heroes": {"1": {"id": 1, "name": "hero"}},
        },
    )
    stat = instance.get_player_hero_stats(PlayerProfile("synthetic"))[0]
    assert (stat.win_rate, stat.role, stat.provenance.patch_version) == (0.0, None, None)


def test_recent_match_calculates_dire_win_and_unknown_role(tmp_path) -> None:
    instance, _ = provider(
        tmp_path,
        {
            "/players/synthetic/recentMatches": [
                {
                    "match_id": 1,
                    "hero_id": 2,
                    "start_time": 1,
                    "duration": 2,
                    "player_slot": 128,
                    "radiant_win": True,
                }
            ],
            "/constants/heroes": {"2": {"id": 2, "name": "hero"}},
        },
    )
    match = instance.get_player_matches(PlayerProfile("synthetic"))[0]
    assert not match.player_won and match.inferred_support_role is None


def test_unsupported_capability_is_explicit(tmp_path, patch) -> None:
    instance, _ = provider(tmp_path, {})
    with pytest.raises(ProviderCapabilityUnavailable):
        instance.get_role_stats(None, patch)  # type: ignore[arg-type]


def test_expired_and_corrupt_cache_refreshes(tmp_path) -> None:
    cache = DiskJsonCache(tmp_path)
    cache.write("x", {"old": True}, datetime.now(UTC) - timedelta(days=1))
    assert cache.read("x", timedelta(seconds=1)) is None
    before = set(tmp_path.glob("*.json"))
    cache.write("bad", {"old": True}, datetime.now(UTC))
    cache_file = next(iter(set(tmp_path.glob("*.json")) - before))
    cache_file.write_text("not json")
    assert cache.read("bad", timedelta(days=1)) is None


def test_corrupt_provider_cache_refreshes_from_transport(tmp_path) -> None:
    cache = DiskJsonCache(tmp_path)
    cache.write("/constants/heroes", {"old": True}, datetime.now(UTC))
    next(tmp_path.glob("*.json")).write_text("invalid json")
    transport = FakeTransport({"/constants/heroes": {"1": {"id": 1, "name": "fresh"}}})
    assert OpenDotaProvider(cache, transport).get_heroes()[0].canonical_name == "fresh"
    assert transport.calls == 1


def test_public_and_not_found_player_profiles_are_distinct(tmp_path) -> None:
    public, _ = provider(tmp_path, {"/players/synthetic": {"profile": {"personaname": "Public"}}})
    assert (
        public.get_player_profile_state(PlayerProfile("synthetic")).availability
        is PlayerAvailability.PUBLIC
    )

    class NotFoundTransport:
        def get_json(self, path: str, timeout_seconds: float) -> object:
            raise ProviderNotFound(path)

    unavailable = OpenDotaProvider(DiskJsonCache(tmp_path / "unavailable"), NotFoundTransport())
    assert (
        unavailable.get_player_profile_state(PlayerProfile("synthetic")).availability
        is PlayerAvailability.PRIVATE_OR_UNAVAILABLE
    )


def test_constants_not_found_is_not_player_unavailable(tmp_path) -> None:
    class NotFoundTransport:
        def get_json(self, path: str, timeout_seconds: float) -> object:
            raise ProviderNotFound(path)

    with pytest.raises(ProviderNotFound):
        OpenDotaProvider(DiskJsonCache(tmp_path), NotFoundTransport()).get_heroes()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (HTTPError("url", 429, "rate", {}, None), ProviderRateLimited),
        (HTTPError("url", 500, "failure", {}, None), ProviderTransportError),
        (TimeoutError(), ProviderTimeout),
        (URLError(TimeoutError()), ProviderTimeout),
    ],
)
def test_urllib_transport_maps_http_and_timeout_errors(monkeypatch, error, expected) -> None:
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(opendota, "urlopen", fail)
    with pytest.raises(expected):
        UrllibJsonTransport().get_json("/constants/heroes", 1)
