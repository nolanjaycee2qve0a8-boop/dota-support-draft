# ruff: noqa: E501
from datetime import UTC, datetime, timedelta

import pytest

from dota_support_draft.domain import EvidenceScopeKind, Hero, Role
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import (
    PatchResolutionError,
    ProviderCapabilityUnavailable,
    ProviderGraphQLError,
    ProviderMalformedResponse,
)
from dota_support_draft.providers.stratz import (
    GameVersionFreshness,
    StratzEvidenceRequest,
    StratzGameVersion,
    StratzProvider,
)


class FakeTransport:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object], str | None]] = []

    def post(self, query, variables, token, timeout_seconds):
        del timeout_seconds
        self.calls.append((query, variables, token))
        return self.response


class ScriptedTransport:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object], str | None]] = []

    def post(self, query, variables, token, timeout_seconds):
        del timeout_seconds
        self.calls.append((query, variables, token))
        return self.responses.pop(0)


def _stats(rows):
    return {"data": {"heroStats": {"stats": rows}}}


def _lane(rows):
    return {"data": {"heroStats": {"c0": rows}}}


def _meta_row(hero: Hero, role: Role, week: int = 7) -> dict[str, object]:
    return {
        "heroId": hero.hero_id,
        "week": week,
        "position": role.value,
        "matchCount": 20,
        "winCount": 10,
    }


def _lane_row(first: int, second: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "heroId1": first,
        "heroId2": second,
        "week": 7,
        "position": "POSITION_1",
        "matchCount": 10,
        "matchWinCount": 7,
    }
    row.update(overrides)
    return row


def test_token_absence_has_explicit_fallback(tmp_path) -> None:
    provider = StratzProvider(DiskJsonCache(tmp_path), None)
    request = provider.__class__.__dict__["get_role_meta"]
    with pytest.raises(ProviderCapabilityUnavailable, match="not configured"):
        request(provider, object())


def test_role_meta_uses_one_request_for_many_candidates(tmp_path, patch) -> None:
    transport = FakeTransport({"data": {"heroStats": {"stats": []}}})
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", transport)
    candidates = tuple(Hero(index, f"hero_{index}") for index in range(1, 128))
    request = StratzEvidenceRequest(patch, Role.POSITION_5, None, candidates, (), ())
    provider.get_role_meta(request)
    assert len(transport.calls) == 1


def test_cache_key_never_contains_token(tmp_path) -> None:
    provider = StratzProvider(DiskJsonCache(tmp_path), "secret-token")
    assert "secret-token" not in provider.cache_identity("meta", {"role": "POSITION_5"})


def test_cache_identity_is_deterministic_and_scoped_by_role_and_patch(tmp_path) -> None:
    provider = StratzProvider(DiskJsonCache(tmp_path), "token")
    p4 = provider.cache_identity("meta", {"role": "POSITION_4", "patch": "7.40"})
    assert p4 == provider.cache_identity("meta", {"patch": "7.40", "role": "POSITION_4"})
    assert p4 != provider.cache_identity("meta", {"role": "POSITION_5", "patch": "7.40"})
    assert p4 != provider.cache_identity("meta", {"role": "POSITION_4", "patch": "7.41"})


def test_graphql_errors_and_malformed_schema_are_not_zero_data() -> None:
    with pytest.raises(ProviderGraphQLError):
        StratzProvider._validate_graphql({"errors": [{"message": "bad"}]})
    with pytest.raises(ProviderMalformedResponse):
        StratzProvider._validate_graphql({"data": []})


def test_query_is_cached_and_transport_receives_token(tmp_path) -> None:
    transport = FakeTransport({"data": {"ok": True}})
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", transport)
    assert provider._query(
        "identity", "query X { x }", {"a": 1}, provider.IDENTITY_TTL
    ).payload == {"ok": True}
    provider._query("identity", "query X { x }", {"a": 1}, provider.IDENTITY_TTL)
    assert len(transport.calls) == 1
    assert transport.calls[0][2] == "token"


def test_expired_cache_refreshes(tmp_path) -> None:
    transport = FakeTransport({"data": {"ok": True}})
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", transport)
    provider._query("identity", "query X { x }", {}, timedelta(seconds=-1))
    provider._query("identity", "query X { x }", {}, timedelta(seconds=-1))
    assert len(transport.calls) == 2


