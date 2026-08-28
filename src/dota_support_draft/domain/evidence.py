"""Provider-neutral, position-aware evidence used by experimental ranking only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dota_support_draft.domain.models import DataProvenance, Hero, Patch, Role


class EvidenceScopeKind(StrEnum):
    CURRENT_WEEK = "CURRENT_WEEK"
    GAME_VERSION = "GAME_VERSION"
    TEST_FIXTURE = "TEST_FIXTURE"


@dataclass(frozen=True, slots=True)
class EvidenceScope:
    """Statistical boundary, deliberately distinct from the active OpenDota patch."""

    kind: EvidenceScopeKind
    stratz_week_id: int | None = None
    game_version_id: int | None = None
    patch_version: str | None = None
    rank_scope: str | None = None

    def __post_init__(self) -> None:
        if self.kind is EvidenceScopeKind.CURRENT_WEEK:
            if self.stratz_week_id is None or self.patch_version is not None:
                raise ValueError(
                    "Current-week evidence requires a STRATZ week and no patch version"
                )
        elif self.kind is EvidenceScopeKind.GAME_VERSION and not self.patch_version:
            raise ValueError("Game-version evidence requires a patch version")


TEST_FIXTURE_SCOPE = EvidenceScope(EvidenceScopeKind.TEST_FIXTURE)


def _validate_matches(matches: int, value: float) -> None:
    if matches < 0 or not 0 <= value <= 1:
        raise ValueError("Evidence requires non-negative matches and a rate from 0 through 1")


@dataclass(frozen=True, slots=True)
class RoleMetaEvidence:
    hero: Hero
    role: Role
    patch: Patch | None
    matches: int
    wins: int
    win_rate: float
    provenance: DataProvenance
    rank_bracket: str | None = None
    pick_rate: float | None = None
    scope: EvidenceScope = TEST_FIXTURE_SCOPE

    def __post_init__(self) -> None:
        _validate_matches(self.matches, self.win_rate)
        if not 0 <= self.wins <= self.matches:
            raise ValueError("Meta wins must be within match count")
        if self.pick_rate is not None and not 0 <= self.pick_rate <= 1:
            raise ValueError("Pick rate must be from 0 through 1")


@dataclass(frozen=True, slots=True)
class CounterEvidence:
    candidate: Hero
    enemy: Hero
    role: Role
    patch: Patch | None
    matches: int
    provenance: DataProvenance
    pair_win_rate: float | None = None
    effect: float | None = None
    rank_bracket: str | None = None
    scope: EvidenceScope = TEST_FIXTURE_SCOPE

    def __post_init__(self) -> None:
        if self.matches < 0:
            raise ValueError("Evidence requires non-negative matches")
        if self.pair_win_rate is not None and not 0 <= self.pair_win_rate <= 1:
            raise ValueError("Pair win rate must be from 0 through 1")
        if self.effect is not None and not -1 <= self.effect <= 1:
            raise ValueError("Verified effect must be between -1 and 1")


@dataclass(frozen=True, slots=True)
class SynergyEvidence:
    candidate: Hero
    ally: Hero
    role: Role
    patch: Patch | None
    matches: int
    provenance: DataProvenance
    pair_win_rate: float | None = None
    effect: float | None = None
    rank_bracket: str | None = None
    scope: EvidenceScope = TEST_FIXTURE_SCOPE

    def __post_init__(self) -> None:
        if self.matches < 0:
            raise ValueError("Evidence requires non-negative matches")
        if self.pair_win_rate is not None and not 0 <= self.pair_win_rate <= 1:
            raise ValueError("Pair win rate must be from 0 through 1")
        if self.effect is not None and not -1 <= self.effect <= 1:
            raise ValueError("Verified effect must be between -1 and 1")


@dataclass(frozen=True, slots=True)
class EvidenceSet:
    """Preloaded evidence. Scoring this object never performs network I/O."""

    role_meta: tuple[RoleMetaEvidence, ...] = ()
    counters: tuple[CounterEvidence, ...] = ()
    synergies: tuple[SynergyEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class RoleEvidenceBundle:
    """Evidence/error state for exactly one intended support position."""

    role: Role
    evidence: EvidenceSet = EvidenceSet()
    error: str | None = None

    def __post_init__(self) -> None:
        roles = (
            *(item.role for item in self.evidence.role_meta),
            *(item.role for item in self.evidence.counters),
            *(item.role for item in self.evidence.synergies),
        )
        if any(item is not self.role for item in roles):
            raise ValueError("Role evidence bundle cannot contain another position")


@dataclass(frozen=True, slots=True)
class RoleEvidenceBundles:
    position_4: RoleEvidenceBundle
    position_5: RoleEvidenceBundle

    def __post_init__(self) -> None:
        if (
            self.position_4.role is not Role.POSITION_4
            or self.position_5.role is not Role.POSITION_5
        ):
            raise ValueError(
                "Role evidence bundles require separate Position 4 and Position 5 entries"
            )

    def for_role(self, role: Role) -> RoleEvidenceBundle:
        if role is Role.POSITION_4:
            return self.position_4
        if role is Role.POSITION_5:
            return self.position_5
        raise ValueError("Only Position 4 and Position 5 have evidence bundles")
