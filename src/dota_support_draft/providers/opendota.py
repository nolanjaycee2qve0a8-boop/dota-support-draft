"""Read-only OpenDota adapter with no import-time network activity."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dota_support_draft.domain import (
    DataProvenance,
    Hero,
    HeroPairStat,
    HeroRoleStat,
    MatchupStat,
    Patch,
    PersonalHeroStat,
    PlayerAvailability,
    PlayerMatchSummary,
    PlayerProfile,
    PlayerProfileState,
    Role,
)
from dota_support_draft.providers.base import DotaDataProvider
from dota_support_draft.providers.cache import CachedJson, DiskJsonCache
from dota_support_draft.providers.errors import (
    PatchResolutionError,
    ProviderCapabilityUnavailable,
    ProviderMalformedResponse,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderTransportError,
)

API_BASE_URL = "https://api.opendota.com/api"
ALL_TIME_SCOPE = "ALL_TIME_OPEN_DOTA_PLAYER_HISTORY"


class JsonTransport(Protocol):
    def get_json(self, path: str, timeout_seconds: float) -> Any: ...


class UrllibJsonTransport:
    def get_json(self, path: str, timeout_seconds: float) -> Any:
        request = Request(f"{API_BASE_URL}{path}", headers={"User-Agent": "DotaSupportDraft/0.1"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise ProviderRateLimited("OpenDota rate limited this request") from error
            if error.code == 404:
                raise ProviderNotFound(f"OpenDota path was not found: {path}") from error
            raise ProviderTransportError(f"OpenDota returned HTTP {error.code}") from error
        except TimeoutError as error:
            raise ProviderTimeout("OpenDota request timed out") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise ProviderTimeout("OpenDota request timed out") from error
            raise ProviderTransportError("OpenDota transport failure") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderMalformedResponse("OpenDota returned invalid JSON") from error


class OpenDotaProvider(DotaDataProvider):
    HERO_CONSTANTS_TTL = timedelta(days=7)
    PATCH_CONSTANTS_TTL = timedelta(hours=6)
    PLAYER_DATA_TTL = timedelta(minutes=15)

    def __init__(
        self,
        cache: DiskJsonCache,
        transport: JsonTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cache, self._transport, self._timeout = (
            cache,
            transport or UrllibJsonTransport(),
            timeout_seconds,
        )

    def _get(self, path: str, ttl: timedelta) -> CachedJson:
        cached = self._cache.read(path, ttl)
        if cached is not None:
            return cached
        retrieved_at = datetime.now(UTC)
        payload = self._transport.get_json(path, self._timeout)
        self._cache.write(path, payload, retrieved_at)
        return CachedJson(payload, retrieved_at, from_cache=False)

    @staticmethod
    def _provenance(
        result: CachedJson, path: str, scope: str, sample_size: int | None = None
    ) -> DataProvenance:
        return DataProvenance(
            "OpenDota", result.retrieved_at, scope, None, sample_size, f"{API_BASE_URL}{path}"
        )

    def get_heroes(self) -> tuple[Hero, ...]:
        result = self._get("/constants/heroes", self.HERO_CONSTANTS_TTL)
        if not isinstance(result.payload, dict):
            raise ProviderMalformedResponse("Hero constants must be an object")
        heroes: list[Hero] = []
        for record in result.payload.values():
            if not isinstance(record, dict):
                raise ProviderMalformedResponse("Hero record must be an object")
            try:
                heroes.append(
                    Hero(
                        int(record["id"]),
                        str(record["name"]),
                        record.get("localized_name"),
                        True,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse("Invalid hero record") from error
        return tuple(sorted(heroes, key=lambda hero: hero.hero_id))

    def get_current_patch(self) -> Patch:
        result = self._get("/constants/patch", self.PATCH_CONSTANTS_TTL)
        if not isinstance(result.payload, list):
            raise ProviderMalformedResponse("Patch constants must be a list")
        patches: list[tuple[int, str, datetime]] = []
        for record in result.payload:
            try:
                patches.append(
                    (
                        int(record["id"]),
                        str(record["name"]),
                        datetime.fromisoformat(str(record["date"]).replace("Z", "+00:00")),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse("Invalid patch record") from error
        eligible = [patch for patch in patches if patch[2] <= result.retrieved_at]
        if not eligible:
            raise PatchResolutionError("No authoritative patch has started")
        selected = max(eligible, key=lambda patch: patch[2])
        later = [p[2] for p in patches if p[2] > selected[2]]
        return Patch(
            str(selected[0]), selected[1], selected[2].date(), min(later).date() if later else None
        )

    def get_player_profile_state(self, profile: PlayerProfile) -> PlayerProfileState:
        path = f"/players/{profile.account_id}"
        try:
            result = self._get(path, self.PLAYER_DATA_TTL)
        except ProviderNotFound:
            return PlayerProfileState(
                profile,
                PlayerAvailability.PRIVATE_OR_UNAVAILABLE,
                DataProvenance(
                    "OpenDota",
                    datetime.now(UTC),
                    "PLAYER_PROFILE_UNAVAILABLE",
                    None,
                    source_reference=f"{API_BASE_URL}{path}",
                ),
            )
        if not isinstance(result.payload, dict):
            raise ProviderMalformedResponse("Player profile must be an object")
        details = result.payload.get("profile")
        if not isinstance(details, dict):
            return PlayerProfileState(
                profile,
                PlayerAvailability.PRIVATE_OR_UNAVAILABLE,
                self._provenance(result, path, "PLAYER_PROFILE"),
            )
        return PlayerProfileState(
            PlayerProfile(profile.account_id, details.get("personaname")),
            PlayerAvailability.PUBLIC,
            self._provenance(result, path, "PLAYER_PROFILE"),
        )

    def get_player_hero_stats(
        self, profile: PlayerProfile, patch: Patch | None = None
    ) -> tuple[PersonalHeroStat, ...]:
        if patch is not None:
            raise ProviderCapabilityUnavailable(
                "OpenDota player hero totals are not patch-specific"
            )
        path = f"/players/{profile.account_id}/heroes"
        result = self._get(path, self.PLAYER_DATA_TTL)
        if not isinstance(result.payload, list):
            raise ProviderMalformedResponse("Player heroes must be a list")
        heroes = {hero.hero_id: hero for hero in self.get_heroes()}
        stats: list[PersonalHeroStat] = []
        for row in result.payload:
            try:
                games, wins, hero_id = int(row["games"]), int(row["win"]), int(row["hero_id"])
                hero = heroes.get(hero_id)
                if hero is None:
                    raise ProviderMalformedResponse("Player statistic references unknown hero")
                stats.append(
                    PersonalHeroStat(
                        hero,
                        games,
                        wins,
                        wins / games if games else 0.0,
                        None,
                        self._provenance(result, path, ALL_TIME_SCOPE, games),
                        None,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse("Invalid player hero record") from error
        return tuple(sorted(stats, key=lambda stat: (-stat.matches, stat.hero.hero_id)))

    def get_player_matches(self, profile: PlayerProfile) -> tuple[PlayerMatchSummary, ...]:
        path = f"/players/{profile.account_id}/recentMatches"
        result = self._get(path, self.PLAYER_DATA_TTL)
        if not isinstance(result.payload, list):
            raise ProviderMalformedResponse("Recent matches must be a list")
        heroes = {hero.hero_id: hero for hero in self.get_heroes()}
        matches: list[PlayerMatchSummary] = []
        for row in result.payload:
            try:
                is_radiant, radiant_win = int(row["player_slot"]) < 128, bool(row["radiant_win"])
                hero = heroes.get(int(row["hero_id"]))
                if hero is None:
                    raise ProviderMalformedResponse("Match references unknown hero")
                matches.append(
                    PlayerMatchSummary(
                        int(row["match_id"]),
                        hero,
                        datetime.fromtimestamp(int(row["start_time"]), UTC),
                        int(row["duration"]),
                        is_radiant,
                        radiant_win,
                        radiant_win if is_radiant else not radiant_win,
                        self._provenance(
                            result, path, "RECENT_PLAYER_MATCHES", len(result.payload)
                        ),
                        row.get("lobby_type"),
                        row.get("game_mode"),
                        row.get("lane_role"),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ProviderMalformedResponse("Invalid match record") from error
        return tuple(matches)

    def get_role_stats(self, role: Role, patch: Patch) -> tuple[HeroRoleStat, ...]:
        raise ProviderCapabilityUnavailable("No verified OpenDota global Position 4/5 statistic")

    def get_matchup_stats(self, hero: Hero, patch: Patch) -> tuple[MatchupStat, ...]:
        raise ProviderCapabilityUnavailable("No verified patch-filtered matchup statistic")

    def get_synergy_stats(self, hero: Hero, patch: Patch) -> tuple[HeroPairStat, ...]:
        raise ProviderCapabilityUnavailable("No verified patch-filtered synergy statistic")