def test_patch_resolution_requires_exact_unique_name(patch) -> None:
    assert StratzProvider.resolve_patch(patch, (StratzGameVersion("1", patch.version),)) == "1"
    with pytest.raises(PatchResolutionError):
        StratzProvider.resolve_patch(patch, ())
    with pytest.raises(PatchResolutionError):
        StratzProvider.resolve_patch(
            patch, (StratzGameVersion("1", patch.version), StratzGameVersion("2", patch.version))
        )


def test_role_meta_normalization_preserves_role_and_rank(patch, hero) -> None:
    rows = StratzProvider.normalize_role_meta_rows(
        [{"heroId": hero.hero_id, "matchCount": 20, "winCount": 12}],
        (hero,),
        patch,
        Role.POSITION_4,
        datetime.now(UTC),
        "DIVINE",
    )
    assert rows[0].role is Role.POSITION_4
    assert rows[0].rank_bracket == "DIVINE"


def test_malformed_role_meta_is_rejected(patch, hero) -> None:
    with pytest.raises(ProviderMalformedResponse):
        StratzProvider.normalize_role_meta_rows(
            [{"heroId": 999, "matchCount": 1, "winCount": 1}],
            (hero,),
            patch,
            Role.POSITION_5,
            datetime.now(UTC),
            None,
        )


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("HERALD", "HERALD_GUARDIAN"),
        ("ANCIENT", "LEGEND_ANCIENT"),
        ("DIVINE_IMMORTAL", "DIVINE_IMMORTAL"),
        (None, None),
    ],
)
def test_rank_normalization(configured, expected) -> None:
    assert StratzProvider.normalize_rank_bracket(configured) == expected


def test_invalid_rank_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        StratzProvider.normalize_rank_bracket("ALL")


def test_current_week_meta_query_scope_and_role_mapping(tmp_path, patch, hero, other_hero) -> None:
    transport = ScriptedTransport(
        [
            _stats(
                [
                    {
                        "heroId": hero.hero_id,
                        "week": 2955,
                        "time": 35,
                        "position": "POSITION_4",
                        "matchCount": 20,
                        "winCount": 12,
                    },
                    {
                        "heroId": other_hero.hero_id,
                        "week": 2955,
                        "time": 99,
                        "position": "POSITION_4",
                        "matchCount": 10,
                        "winCount": 5,
                    },
                ]
            )
        ]
    )
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", transport)
    rows = provider.get_role_meta(
        StratzEvidenceRequest(patch, Role.POSITION_4, "ANCIENT", (hero, other_hero), (), ())
    )
    assert len(transport.calls) == 1
    assert transport.calls[0][1]["positionIds"] == ["POSITION_4"]
    assert transport.calls[0][1]["bracketBasicIds"] == ["LEGEND_ANCIENT"]
    assert rows[0].patch is None and rows[0].scope.kind is EvidenceScopeKind.CURRENT_WEEK
    assert rows[0].scope.stratz_week_id == 2955 and rows[0].scope.patch_version is None


def test_current_week_meta_rejects_duplicate_or_wrong_position(tmp_path, patch, hero) -> None:
    duplicate = _stats(
        [
            {
                "heroId": hero.hero_id,
                "week": 1,
                "position": "POSITION_5",
                "matchCount": 1,
                "winCount": 1,
            },
            {
                "heroId": hero.hero_id,
                "week": 1,
                "position": "POSITION_5",
                "matchCount": 1,
                "winCount": 1,
            },
        ]
    )
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", FakeTransport(duplicate))
    request = StratzEvidenceRequest(patch, Role.POSITION_5, None, (hero,), (), ())
    with pytest.raises(ProviderMalformedResponse):
        provider.get_role_meta(request)


def test_lane_outcome_is_baseline_adjusted_and_cached(tmp_path, patch, hero, other_hero) -> None:
    meta = _stats(
        [
            {
                "heroId": hero.hero_id,
                "week": 7,
                "position": "POSITION_5",
                "matchCount": 20,
                "winCount": 10,
            }
        ]
    )
    lane = _lane(
        [
            {
                "heroId1": hero.hero_id,
                "heroId2": other_hero.hero_id,
                "week": 7,
                "position": "POSITION_1",
                "matchCount": 10,
                "matchWinCount": 7,
            }
        ]
    )
    transport = ScriptedTransport([meta, lane])
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", transport)
    request = StratzEvidenceRequest(patch, Role.POSITION_5, None, (hero,), (other_hero,), ())
    rows = provider.get_synergy_evidence(request)
    assert rows[0].pair_win_rate == 0.7 and rows[0].effect == pytest.approx(0.2)
    assert rows[0].role is Role.POSITION_5 and len(transport.calls) == 2
    provider.get_synergy_evidence(request)
    assert len(transport.calls) == 2


