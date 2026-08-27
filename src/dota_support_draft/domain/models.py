"""Provider-neutral, strongly typed Dota concepts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Role(StrEnum):
    POSITION_4 = "POSITION_4"
    POSITION_5 = "POSITION_5"


class TeamSide(StrEnum):
    ALLY = "ALLY"
    ENEMY = "ENEMY"


class LaneRelation(StrEnum):
    SAFE = "SAFE"
    OFF = "OFF"
    ROAM = "ROAM"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Hero:
    hero_id: int
    canonical_name: str
    localized_name: str | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        if self.hero_id <= 0 or not self.canonical_name.strip():
            raise ValueError("Hero requires a positive ID and canonical name")


@dataclass(frozen=True, slots=True)
class Patch:
    patch_id: str
    version: str
    starts_at: date | datetime
    ends_at: date | datetime | None = None

    def __post_init__(self) -> None:
        if not self.patch_id.strip() or not self.version.strip():
            raise ValueError("Patch ID and version are required")
        if self.ends_at is not None and self.ends_at < self.starts_at:
            raise ValueError("Patch end cannot precede patch start")


@dataclass(frozen=True, slots=True)
class DataProvenance:
    """Traceability required for all statistics and manually curated capabilities."""

    provider: str
    retrieved_at: datetime
    source_scope: str
    patch_version: str | None
    sample_size: int | None = None
    source_reference: str | None = None
    data_kind: str = "REAL"

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.source_scope.strip():
            raise ValueError("Provenance provider and source scope are required")
        if self.sample_size is not None and self.sample_size < 0:
            raise ValueError("Provenance sample size cannot be negative")
        if self.data_kind not in {"REAL", "TEST/FIXTURE", "MANUAL", "UNKNOWN / UNAVAILABLE"}:
            raise ValueError("Unknown data kind")


@dataclass(frozen=True, slots=True)
class CapabilityScore:
    value: int
    provenance: DataProvenance

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError("Capability values must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class HeroCapabilities:
    """Optional per-hero assessments; values are not populated wholesale in DOTA-001."""

    hero: Hero
    hard_disable: CapabilityScore | None = None
    soft_disable: CapabilityScore | None = None
    initiation: CapabilityScore | None = None
    counter_initiation: CapabilityScore | None = None
    save: CapabilityScore | None = None
    heal: CapabilityScore | None = None
    dispel: CapabilityScore | None = None
    wave_clear: CapabilityScore | None = None
    push: CapabilityScore | None = None
    anti_heal: CapabilityScore | None = None
    vision: CapabilityScore | None = None
    scouting: CapabilityScore | None = None
    mobility: CapabilityScore | None = None
    lane_pressure: CapabilityScore | None = None
    teamfight: CapabilityScore | None = None
    damage_amp: CapabilityScore | None = None
    defensive_support: CapabilityScore | None = None
    offensive_support: CapabilityScore | None = None
    scaling: CapabilityScore | None = None
    late_game: CapabilityScore | None = None


@dataclass(frozen=True, slots=True)
class HeroPick:
    hero: Hero
    side: TeamSide
    player_role: Role | None = None
    lane_relation: LaneRelation | None = None


@dataclass(frozen=True, slots=True)
class DraftState:
    allied_picks: tuple[HeroPick, ...]
    enemy_picks: tuple[HeroPick, ...]
    intended_role: Role
    patch: Patch
    lane_partner: Hero | None = None
    banned_heroes: frozenset[Hero] = field(default_factory=frozenset)
    unavailable_heroes: frozenset[Hero] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.intended_role not in (Role.POSITION_4, Role.POSITION_5):
            raise ValueError("Only Position 4 and Position 5 are supported")
        if any(pick.side is not TeamSide.ALLY for pick in self.allied_picks):
            raise ValueError("Allied picks must have ALLY side")
        if any(pick.side is not TeamSide.ENEMY for pick in self.enemy_picks):
            raise ValueError("Enemy picks must have ENEMY side")
        allied_ids = {pick.hero.hero_id for pick in self.allied_picks}
        enemy_ids = {pick.hero.hero_id for pick in self.enemy_picks}
        if allied_ids & enemy_ids:
            raise ValueError("A hero cannot be picked by both teams")

    @property
    def picked_heroes(self) -> frozenset[Hero]:
        return frozenset(pick.hero for pick in (*self.allied_picks, *self.enemy_picks))

    def validates_candidate(self, candidate: Hero) -> None:
        if not candidate.is_active:
            raise ValueError("Inactive hero cannot be recommended")
        if candidate in self.picked_heroes:
            raise ValueError("Picked hero cannot be recommended")
        if candidate in self.banned_heroes:
            raise ValueError("Banned hero cannot be recommended")
        if candidate in self.unavailable_heroes:
            raise ValueError("Unavailable hero cannot be recommended")


def _validate_record(matches: int, wins: int, win_rate: float) -> None:
    if matches < 0 or not 0 <= wins <= matches or not 0 <= win_rate <= 1:
        raise ValueError("Invalid match record")


@dataclass(frozen=True, slots=True)
class HeroRoleStat:
    hero: Hero
    role: Role
    patch: Patch
    matches: int
    wins: int
    win_rate: float
    provenance: DataProvenance
    pick_rate: float | None = None
    rank_bracket: str | None = None

    def __post_init__(self) -> None:
        _validate_record(self.matches, self.wins, self.win_rate)


@dataclass(frozen=True, slots=True)
class MatchupStat:
    hero: Hero
    opponent: Hero
    patch: Patch
    matches: int
    wins: int
    win_rate: float
    provenance: DataProvenance

    def __post_init__(self) -> None:
        _validate_record(self.matches, self.wins, self.win_rate)


@dataclass(frozen=True, slots=True)
class HeroPairStat:
    hero: Hero
    partner: Hero
    patch: Patch
    matches: int
    wins: int
    synergy: float
    provenance: DataProvenance

    def __post_init__(self) -> None:
        _validate_record(self.matches, self.wins, self.wins / self.matches if self.matches else 0.0)
        if not -1 <= self.synergy <= 1:
            raise ValueError("Synergy must be between -1 and 1")


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    account_id: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("Account ID is required")


@dataclass(frozen=True, slots=True)
class PersonalHeroStat:
    hero: Hero
    matches: int
    wins: int
    win_rate: float
    confidence: float | None
    provenance: DataProvenance
    role: Role | None = None
    recent_matches: int | None = None
    recent_win_rate: float | None = None
    last_played_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_record(self.matches, self.wins, self.win_rate)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        if self.recent_matches is not None and self.recent_matches < 0:
            raise ValueError("Recent matches cannot be negative")
        if self.recent_win_rate is not None and not 0 <= self.recent_win_rate <= 1:
            raise ValueError("Recent win rate must be between 0 and 1")


class PlayerAvailability(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE_OR_UNAVAILABLE = "PRIVATE_OR_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PlayerProfileState:
    profile: PlayerProfile
    availability: PlayerAvailability
    provenance: DataProvenance


@dataclass(frozen=True, slots=True)
class PlayerMatchSummary:
    match_id: int
    hero: Hero
    start_time: datetime
    duration_seconds: int
    player_is_radiant: bool
    radiant_win: bool
    player_won: bool
    provenance: DataProvenance
    lobby_type: int | None = None
    game_mode: int | None = None
    lane_role_evidence: int | None = None
    inferred_support_role: Role | None = None

    def __post_init__(self) -> None:
        if self.match_id <= 0 or self.duration_seconds < 0:
            raise ValueError("Invalid match summary")
        if self.player_won != (
            self.radiant_win if self.player_is_radiant else not self.radiant_win
        ):
            raise ValueError("Player win must agree with team side")
