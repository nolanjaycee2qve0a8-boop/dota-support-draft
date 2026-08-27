"""Explainable experimental (not probabilistic) evidence ranking."""

from __future__ import annotations

from dataclasses import dataclass

from dota_support_draft.domain import (
    CounterEvidence,
    DraftState,
    EvidenceSet,
    Hero,
    PersonalHeroStat,
    RoleMetaEvidence,
    SynergyEvidence,
)
from dota_support_draft.scoring.engine import ReasonPolarity, RecommendationReason


@dataclass(frozen=True, slots=True)
class ExperimentalWeights:
    meta: float = 0.25
    counter: float = 0.30
    synergy: float = 0.25
    familiarity: float = 0.20

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.values()) or sum(self.values()) == 0:
            raise ValueError("Experimental weights must be non-negative and non-zero")

    def values(self) -> tuple[float, float, float, float]:
        return self.meta, self.counter, self.synergy, self.familiarity


@dataclass(frozen=True, slots=True)
class ExperimentalRecommendation:
    """0–100 internal ordering score, expressly not a win-probability estimate."""

    hero: Hero
    role: str
    experimental_score: float | None
    confidence: float
    components: tuple[tuple[str, float | None], ...]
    reasons: tuple[RecommendationReason, ...]
    missing_evidence: tuple[str, ...]


def sample_confidence(matches: int, half_confidence_matches: int = 100) -> float:
    """Conservative n/(n+k) confidence curve; 100 games reaches 0.5."""
    if matches < 0 or half_confidence_matches <= 0:
        raise ValueError("Match counts must be non-negative and half point positive")
    return matches / (matches + half_confidence_matches)