def test_lane_outcome_week_mismatch_degrades_without_scoring(
    tmp_path, patch, hero, other_hero
) -> None:
    meta = _stats(
        [
            {
                "heroId": hero.hero_id,
                "week": 7,
                "position": "POSITION_4",
                "matchCount": 20,
                "winCount": 10,
            }
        ]
    )
    lane = _lane(
        [
            {
                "heroId1": hero.hero_id,
                "heroId2": other_hero.hero_id,
                "week": 8,
                "position": "POSITION_1",
                "matchCount": 10,
                "matchWinCount": 7,
            }
        ]
    )
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", ScriptedTransport([meta, lane]))
    request = StratzEvidenceRequest(patch, Role.POSITION_4, None, (hero,), (), (other_hero,))
    assert provider.get_counter_evidence(request) == ()


@pytest.mark.parametrize(
    ("is_with", "method_name"),
    [(True, "get_synergy_evidence"), (False, "get_counter_evidence")],
)
def test_full_lane_profile_locally_filters_unrelated_rows(
    tmp_path, patch, hero, other_hero, is_with, method_name
) -> None:
    related = (other_hero,)
    profile = [
        _lane_row(hero.hero_id, 901),
        _lane_row(hero.hero_id, 902),
        _lane_row(hero.hero_id, other_hero.hero_id),
        _lane_row(hero.hero_id, 903),
    ]
    provider = StratzProvider(
        DiskJsonCache(tmp_path),
        "token",
        ScriptedTransport([_stats([_meta_row(hero, Role.POSITION_5)]), _lane(profile)]),
    )
    request = StratzEvidenceRequest(
        patch,
        Role.POSITION_5,
        None,
        (hero,),
        related if is_with else (),
        () if is_with else related,
    )
    rows = getattr(provider, method_name)(request)
    assert len(rows) == 1
    assert rows[0].pair_win_rate == 0.7
    assert rows[0].effect == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("is_with", "method_name"),
    [(True, "get_synergy_evidence"), (False, "get_counter_evidence")],
)
def test_all_unrelated_lane_profile_rows_are_unavailable(
    tmp_path, patch, hero, other_hero, is_with, method_name
) -> None:
    provider = StratzProvider(
        DiskJsonCache(tmp_path),
        "token",
        ScriptedTransport(
            [
                _stats([_meta_row(hero, Role.POSITION_4)]),
                _lane([_lane_row(hero.hero_id, 901), _lane_row(hero.hero_id, 902)]),
            ]
        ),
    )
    request = StratzEvidenceRequest(
        patch,
        Role.POSITION_4,
        None,
        (hero,),
        (other_hero,) if is_with else (),
        () if is_with else (other_hero,),
    )
    assert getattr(provider, method_name)(request) == ()


def test_selected_lane_profile_row_with_invalid_scoring_fields_is_rejected(
    tmp_path, patch, hero, other_hero
) -> None:
    provider = StratzProvider(
        DiskJsonCache(tmp_path),
        "token",
        ScriptedTransport(
            [
                _stats([_meta_row(hero, Role.POSITION_4)]),
                _lane([_lane_row(hero.hero_id, other_hero.hero_id, matchWinCount=11)]),
            ]
        ),
    )
    request = StratzEvidenceRequest(patch, Role.POSITION_4, None, (hero,), (), (other_hero,))
    with pytest.raises(ProviderMalformedResponse):
        provider.get_counter_evidence(request)


def test_game_versions_sort_newest_first_and_diagnostic_ignores_response_order(
    tmp_path, patch
) -> None:
    payload = {
        "data": {
            "constants": {
                "gameVersions": [
                    {"id": 1, "name": "7.39", "asOfDateTime": 100},
                    {"id": 3, "name": "unknown", "asOfDateTime": None},
                    {"id": 2, "name": patch.version, "asOfDateTime": 300},
                ]
            }
        }
    }
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", FakeTransport(payload))
    versions = provider.get_game_versions()
    assert tuple(version.version_id for version in versions) == ("2", "1", "3")
    assert versions[0].as_of_date_time == 300
    diagnostic = provider.game_version_diagnostic(patch)
    assert diagnostic.state is GameVersionFreshness.MATCHED
    assert diagnostic.latest == versions[0]
