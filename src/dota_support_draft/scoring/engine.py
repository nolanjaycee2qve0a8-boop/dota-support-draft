"""Deterministic scoring boundary. We intentionally do not freeze production weights yet."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from dota_support_draft.domain import DraftState, Hero, HeroRoleStat, PersonalHeroStat


class ReasonPolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class RecommendationReason:
    polarity: ReasonPolarity
    category: str
    contribution: float
    explanation: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    hero: Hero
    total_score: float
    score_components: tuple[tuple[str, float], ...]
    reasons: tuple[RecommendationReason, ...]
    confidence: float


class DraftScoringEngine(ABC):
    @abstractmethod
    def score(
        self,
        draft: DraftState,
        candidate: Hero,
        role_stats: tuple[HeroRoleStat, ...],
        personal_stats: tuple[PersonalHeroStat, ...] = (),
    ) -> Recommendation: ...


class BaselineDraftScoringEngine(DraftScoringEngine):
    """A transparent placeholder, useful for contract tests but not recommendations."""

    def score(
        self,
        draft: DraftState,
        candidate: Hero,
        role_stats: tuple[HeroRoleStat, ...],
        personal_stats: tuple[PersonalHeroStat, ...] = (),
    ) -> Recommendation:
        draft.validates_candidate(candidate)
        matching_stats = tuple(stat for stat in role_stats if stat.hero == candidate)
        if any(stat.patch.patch_id != draft.patch.patch_id for stat in matching_stats):
            raise ValueError("Role-stat patch mismatches DraftState patch")
        if any(stat.role != draft.intended_role for stat in matching_stats):
            raise ValueError("Role-stat role mismatches intended support role")
        if any(
            stat.hero == candidate and stat.role not in (None, draft.intended_role)
            for stat in personal_stats
        ):
            raise ValueError("Personal-stat role mismatches intended support role")

        meta_score = matching_stats[0].win_rate - 0.5 if matching_stats else 0.0
        reasons = [
            RecommendationReason(
                ReasonPolarity.POSITIVE,
                "eligibility",
                0.0,
                "Hero is active and available for the current support draft.",
            )
        ]
        if matching_stats:
            reasons.append(
                RecommendationReason(
                    ReasonPolarity.POSITIVE,
                    "role_meta",
                    meta_score,
                    "Patch-aligned role statistics are available for future weighting.",
                )
            )
        else:
            reasons.append(
                RecommendationReason(
                    ReasonPolarity.NEGATIVE,
                    "data_quality",
                    0.0,
                    "No patch-aligned public role statistic is available yet.",
                )
            )
        return Recommendation(
            hero=candidate,
            total_score=meta_score,
            score_components=(("role_meta", meta_score),),
            reasons=tuple(reasons),
            confidence=0.5 if matching_stats else 0.0,
        )
