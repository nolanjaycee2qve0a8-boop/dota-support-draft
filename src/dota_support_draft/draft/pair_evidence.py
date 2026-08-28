"""Pure orchestration for bounded, draft-dependent STRATZ pair evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from dota_support_draft.domain import (
    CounterEvidence,
    DraftState,
    EvidenceSet,
    Hero,
    PersonalHeroStat,
    Role,
    SynergyEvidence,
)
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.stratz import StratzEvidenceRequest
from dota_support_draft.scoring import ExperimentalEvidenceScoringEngine

PAIR_SHORTLIST_SIZE = 8


class PairEvidenceProvider(Protocol):
    def get_counter_evidence(
        self, request: StratzEvidenceRequest
    ) -> tuple[CounterEvidence, ...]: ...

    def get_synergy_evidence(
        self, request: StratzEvidenceRequest
    ) -> tuple[SynergyEvidence, ...]: ...


@dataclass(frozen=True, slots=True)
class PairEvidenceContext:
    """Stable semantic identity used to reject results from an older draft."""

    patch_version: str
    role: Role
    ally_ids: tuple[int, ...]
    enemy_ids: tuple[int, ...]
    shortlist_ids: tuple[int, ...]
    rank_scope: str | None


@dataclass(frozen=True, slots=True)
class PairEvidenceInput:
    generation: int
    context: PairEvidenceContext
    draft: DraftState
    shortlist: tuple[Hero, ...]
    rank_bracket: str | None


@dataclass(frozen=True, slots=True)
class PairEvidenceResult:
    generation: int
    context: PairEvidenceContext
    counters: tuple[CounterEvidence, ...] = ()
    synergies: tuple[SynergyEvidence, ...] = ()
    counter_error: str | None = None
    synergy_error: str | None = None


def select_pair_shortlist(
    draft: DraftState,
    candidates: tuple[Hero, ...],
    base_evidence: EvidenceSet,
    personal_stats: tuple[PersonalHeroStat, ...] = (),
    maximum: int = PAIR_SHORTLIST_SIZE,
) -> tuple[Hero, ...]:
    """Choose deterministic base-evidence candidates; pair overlay never influences selection."""
    if maximum <= 0:
        raise ValueError("Pair shortlist maximum must be positive")
    base_only = EvidenceSet(role_meta=base_evidence.role_meta)
    ranked = ExperimentalEvidenceScoringEngine().rank(draft, candidates, base_only, personal_stats)
    return tuple(result.hero for result in ranked if result.experimental_score is not None)[
        :maximum
    ]


def make_pair_input(
    generation: int,
    draft: DraftState,
    candidates: tuple[Hero, ...],
    base_evidence: EvidenceSet,
    rank_bracket: str | None,
    personal_stats: tuple[PersonalHeroStat, ...] = (),
) -> PairEvidenceInput:
    shortlist = select_pair_shortlist(draft, candidates, base_evidence, personal_stats)
    context = PairEvidenceContext(
        draft.patch.version,
        draft.intended_role,
        tuple(sorted(pick.hero.hero_id for pick in draft.allied_picks)),
        tuple(sorted(pick.hero.hero_id for pick in draft.enemy_picks)),
        tuple(hero.hero_id for hero in shortlist),
        rank_bracket.strip().upper() if rank_bracket else None,
    )
    return PairEvidenceInput(generation, context, draft, shortlist, rank_bracket)


class DraftPairEvidenceService:
    """Synchronous, provider-independent unit of work for a background Qt worker."""

    def __init__(self, provider: PairEvidenceProvider, rank_bracket: str | None = None) -> None:
        self._provider, self._rank_bracket = provider, rank_bracket

    @property
    def rank_bracket(self) -> str | None:
        return self._rank_bracket

    def refresh(self, input_data: PairEvidenceInput) -> PairEvidenceResult:
        if not input_data.shortlist or (
            not input_data.context.ally_ids and not input_data.context.enemy_ids
        ):
            return PairEvidenceResult(input_data.generation, input_data.context)
        request = StratzEvidenceRequest(
            input_data.draft.patch,
            input_data.draft.intended_role,
            self._rank_bracket,
            input_data.shortlist,
            tuple(pick.hero for pick in input_data.draft.allied_picks),
            tuple(pick.hero for pick in input_data.draft.enemy_picks),
        )
        counters: tuple[CounterEvidence, ...] = ()
        synergies: tuple[SynergyEvidence, ...] = ()
        counter_error: str | None = None
        synergy_error: str | None = None
        if request.enemies:
            try:
                counters = self._provider.get_counter_evidence(request)
            except ProviderError as error:
                counter_error = str(error)
        if request.allies:
            try:
                synergies = self._provider.get_synergy_evidence(request)
            except ProviderError as error:
                synergy_error = str(error)
        return PairEvidenceResult(
            input_data.generation,
            input_data.context,
            counters,
            synergies,
            counter_error,
            synergy_error,
        )
