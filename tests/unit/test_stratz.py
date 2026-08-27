from datetime import UTC, datetime, timedelta

import pytest

from dota_support_draft.domain import Hero, Role
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import (
    PatchResolutionError,
    ProviderCapabilityUnavailable,
    ProviderGraphQLError,
    ProviderMalformedResponse,
)
from dota_support_draft.providers.stratz import (
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


def test_token_absence_has_explicit_fallback(tmp_path) -> None:
    provider = StratzProvider(DiskJsonCache(tmp_path), None)
    request = provider.__class__.__dict__["get_role_meta"]
    with pytest.raises(ProviderCapabilityUnavailable, match="not configured"):
        request(provider, object())


def test_unverified_capability_does_not_fan_out_per_candidate(tmp_path, patch) -> None:
    transport = FakeTransport({"data": {"unused": True}})
    provider = StratzProvider(DiskJsonCache(tmp_path), "token", transport)
    candidates = tuple(Hero(index, f"hero_{index}") for index in range(1, 128))
    request = StratzEvidenceRequest(patch, Role.POSITION_5, None, candidates, (), ())
    with pytest.raises(ProviderCapabilityUnavailable, match="schema-verified"):
        provider.get_role_meta(request)
    assert transport.calls == []


def test_cache_key_never_contains_token(tmp_path) -> None:
    provider = StratzProvider(DiskJsonCache(tmp_path), "secret-token")
    assert "secret-token" not in provider.cache_identity("meta", {"role": "POSITION_5"})


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
