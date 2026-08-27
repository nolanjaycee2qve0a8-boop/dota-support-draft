"""Read-only STRATZ GraphQL boundary.

The only raw GraphQL objects live in this module.  Callers receive typed evidence or
an explicit provider error; a failed/unknown query never becomes zero evidence.
"""

from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dota_support_draft.domain import (
    CounterEvidence,
    DataProvenance,
    Hero,
    Patch,
    Role,
    RoleMetaEvidence,
    SynergyEvidence,
)
from dota_support_draft.providers.cache import CachedJson, DiskJsonCache
from dota_support_draft.providers.errors import (
    PatchResolutionError,
    ProviderAuthenticationRequired,
    ProviderCapabilityUnavailable,
    ProviderGraphQLError,
    ProviderMalformedResponse,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderTransportError,
)

STRATZ_GRAPHQL_URL = "https://api.stratz.com/graphql"
USER_AGENT = "DotaSupportDraft/0.1"


class GraphQLTransport(Protocol):
    def post(
        self, query: str, variables: dict[str, object], token: str | None, timeout_seconds: float
    ) -> object: ...


class UrllibGraphQLTransport:
    """Synchronous transport, injected in tests and never invoked at import time."""

    def post(
        self, query: str, variables: dict[str, object], token: str | None, timeout_seconds: float
    ) -> object:
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            STRATZ_GRAPHQL_URL,
            data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code in {401, 403}:
                raise ProviderAuthenticationRequired(
                    "STRATZ authentication was rejected"
                ) from error
            if error.code == 429:
                raise ProviderRateLimited("STRATZ rate limited this request") from error
            raise ProviderTransportError(f"STRATZ returned HTTP {error.code}") from error
        except TimeoutError as error:
            raise ProviderTimeout("STRATZ request timed out") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise ProviderTimeout("STRATZ request timed out") from error
            raise ProviderTransportError("STRATZ transport failure") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderMalformedResponse("STRATZ returned invalid JSON") from error


@dataclass(frozen=True, slots=True)
class StratzGameVersion:
    version_id: str
    name: str


@dataclass(frozen=True, slots=True)
class StratzEvidenceRequest:
    patch: Patch
    role: Role
    rank_bracket: str | None
    candidates: tuple[Hero, ...]
    allies: tuple[Hero, ...]
    enemies: tuple[Hero, ...]


