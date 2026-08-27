"""Read-only, bounded STRATZ GraphQL provider for current-week position evidence."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dota_support_draft.domain import (
    CounterEvidence,
    DataProvenance,
    EvidenceScope,
    EvidenceScopeKind,
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
ROLE_META_QUERY = """query CurrentWeekRoleMeta($heroIds:[Short],$positionIds:[MatchPlayerPositionType],$bracketBasicIds:[RankBracketBasicEnum]) {
  heroStats { stats(heroIds:$heroIds, positionIds:$positionIds, bracketBasicIds:$bracketBasicIds, groupByTime:false, groupByPosition:true, groupByBracket:false) { heroId week time position bracketBasicIds matchCount remainingMatchCount winCount } }
}"""
GAME_VERSIONS_QUERY = (
    "query StratzGameVersions { constants { gameVersions { id name asOfDateTime } } }"
)


class GraphQLTransport(Protocol):
    def post(
        self, query: str, variables: dict[str, object], token: str | None, timeout_seconds: float
    ) -> object: ...


class UrllibGraphQLTransport:
    def post(
        self, query: str, variables: dict[str, object], token: str | None, timeout_seconds: float
    ) -> object:
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            STRATZ_GRAPHQL_URL,
            data=json.dumps({"query": query, "variables": variables}).encode(),
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
    as_of_date_time: int | None = None


class GameVersionFreshness(StrEnum):
    MATCHED = "MATCHED"
    STRATZ_CATALOG_LAGGING = "STRATZ_CATALOG_LAGGING"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class GameVersionDiagnostic:
    state: GameVersionFreshness
    latest: StratzGameVersion | None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class StratzEvidenceRequest:
    patch: Patch
    role: Role
    rank_bracket: str | None
    candidates: tuple[Hero, ...]
    allies: tuple[Hero, ...]
    enemies: tuple[Hero, ...]


class StratzProvider:
    """Production current-week position stats; global matchUp is intentionally excluded."""

    META_TTL = timedelta(minutes=45)
    PAIR_TTL = timedelta(minutes=45)
    IDENTITY_TTL = timedelta(hours=6)
    PAIR_BATCH_SIZE = 8

    def __init__(
        self,
        cache: DiskJsonCache,
        token: str | None,
        transport: GraphQLTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache, self._token = cache, token.strip() if token else None
        self._transport, self._timeout = transport or UrllibGraphQLTransport(), timeout_seconds

    @property
    def configured(self) -> bool:
        return self._token is not None

    @staticmethod
    def cache_identity(operation: str, variables: dict[str, object]) -> str:
        normalized = json.dumps(variables, sort_keys=True, separators=(",", ":"))
        return f"stratz:{operation}:{hashlib.sha256(normalized.encode()).hexdigest()}"

    def _query(
        self, operation: str, query: str, variables: dict[str, object], ttl: timedelta
    ) -> CachedJson:
        self._require_configuration()
        identity = self.cache_identity(operation, variables)
        cached = self._cache.read(identity, ttl)
        if cached is not None:
            return cached
        retrieved_at = datetime.now(UTC)
        payload = self._validate_graphql(
            self._transport.post(query, variables, self._token, self._timeout)
        )
        self._cache.write(identity, payload, retrieved_at)
        return CachedJson(payload, retrieved_at, from_cache=False)

    @staticmethod
    def _validate_graphql(raw: object) -> dict[str, object]:
        if not isinstance(raw, dict):
            raise ProviderMalformedResponse("STRATZ GraphQL response must be an object")
        if raw.get("errors"):
            raise ProviderGraphQLError("STRATZ GraphQL returned errors")
        data = raw.get("data")
        if not isinstance(data, dict):
            raise ProviderMalformedResponse("STRATZ GraphQL response lacks object data")
        return data

    @staticmethod
    def _role_position(role: Role) -> str:
        if role in {Role.POSITION_4, Role.POSITION_5}:
            return role.value
        raise ValueError("Only Position 4 and Position 5 are supported")

    @staticmethod
    def normalize_rank_bracket(value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        value = value.strip().upper()
        direct = {
            "UNCALIBRATED",
            "HERALD_GUARDIAN",
            "CRUSADER_ARCHON",
            "LEGEND_ANCIENT",
            "DIVINE_IMMORTAL",
        }
        fine = {
            "HERALD": "HERALD_GUARDIAN",
            "GUARDIAN": "HERALD_GUARDIAN",
            "CRUSADER": "CRUSADER_ARCHON",
            "ARCHON": "CRUSADER_ARCHON",
            "LEGEND": "LEGEND_ANCIENT",
            "ANCIENT": "LEGEND_ANCIENT",
            "DIVINE": "DIVINE_IMMORTAL",
            "IMMORTAL": "DIVINE_IMMORTAL",
        }
        if value in direct:
            return value
        if value in fine:
            return fine[value]
        raise ValueError(f"Unsupported STRATZ rank bracket: {value}")

    def get_role_meta(self, request: StratzEvidenceRequest) -> tuple[RoleMetaEvidence, ...]:
        self._require_configuration()
        if not request.candidates:
            return ()
        rank = self.normalize_rank_bracket(request.rank_bracket)
        variables: dict[str, object] = {
            "heroIds": [hero.hero_id for hero in request.candidates],
            "positionIds": [self._role_position(request.role)],
            "bracketBasicIds": [rank] if rank else None,
        }
        result = self._query("current_week_role_meta", ROLE_META_QUERY, variables, self.META_TTL)
        return self.normalize_current_week_role_meta_rows(
            self._nested_list(result.payload, "heroStats", "stats"),
            request.candidates,
            request.role,
            result.retrieved_at,
            rank,
        )

    @staticmethod
    def _nested_list(payload: dict[str, object], *keys: str) -> list[object]:
        current: object = payload
        for key in keys:
            if not isinstance(current, dict):
                raise ProviderMalformedResponse("STRATZ response has unexpected object shape")
            current = current.get(key)
        if not isinstance(current, list):
            raise ProviderMalformedResponse("STRATZ response expected a list")
        return current

    @staticmethod
    def normalize_current_week_role_meta_rows(
        rows: object,
        heroes: tuple[Hero, ...],
        role: Role,
        retrieved_at: datetime,
        rank_bracket: str | None,
    ) -> tuple[RoleMetaEvidence, ...]:
        if not isinstance(rows, list):
            raise ProviderMalformedResponse("STRATZ role meta rows must be a list")
        known, out, seen, weeks = {hero.hero_id: hero for hero in heroes}, [], set(), set()
        for row in rows:
            if not isinstance(row, dict):
                raise ProviderMalformedResponse("STRATZ role meta row must be an object")
            try:
                hero_id, week, matches, wins = (
                    int(row["heroId"]),
                    int(row["week"]),
                    int(row["matchCount"]),
                    int(row["winCount"]),
                )
                if (
                    hero_id not in known
                    or hero_id in seen
                    or row["position"] != StratzProvider._role_position(role)
                    or matches < 0
                    or not 0 <= wins <= matches
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse(
                    "Invalid or ambiguous STRATZ current-week role meta row"
                ) from error
            seen.add(hero_id)
            weeks.add(week)
            out.append((known[hero_id], week, matches, wins))
        if len(weeks) > 1:
            raise ProviderMalformedResponse("STRATZ current-week rows span multiple week IDs")
        return tuple(
            RoleMetaEvidence(
                hero,
                role,
                None,
                matches,
                wins,
                wins / matches if matches else 0.0,
                DataProvenance(
                    "STRATZ",
                    retrieved_at,
                    "ROLE_META_CURRENT_WEEK_POSITION",
                    None,
                    matches,
                    STRATZ_GRAPHQL_URL,
                ),
                rank_bracket,
                scope=EvidenceScope(EvidenceScopeKind.CURRENT_WEEK, week, rank_scope=rank_bracket),
            )
            for hero, week, matches, wins in sorted(out, key=lambda item: item[0].hero_id)
        )

    def get_game_versions(self) -> tuple[StratzGameVersion, ...]:
        result = self._query("game_versions", GAME_VERSIONS_QUERY, {}, self.IDENTITY_TTL)
        rows = self._nested_list(result.payload, "constants", "gameVersions")
        output = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), (str, int)):
                raise ProviderMalformedResponse("Invalid STRATZ gameVersion row")
            if not isinstance(row.get("name"), str):
                raise ProviderMalformedResponse("Invalid STRATZ gameVersion row")
            raw_as_of = row.get("asOfDateTime")
            if raw_as_of is not None and not isinstance(raw_as_of, int):
                raise ProviderMalformedResponse("Invalid STRATZ gameVersion asOfDateTime")
            output.append(StratzGameVersion(str(row["id"]), row["name"], raw_as_of))
        return tuple(
            sorted(
                output,
                key=lambda version: (
                    version.as_of_date_time is None,
                    -(version.as_of_date_time or 0),
                    version.version_id,
                    version.name,
                ),
            )
        )

    def game_version_diagnostic(self, patch: Patch) -> GameVersionDiagnostic:
        versions = self.get_game_versions()
        latest = versions[0] if versions else None
        if len(tuple(version for version in versions if version.name == patch.version)) == 1:
            return GameVersionDiagnostic(GameVersionFreshness.MATCHED, latest)
        if latest:
            return GameVersionDiagnostic(
                GameVersionFreshness.STRATZ_CATALOG_LAGGING,
                latest,
                f"STRATZ current-week position evidence is active; game-version catalog does not yet contain OpenDota patch {patch.version}.",
            )
        return GameVersionDiagnostic(
            GameVersionFreshness.UNRESOLVED, None, "STRATZ game-version catalog was empty."
        )

    def _lane_query(
        self, candidates: tuple[Hero, ...], role: Role, rank: str | None, is_with: bool
    ) -> tuple[str, dict[str, object]]:
        declarations, fields = [], []
        variables: dict[str, object] = {
            "positionIds": [self._role_position(role)],
            "bracketBasicIds": [rank] if rank else None,
        }
        for index, hero in enumerate(candidates):
            declarations.append(f"$heroId{index}:Short!")
            fields.append(
                f"c{index}:laneOutcome(heroId:$heroId{index},isWith:{str(is_with).lower()},positionIds:$positionIds,bracketBasicIds:$bracketBasicIds){{heroId1 heroId2 week position matchCount drawCount winCount lossCount stompWinCount stompLossCount matchWinCount}}"
            )
            variables[f"heroId{index}"] = hero.hero_id
        query = f"query CurrentWeekLaneProfiles({','.join(declarations)},$positionIds:[MatchPlayerPositionType],$bracketBasicIds:[RankBracketBasicEnum]){{heroStats{{{' '.join(fields)}}}}}"
        return query, variables

    def _lane_profiles(
        self, candidates: tuple[Hero, ...], role: Role, rank: str | None, is_with: bool
    ) -> tuple[tuple[Hero, list[object], datetime], ...]:
        out = []
        ordered = tuple(sorted(candidates, key=lambda hero: hero.hero_id))
        for start in range(0, len(ordered), self.PAIR_BATCH_SIZE):
            batch = ordered[start : start + self.PAIR_BATCH_SIZE]
            query, variables = self._lane_query(batch, role, rank, is_with)
            result = self._query(
                "lane_profiles_with" if is_with else "lane_profiles_against",
                query,
                variables,
                self.PAIR_TTL,
            )
            stats = result.payload.get("heroStats")
            if not isinstance(stats, dict):
                raise ProviderMalformedResponse("STRATZ laneOutcome response has unexpected shape")
            for index, hero in enumerate(batch):
                rows = stats.get(f"c{index}")
                if not isinstance(rows, list):
                    raise ProviderMalformedResponse("STRATZ laneOutcome alias is not a list")
                out.append((hero, rows, result.retrieved_at))
        return tuple(out)

    def _pair_evidence(
        self, request: StratzEvidenceRequest, is_with: bool
    ) -> tuple[CounterEvidence, ...] | tuple[SynergyEvidence, ...]:
        related = request.allies if is_with else request.enemies
        if not request.candidates or not related:
            return ()
        rank = self.normalize_rank_bracket(request.rank_bracket)
        baselines = {row.hero: row for row in self.get_role_meta(request)}
        wanted = {hero.hero_id: hero for hero in related}
        out: list[CounterEvidence | SynergyEvidence] = []
        for candidate, rows, retrieved_at in self._lane_profiles(
            request.candidates, request.role, rank, is_with
        ):
            baseline = baselines.get(candidate)
            if (
                baseline is None
                or baseline.scope.kind is not EvidenceScopeKind.CURRENT_WEEK
                or baseline.scope.rank_scope != rank
            ):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    raise ProviderMalformedResponse("STRATZ laneOutcome row must be an object")
                try:
                    first, second = int(row["heroId1"]), int(row["heroId2"])
                except (KeyError, TypeError, ValueError) as error:
                    raise ProviderMalformedResponse("Invalid STRATZ laneOutcome row") from error
                if first != candidate.hero_id:
                    raise ProviderMalformedResponse(
                        "STRATZ laneOutcome row belongs to another hero"
                    )
                if second not in wanted:
                    continue
                try:
                    week, matches, wins = (
                        int(row["week"]),
                        int(row["matchCount"]),
                        int(row["matchWinCount"]),
                    )
                    if matches < 0 or not 0 <= wins <= matches:
                        raise ValueError
                except (KeyError, TypeError, ValueError) as error:
                    raise ProviderMalformedResponse("Invalid STRATZ laneOutcome row") from error
                if not matches or week != baseline.scope.stratz_week_id:
                    continue
                rate = wins / matches
                scope = EvidenceScope(EvidenceScopeKind.CURRENT_WEEK, week, rank_scope=rank)
                provenance = DataProvenance(
                    "STRATZ",
                    retrieved_at,
                    "LANE_OUTCOME_CURRENT_WEEK_POSITION",
                    None,
                    matches,
                    STRATZ_GRAPHQL_URL,
                )
                if is_with:
                    out.append(
                        SynergyEvidence(
                            candidate,
                            wanted[second],
                            request.role,
                            None,
                            matches,
                            provenance,
                            rate,
                            rate - baseline.win_rate,
                            rank,
                            scope,
                        )
                    )
                else:
                    out.append(
                        CounterEvidence(
                            candidate,
                            wanted[second],
                            request.role,
                            None,
                            matches,
                            provenance,
                            rate,
                            rate - baseline.win_rate,
                            rank,
                            scope,
                        )
                    )
        return cast(
            tuple[CounterEvidence, ...] | tuple[SynergyEvidence, ...],
            tuple(
                sorted(
                    out,
                    key=lambda row: (
                        row.candidate.hero_id,
                        (row.ally if isinstance(row, SynergyEvidence) else row.enemy).hero_id,
                    ),
                )
            ),
        )

    def get_counter_evidence(self, request: StratzEvidenceRequest) -> tuple[CounterEvidence, ...]:
        return cast(tuple[CounterEvidence, ...], self._pair_evidence(request, False))

    def get_synergy_evidence(self, request: StratzEvidenceRequest) -> tuple[SynergyEvidence, ...]:
        return cast(tuple[SynergyEvidence, ...], self._pair_evidence(request, True))

    def probe_query(
        self, query: str, variables: dict[str, object] | None = None
    ) -> dict[str, object]:
        self._require_configuration()
        return self._validate_graphql(
            self._transport.post(query, variables or {}, self._token, self._timeout)
        )

    @staticmethod
    def normalize_role_meta_rows(
        rows: object,
        heroes: tuple[Hero, ...],
        patch: Patch,
        role: Role,
        retrieved_at: datetime,
        rank_bracket: str | None,
    ) -> tuple[RoleMetaEvidence, ...]:
        if not isinstance(rows, list):
            raise ProviderMalformedResponse("STRATZ role meta rows must be a list")
        known, out = {hero.hero_id: hero for hero in heroes}, []
        for row in rows:
            try:
                hero_id, matches, wins = (
                    int(row["heroId"]),
                    int(row["matchCount"]),
                    int(row["winCount"]),
                )
                if hero_id not in known or matches < 0 or not 0 <= wins <= matches:
                    raise ValueError
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse("Invalid STRATZ role meta row") from error
            out.append(
                RoleMetaEvidence(
                    known[hero_id],
                    role,
                    patch,
                    matches,
                    wins,
                    wins / matches if matches else 0.0,
                    DataProvenance(
                        "STRATZ",
                        retrieved_at,
                        "ROLE_META_GAME_VERSION",
                        patch.version,
                        matches,
                        STRATZ_GRAPHQL_URL,
                    ),
                    rank_bracket,
                    scope=EvidenceScope(
                        EvidenceScopeKind.GAME_VERSION,
                        patch_version=patch.version,
                        rank_scope=rank_bracket,
                    ),
                )
            )
        return tuple(sorted(out, key=lambda item: item.hero.hero_id))

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
