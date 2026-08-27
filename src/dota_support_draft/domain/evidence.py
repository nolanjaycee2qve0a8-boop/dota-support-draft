"""Provider-neutral, position-aware evidence used by experimental ranking only."""

from __future__ import annotations

from dataclasses import dataclass

from dota_support_draft.domain.models import DataProvenance, Hero, Patch, Role


def _validate_matches(matches: int, value: float) -> None:
    if matches < 0 or not 0 <= value <= 1:
        raise ValueError("Evidence requires non-negative matches and a rate from 0 through 1")


@dataclass(frozen=True, slots=True)
class RoleMetaEvidence:
    hero: Hero
    role: Role
    patch: Patch
    matches: int
    wins: int
    win_rate: float
    provenance: DataProvenance
    rank_bracket: str | None = None
    pick_rate: float | None = None

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
    patch: Patch
    matches: int
    candidate_win_rate: float
    provenance: DataProvenance
    rank_bracket: str | None = None

    def __post_init__(self) -> None:
        _validate_matches(self.matches, self.candidate_win_rate)

    @property
    def advantage(self) -> float:
        return self.candidate_win_rate - 0.5


@dataclass(frozen=True, slots=True)
class SynergyEvidence:
    candidate: Hero
    ally: Hero
    role: Role
    patch: Patch
    matches: int
    candidate_win_rate: float
    provenance: DataProvenance
    rank_bracket: str | None = None

    def __post_init__(self) -> None:
        _validate_matches(self.matches, self.candidate_win_rate)

    @property
    def advantage(self) -> float:
        return self.candidate_win_rate - 0.5


@dataclass(frozen=True, slots=True)
class EvidenceSet:
    """Preloaded evidence. Scoring this object never performs network I/O."""

    role_meta: tuple[RoleMetaEvidence, ...] = ()
    counters: tuple[CounterEvidence, ...] = ()
    synergies: tuple[SynergyEvidence, ...] = ()