class StratzProvider:
    """Position-aware provider with a deliberately small, bounded query surface.

    `winWeek` is the current GraphQL Explorer contract recorded in documentation.
    Its response has no verified game-version filter, so it is intentionally *not*
    normalized as current-patch evidence until a game-version mapping is supplied.
    Counter/synergy operation position filtering is not verified and is therefore
    unavailable rather than mislabeled P4/P5 evidence.
    """

    META_TTL = timedelta(hours=3)
    PAIR_TTL = timedelta(hours=3)
    IDENTITY_TTL = timedelta(hours=6)

    def __init__(
        self,
        cache: DiskJsonCache,
        token: str | None,
        transport: GraphQLTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache = cache
        self._token = token.strip() if token else None
        self._transport = transport or UrllibGraphQLTransport()
        self._timeout = timeout_seconds

    @property
    def configured(self) -> bool:
        return self._token is not None

    @staticmethod
    def cache_identity(operation: str, variables: dict[str, object]) -> str:
        """Tokens are deliberately absent from cache identity and disk payloads."""
        normalized = json.dumps(variables, sort_keys=True, separators=(",", ":"))
        return f"stratz:{operation}:{hashlib.sha256(normalized.encode()).hexdigest()}"

    def _query(
        self, operation: str, query: str, variables: dict[str, object], ttl: timedelta
    ) -> CachedJson:
        if not self._token:
            raise ProviderCapabilityUnavailable("STRATZ not configured (STRATZ_API_TOKEN absent)")
        identity = self.cache_identity(operation, variables)
        cached = self._cache.read(identity, ttl)
        if cached is not None:
            return cached
        retrieved_at = datetime.now(UTC)
        raw = self._transport.post(query, variables, self._token, self._timeout)
        payload = self._validate_graphql(raw)
        self._cache.write(identity, payload, retrieved_at)
        return CachedJson(payload, retrieved_at, from_cache=False)

    @staticmethod
    def _validate_graphql(raw: object) -> dict[str, object]:
        if not isinstance(raw, dict):
            raise ProviderMalformedResponse("STRATZ GraphQL response must be an object")
        errors = raw.get("errors")
        if errors:
            raise ProviderGraphQLError("STRATZ GraphQL returned errors")
        data = raw.get("data")
        if not isinstance(data, dict):
            raise ProviderMalformedResponse("STRATZ GraphQL response lacks object data")
        return data

    def get_role_meta(self, request: StratzEvidenceRequest) -> tuple[RoleMetaEvidence, ...]:
        """Fetch one bounded, role-specific batch after explicit patch verification.

        The current publicly inspectable contract did not prove a game-version
        argument for this operation.  Refusing it protects against treating a
        rolling window as current-patch data.
        """
        del request
        self._require_configuration()
        raise ProviderCapabilityUnavailable(
            "STRATZ role-meta patch filter is not yet schema-verified; evidence withheld"
        )

    def get_counter_evidence(self, request: StratzEvidenceRequest) -> tuple[CounterEvidence, ...]:
        del request
        self._require_configuration()
        raise ProviderCapabilityUnavailable(
            "STRATZ matchup position filter is not yet schema-verified; evidence withheld"
        )

    def get_synergy_evidence(self, request: StratzEvidenceRequest) -> tuple[SynergyEvidence, ...]:
        del request
        self._require_configuration()
        raise ProviderCapabilityUnavailable(
            "STRATZ synergy position filter is not yet schema-verified; evidence withheld"
        )

    def probe_query(
        self, query: str, variables: dict[str, object] | None = None
    ) -> dict[str, object]:
        """Run an explicit opt-in diagnostic without caching its raw schema response."""
        self._require_configuration()
        raw = self._transport.post(query, variables or {}, self._token, self._timeout)
        return self._validate_graphql(raw)

    @staticmethod
    def normalize_role_meta_rows(
        rows: object,
        heroes: tuple[Hero, ...],
        patch: Patch,
        role: Role,
        retrieved_at: datetime,
        rank_bracket: str | None,
    ) -> tuple[RoleMetaEvidence, ...]:
        """Validate the documented `heroId/matchCount/winCount` DTO shape.

        This normalizer is deliberately separate from query eligibility: it is
        usable only after the calling operation has verified patch semantics.
        """
        if not isinstance(rows, list):
            raise ProviderMalformedResponse("STRATZ role meta rows must be a list")
        known = {hero.hero_id: hero for hero in heroes}
        normalized: list[RoleMetaEvidence] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ProviderMalformedResponse("STRATZ role meta row must be an object")
            try:
                hero_id, matches, wins = (
                    int(row["heroId"]),
                    int(row["matchCount"]),
                    int(row["winCount"]),
                )
                hero = known[hero_id]
                if matches < 0 or wins < 0 or wins > matches:
                    raise ValueError
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse("Invalid STRATZ role meta row") from error
            normalized.append(
                RoleMetaEvidence(
                    hero,
                    role,
                    patch,
                    matches,
                    wins,
                    wins / matches if matches else 0.0,
                    DataProvenance(
                        "STRATZ",
                        retrieved_at,
                        "ROLE_META_PATCH_VERIFIED",
                        patch.version,
                        matches,
                        STRATZ_GRAPHQL_URL,
                    ),
                    rank_bracket,
                )
            )
        return tuple(sorted(normalized, key=lambda item: item.hero.hero_id))

    @staticmethod
    def resolve_patch(open_dota_patch: Patch, versions: tuple[StratzGameVersion, ...]) -> str:
        matches = tuple(version for version in versions if version.name == open_dota_patch.version)
        if len(matches) != 1:
            raise PatchResolutionError(
                f"Cannot unambiguously map OpenDota {open_dota_patch.version} to STRATZ"
            )
        return matches[0].version_id

    def _require_configuration(self) -> None:
        if not self._token:
            raise ProviderCapabilityUnavailable("STRATZ not configured (STRATZ_API_TOKEN absent)")
