from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dota_support_draft.domain import PlayerProfile
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import PatchResolutionError, ProviderCapabilityUnavailable
from dota_support_draft.providers.opendota import OpenDotaProvider


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
    (tmp_path / "bad.json").write_text("not json")
    assert cache.read("bad", timedelta(days=1)) is None