class ExperimentalEvidenceScoringEngine:
    """Pure local scorer. Missing evidence is neutral via available-weight renormalization."""

    def __init__(self, weights: ExperimentalWeights | None = None) -> None:
        self.weights = weights or ExperimentalWeights()

    def score(
        self,
        draft: DraftState,
        candidate: Hero,
        evidence: EvidenceSet,
        personal_stats: tuple[PersonalHeroStat, ...] = (),
    ) -> ExperimentalRecommendation:
        draft.validates_candidate(candidate)
        meta = self._meta(draft, candidate, evidence.role_meta)
        counters = self._counters(draft, candidate, evidence.counters)
        synergies = self._synergies(draft, candidate, evidence.synergies)
        familiarity = self._familiarity(candidate, personal_stats)
        present = tuple(
            component for component in (meta, counters, synergies, familiarity) if component
        )
        missing = tuple(
            name
            for name, component in (
                ("current position meta", meta),
                ("enemy counter", counters),
                ("ally synergy", synergies),
                ("personal familiarity", familiarity),
            )
            if component is None
        )
        if not present:
            return ExperimentalRecommendation(
                candidate,
                draft.intended_role.value,
                None,
                0.0,
                (("meta", None), ("counter", None), ("synergy", None), ("personal", None)),
                (
                    self._reason(
                        ReasonPolarity.NEGATIVE,
                        "unavailable",
                        0.0,
                        "No experimental evidence is available.",
                    ),
                ),
                missing,
            )
        total_weight = sum(component.weight for component in present)
        normalized = sum(component.value * component.weight / total_weight for component in present)
        confidence = sum(
            component.confidence * component.weight / total_weight for component in present
        )
        components = tuple(
            (name, component.value if component else None)
            for name, component in (
                ("meta", meta),
                ("counter", counters),
                ("synergy", synergies),
                ("personal", familiarity),
            )
        )
        reasons = [component.reason for component in present]
        reasons.extend(
            self._reason(
                ReasonPolarity.NEGATIVE,
                "unavailable",
                0.0,
                f"{name.title()} evidence unavailable; treated neutrally.",
            )
            for name in missing
        )
        return ExperimentalRecommendation(
            candidate,
            draft.intended_role.value,
            round(max(0.0, min(100.0, 50.0 + normalized * 100.0)), 1),
            round(confidence, 3),
            components,
            tuple(reasons),
            missing,
        )

    def rank(
        self,
        draft: DraftState,
        candidates: tuple[Hero, ...],
        evidence: EvidenceSet,
        personal_stats: tuple[PersonalHeroStat, ...] = (),
    ) -> tuple[ExperimentalRecommendation, ...]:
        return tuple(
            sorted(
                (self.score(draft, hero, evidence, personal_stats) for hero in candidates),
                key=lambda result: (
                    result.experimental_score is None,
                    -(result.experimental_score or 0.0),
                    result.hero.localized_name or result.hero.canonical_name,
                    result.hero.hero_id,
                ),
            )
        )

    @dataclass(frozen=True, slots=True)
    class _Component:
        value: float
        confidence: float
        weight: float
        reason: RecommendationReason

    @staticmethod
    def _reason(
        polarity: ReasonPolarity, category: str, contribution: float, explanation: str
    ) -> RecommendationReason:
        return RecommendationReason(polarity, category, contribution, explanation)

    def _meta(
        self, draft: DraftState, candidate: Hero, rows: tuple[RoleMetaEvidence, ...]
    ) -> _Component | None:
        matching = tuple(
            item
            for item in rows
            if item.hero == candidate
            and item.role == draft.intended_role
            and item.patch == draft.patch
        )
        if not matching:
            return None
        item = matching[0]
        value = (item.win_rate - 0.5) * sample_confidence(item.matches)
        polarity = ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE
        return self._Component(
            value,
            sample_confidence(item.matches),
            self.weights.meta,
            self._reason(
                polarity,
                "meta",
                value,
                (
                    f"Current {item.role.value} meta: {item.win_rate:.0%} "
                    f"across {item.matches} matches."
                ),
            ),
        )

    def _counters(
        self, draft: DraftState, candidate: Hero, rows: tuple[CounterEvidence, ...]
    ) -> _Component | None:
        enemy_heroes = {pick.hero for pick in draft.enemy_picks}
        matching = tuple(
            item
            for item in rows
            if item.candidate == candidate
            and item.enemy in enemy_heroes
            and item.role == draft.intended_role
            and item.patch == draft.patch
        )
        if not matching:
            return None
        confidence_total = sum(sample_confidence(item.matches) for item in matching)
        value = (
            sum(item.advantage * sample_confidence(item.matches) for item in matching)
            / confidence_total
        )
        confidence = confidence_total / len(matching)
        polarity = ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE
        return self._Component(
            value,
            confidence,
            self.weights.counter,
            self._reason(
                polarity,
                "counter",
                value,
                f"Counter evidence covers {len(matching)} known enemy hero(es).",
            ),
        )

    def _synergies(
        self, draft: DraftState, candidate: Hero, rows: tuple[SynergyEvidence, ...]
    ) -> _Component | None:
        allied_heroes = {pick.hero for pick in draft.allied_picks}
        matching = tuple(
            item
            for item in rows
            if item.candidate == candidate
            and item.ally in allied_heroes
            and item.role == draft.intended_role
            and item.patch == draft.patch
        )
        if not matching:
            return None
        confidence_total = sum(sample_confidence(item.matches) for item in matching)
        value = (
            sum(item.advantage * sample_confidence(item.matches) for item in matching)
            / confidence_total
        )
        confidence = confidence_total / len(matching)
        polarity = ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE
        return self._Component(
            value,
            confidence,
            self.weights.synergy,
            self._reason(
                polarity,
                "synergy",
                value,
                f"Synergy evidence covers {len(matching)} allied hero(es).",
            ),
        )

    def _familiarity(
        self, candidate: Hero, rows: tuple[PersonalHeroStat, ...]
    ) -> _Component | None:
        item = next((row for row in rows if row.hero == candidate), None)
        if item is None:
            return None
        confidence = sample_confidence(item.matches, 25)
        value = (item.win_rate - 0.5) * confidence * 0.5 + confidence * 0.05
        return self._Component(
            value,
            confidence,
            self.weights.familiarity,
            self._reason(
                ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE,
                "familiarity",
                value,
                f"All-time, role-unknown personal familiarity: {item.matches} matches.",
            ),
        )
