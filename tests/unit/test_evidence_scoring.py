from datetime import UTC, datetime

import pytest

from dota_support_draft.domain import (
    CounterEvidence,
    DataProvenance,
    DraftState,
    EvidenceSet,
    Hero,
    HeroPick,
    PersonalHeroStat,
    Role,
    RoleMetaEvidence,
    SynergyEvidence,
    TeamSide,
)
from dota_support_draft.draft.presentation import build_candidate_rows
from dota_support_draft.scoring import ExperimentalEvidenceScoringEngine, sample_confidence


def _provenance(patch: object) -> DataProvenance:
    return DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )


def _draft(hero, other_hero, patch, role=Role.POSITION_5) -> DraftState:
    ally = Hero(999, "npc_dota_hero_ally", "Ally")
    return DraftState(
        (HeroPick(ally, TeamSide.ALLY),),
        (HeroPick(other_hero, TeamSide.ENEMY),),
        role,
        patch,
    )


def test_confidence_increases_with_sample_size() -> None:
    assert sample_confidence(3) < sample_confidence(50_000) < 1


def test_position_four_evidence_never_scores_position_five(hero, other_hero, patch) -> None:
    evidence = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(hero, Role.POSITION_4, patch, 500, 300, 0.6, _provenance(patch)),
        )
    )
    result = ExperimentalEvidenceScoringEngine().score(
        _draft(hero, other_hero, patch), hero, evidence
    )
    assert result.experimental_score is None
    assert "current position meta" in result.missing_evidence


def test_patch_mismatch_is_neutral_not_current_evidence(hero, other_hero, patch) -> None:
    wrong_patch = type(patch)("old", "old", patch.starts_at)
    evidence = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(
                hero, Role.POSITION_5, wrong_patch, 500, 300, 0.6, _provenance(wrong_patch)
            ),
        )
    )
    assert (
        ExperimentalEvidenceScoringEngine()
        .score(_draft(hero, other_hero, patch), hero, evidence)
        .experimental_score
        is None
    )


def test_counter_and_synergy_are_sample_weighted(hero, other_hero, patch) -> None:
    ally = Hero(999, "npc_dota_hero_ally", "Ally")
    evidence = EvidenceSet(
        counters=(
            CounterEvidence(
                hero,
                other_hero,
                Role.POSITION_5,
                patch,
                1000,
                _provenance(patch),
                pair_win_rate=0.60,
                effect=0.1,
            ),
        ),
        synergies=(
            SynergyEvidence(
                hero,
                ally,
                Role.POSITION_5,
                patch,
                1000,
                _provenance(patch),
                pair_win_rate=0.55,
                effect=0.05,
            ),
        ),
    )
    result = ExperimentalEvidenceScoringEngine().score(
        _draft(hero, other_hero, patch), hero, evidence
    )
    components = dict(result.components)
    assert result.experimental_score is not None
    assert components["counter"] == pytest.approx(0.1 * sample_confidence(1000))
    assert components["synergy"] == pytest.approx(0.05 * sample_confidence(1000))


def test_personal_familiarity_is_all_time_role_unknown(hero, other_hero, patch) -> None:
    personal = PersonalHeroStat(hero, 100, 55, 0.55, None, _provenance(patch))
    result = ExperimentalEvidenceScoringEngine().score(
        _draft(hero, other_hero, patch), hero, EvidenceSet(), (personal,)
    )
    assert result.experimental_score is None
    assert "role-unknown" in result.reasons[0].explanation


def test_missing_components_are_neutral_and_disclosed(hero, other_hero, patch) -> None:
    evidence = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(hero, Role.POSITION_5, patch, 1000, 600, 0.6, _provenance(patch)),
        )
    )
    result = ExperimentalEvidenceScoringEngine().score(
        _draft(hero, other_hero, patch), hero, evidence
    )
    assert result.experimental_score is not None
    assert "enemy counter" in result.missing_evidence
    assert any("neutral zero" in reason.explanation for reason in result.reasons)


def test_ranking_is_deterministic_with_hero_id_tiebreak(hero, other_hero, patch) -> None:
    draft = DraftState((), (), Role.POSITION_5, patch)
    result = ExperimentalEvidenceScoringEngine().rank(draft, (other_hero, hero), EvidenceSet())
    assert tuple(item.hero.hero_id for item in result) == (hero.hero_id, other_hero.hero_id)


def test_score_is_bounded_and_not_called_probability(hero, other_hero, patch) -> None:
    evidence = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(
                hero, Role.POSITION_5, patch, 100_000, 100_000, 1.0, _provenance(patch)
            ),
        )
    )
    result = ExperimentalEvidenceScoringEngine().score(
        _draft(hero, other_hero, patch), hero, evidence
    )
    assert 0 <= (result.experimental_score or 0) <= 100
    assert "not a win-probability" in type(result).__doc__.lower()


def test_candidate_row_shows_score_only_when_evidence_exists(hero, other_hero, patch) -> None:
    draft = _draft(hero, other_hero, patch)
    evidence = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(hero, Role.POSITION_5, patch, 1000, 600, 0.6, _provenance(patch)),
        )
    )
    recommendation = ExperimentalEvidenceScoringEngine().score(draft, hero, evidence)
    assert (
        build_candidate_rows((hero,), recommendations=(recommendation,))[0].experimental_score
        is not None
    )
    assert build_candidate_rows((hero,))[0].experimental_score is None
