"""Explainable experimental (not probabilistic) evidence ranking."""

from __future__ import annotations

from dataclasses import dataclass

from dota_support_draft.domain import (
    CounterEvidence,
    DraftState,
    EvidenceSet,
    Hero,
    PersonalHeroStat,
    Role,
    RoleMetaEvidence,
    SynergyEvidence,
)
from dota_support_draft.scoring.engine import ReasonPolarity, RecommendationReason


@dataclass(frozen=True, slots=True)
class ExperimentalWeights:
    """Fixed V0 policy: missing evidence stays zero and never inherits weight."""

    meta: float = 0.25
    counter: float = 0.30
    synergy: float = 0.25
    familiarity: float = 0.20

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.values()) or abs(sum(self.values()) - 1.0) > 1e-9:
            raise ValueError("Experimental weights must be non-negative and sum to 1.0")
        if self.meta + self.counter + self.synergy <= 0:
            raise ValueError("At least one public evidence weight must be positive")

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
    """Pure local scorer with fixed weights and a public-evidence score gate."""

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
        public_components = tuple(
            item for item in (meta, counters, synergies) if item is not None and item.weight > 0
        )
        all_components = (
            ("meta", meta),
            ("counter", counters),
            ("synergy", synergies),
            ("personal", familiarity),
        )
        missing = tuple(
            name
            for name, item in (
                ("current position meta", meta),
                ("enemy counter", counters),
                ("ally synergy", synergies),
                ("personal familiarity", familiarity),
            )
            if item is None
        )
        components = tuple((name, item.value if item else None) for name, item in all_components)
        reasons = [item.reason for _, item in all_components if item is not None]
        reasons.extend(
            self._reason(
                ReasonPolarity.NEGATIVE,
                "unavailable",
                0.0,
                f"{name.title()} evidence unavailable; fixed weight contributes neutral zero.",
            )
            for name in missing
        )
        if not public_components:
            if familiarity is not None:
                reasons.append(
                    self._reason(
                        ReasonPolarity.NEGATIVE,
                        "public_evidence_gate",
                        0.0,
                        "Personal familiarity alone cannot enable an experimental recommendation.",
                    )
                )
            return ExperimentalRecommendation(
                candidate,
                draft.intended_role.value,
                None,
                0.0,
                components,
                tuple(reasons),
                missing,
            )
        weighted_effect = sum(item.value * item.weight for _, item in all_components if item)
        public_weight = self.weights.meta + self.weights.counter + self.weights.synergy
        confidence = (
            sum(item.confidence * item.coverage * item.weight for item in public_components)
            / public_weight
        )
        return ExperimentalRecommendation(
            candidate,
            draft.intended_role.value,
            round(max(0.0, min(100.0, 50.0 + weighted_effect * 100.0)), 1),
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
        coverage: float
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
        item = next(
            (
                row
                for row in rows
                if row.hero == candidate
                and row.role == draft.intended_role
                and row.patch == draft.patch
            ),
            None,
        )
        if item is None:
            return None
        confidence = sample_confidence(item.matches)
        value = (item.win_rate - 0.5) * confidence
        return self._Component(
            value,
            confidence,
            1.0,
            self.weights.meta,
            self._reason(
                ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE,
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
        return self._pair_component(
            candidate,
            draft.intended_role,
            draft.patch,
            tuple(pick.hero for pick in draft.enemy_picks),
            rows,
            self.weights.counter,
            "counter",
            "enemy",
        )

    def _synergies(
        self, draft: DraftState, candidate: Hero, rows: tuple[SynergyEvidence, ...]
    ) -> _Component | None:
        return self._pair_component(
            candidate,
            draft.intended_role,
            draft.patch,
            tuple(pick.hero for pick in draft.allied_picks),
            rows,
            self.weights.synergy,
            "synergy",
            "ally",
        )

    def _pair_component(
        self,
        candidate: Hero,
        role: Role,
        patch: object,
        related_heroes: tuple[Hero, ...],
        rows: tuple[CounterEvidence, ...] | tuple[SynergyEvidence, ...],
        weight: float,
        category: str,
        related_label: str,
    ) -> _Component | None:
        relevant = tuple(
            row
            for row in rows
            if row.candidate == candidate
            and row.role == role
            and row.patch == patch
            and row.effect is not None
            and row.matches > 0
            and (row.enemy if isinstance(row, CounterEvidence) else row.ally) in related_heroes
        )
        if not relevant:
            return None
        confidences = tuple(sample_confidence(row.matches) for row in relevant)
        confidence_total = sum(confidences)
        raw_effect = (
            sum(
                (row.effect or 0.0) * confidence
                for row, confidence in zip(relevant, confidences, strict=True)
            )
            / confidence_total
        )
        confidence = confidence_total / len(relevant)
        value = raw_effect * confidence
        coverage = len(relevant) / len(related_heroes) if related_heroes else 0.0
        return self._Component(
            value,
            confidence,
            coverage,
            weight,
            self._reason(
                ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE,
                category,
                value,
                (
                    f"{category.title()} evidence: {len(relevant)} / "
                    f"{len(related_heroes)} {related_label} heroes covered."
                ),
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
            1.0,
            self.weights.familiarity,
            self._reason(
                ReasonPolarity.POSITIVE if value >= 0 else ReasonPolarity.NEGATIVE,
                "familiarity",
                value,
                f"All-time, role-unknown personal familiarity: {item.matches} matches.",
            ),
        )
