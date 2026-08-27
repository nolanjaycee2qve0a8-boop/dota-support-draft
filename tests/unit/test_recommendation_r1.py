from datetime import UTC, datetime

import pytest

from dota_support_draft.domain import (
    CounterEvidence,
    DataProvenance,
    EvidenceSet,
    Hero,
    PersonalHeroStat,
    Role,
    RoleMetaEvidence,
    SynergyEvidence,
)
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.draft.bootstrap import DraftBootstrapService
from dota_support_draft.scoring import ExperimentalEvidenceScoringEngine


def _provenance(patch: object) -> DataProvenance:
    return DataProvenance(
        "fixture", datetime.now(UTC), "fixture", patch.version, data_kind="TEST/FIXTURE"
    )


class CountingCoreProvider:
    def __init__(self, patch, heroes) -> None:
        self.patch = patch
        self.heroes = heroes

    def get_current_patch(self):
        return self.patch

    def get_heroes(self):
        return self.heroes


class CountingStratzProvider:
    def __init__(self, hero, patch) -> None:
        self.hero = hero
        self.patch = patch
        self.calls: list[Role] = []

    def get_role_meta(self, request):
        self.calls.append(request.role)
        if request.role is Role.POSITION_4:
            return (
                RoleMetaEvidence(
                    self.hero,
                    Role.POSITION_4,
                    self.patch,
                    1000,
                    600,
                    0.6,
                    _provenance(self.patch),
                ),
            )
        return ()


def test_bootstrap_keeps_p4_and_p5_evidence_separate(hero, other_hero, patch) -> None:
    stratz = CountingStratzProvider(hero, patch)
    data = DraftBootstrapService(CountingCoreProvider(patch, (hero, other_hero)), stratz).load()
    assert stratz.calls == [Role.POSITION_4, Role.POSITION_5]
    assert (
        data.evidence_by_role.for_role(Role.POSITION_4).evidence.role_meta[0].role
        is Role.POSITION_4
    )
    assert data.evidence_by_role.for_role(Role.POSITION_5).evidence.role_meta == ()


def test_role_switch_never_reuses_p4_evidence_or_calls_provider(hero, other_hero, patch) -> None:
    stratz = CountingStratzProvider(hero, patch)
    data = DraftBootstrapService(CountingCoreProvider(patch, (hero, other_hero)), stratz).load()
    session = ManualDraftSession((hero, other_hero), patch)
    engine = ExperimentalEvidenceScoringEngine()
    p4 = engine.score(
        session.to_draft_state(), hero, data.evidence_by_role.for_role(session.role).evidence
    )
    session.set_role(Role.POSITION_5)
    p5 = engine.score(
        session.to_draft_state(), hero, data.evidence_by_role.for_role(session.role).evidence
    )
    session.set_role(Role.POSITION_4)
    restored = engine.score(
        session.to_draft_state(), hero, data.evidence_by_role.for_role(session.role).evidence
    )
    assert p4.experimental_score is not None
    assert p5.experimental_score is None
    assert restored.experimental_score == p4.experimental_score
    assert stratz.calls == [Role.POSITION_4, Role.POSITION_5]


def test_pair_rate_without_verified_effect_is_not_scored(hero, other_hero, patch) -> None:
    session = ManualDraftSession((hero, other_hero), patch)
    session.add_enemy(other_hero)
    pair = CounterEvidence(
        hero, other_hero, Role.POSITION_4, patch, 1000, _provenance(patch), pair_win_rate=0.9
    )
    result = ExperimentalEvidenceScoringEngine().score(
        session.to_draft_state(), hero, EvidenceSet(counters=(pair,))
    )
    assert result.experimental_score is None
    assert dict(result.components)["counter"] is None


@pytest.mark.parametrize("kind", ("meta", "counter", "synergy"))
def test_large_samples_have_greater_actual_component_influence(
    kind, hero, other_hero, patch
) -> None:
    ally = Hero(99, "ally", "Ally")
    session = ManualDraftSession((hero, other_hero, ally), patch)
    session.add_enemy(other_hero)
    session.add_ally(ally)

    def evidence(matches: int) -> EvidenceSet:
        if kind == "meta":
            return EvidenceSet(
                role_meta=(
                    RoleMetaEvidence(
                        hero,
                        Role.POSITION_4,
                        patch,
                        matches,
                        int(matches * 0.6),
                        0.6,
                        _provenance(patch),
                    ),
                )
            )
        if kind == "counter":
            return EvidenceSet(
                counters=(
                    CounterEvidence(
                        hero,
                        other_hero,
                        Role.POSITION_4,
                        patch,
                        matches,
                        _provenance(patch),
                        pair_win_rate=0.6,
                        effect=0.1,
                    ),
                )
            )
        return EvidenceSet(
            synergies=(
                SynergyEvidence(
                    hero,
                    ally,
                    Role.POSITION_4,
                    patch,
                    matches,
                    _provenance(patch),
                    pair_win_rate=0.6,
                    effect=0.1,
                ),
            )
        )

    small = ExperimentalEvidenceScoringEngine().score(session.to_draft_state(), hero, evidence(5))
    large = ExperimentalEvidenceScoringEngine().score(
        session.to_draft_state(), hero, evidence(50_000)
    )
    assert abs(dict(small.components)[kind] or 0) < abs(dict(large.components)[kind] or 0)


def test_missing_weights_are_fixed_and_familiarity_cannot_unlock_score(
    hero, other_hero, patch
) -> None:
    session = ManualDraftSession((hero, other_hero), patch)
    personal = PersonalHeroStat(hero, 1000, 1000, 1.0, None, _provenance(patch))
    familiarity_only = ExperimentalEvidenceScoringEngine().score(
        session.to_draft_state(), hero, EvidenceSet(), (personal,)
    )
    meta = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(hero, Role.POSITION_4, patch, 50_000, 30_000, 0.6, _provenance(patch)),
        )
    )
    with_meta = ExperimentalEvidenceScoringEngine().score(
        session.to_draft_state(), hero, meta, (personal,)
    )
    assert familiarity_only.experimental_score is None
    assert with_meta.experimental_score is not None
    assert with_meta.experimental_score < 60


def test_candidate_public_evidence_gate_is_per_candidate(hero, other_hero, patch) -> None:
    session = ManualDraftSession((hero, other_hero), patch)
    evidence = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(hero, Role.POSITION_4, patch, 1000, 600, 0.6, _provenance(patch)),
        )
    )
    ranked = ExperimentalEvidenceScoringEngine().rank(
        session.to_draft_state(), (hero, other_hero), evidence
    )
    by_id = {item.hero.hero_id: item for item in ranked}
    assert by_id[hero.hero_id].experimental_score is not None
    assert by_id[other_hero.hero_id].experimental_score is None


def test_confidence_reflects_public_component_coverage(hero, other_hero, patch) -> None:
    ally = Hero(99, "ally", "Ally")
    session = ManualDraftSession((hero, other_hero, ally), patch)
    session.add_enemy(other_hero)
    session.add_ally(ally)
    meta_only = EvidenceSet(
        role_meta=(
            RoleMetaEvidence(hero, Role.POSITION_4, patch, 50_000, 30_000, 0.6, _provenance(patch)),
        )
    )
    complete = EvidenceSet(
        role_meta=meta_only.role_meta,
        counters=(
            CounterEvidence(
                hero,
                other_hero,
                Role.POSITION_4,
                patch,
                50_000,
                _provenance(patch),
                pair_win_rate=0.6,
                effect=0.1,
            ),
        ),
        synergies=(
            SynergyEvidence(
                hero,
                ally,
                Role.POSITION_4,
                patch,
                50_000,
                _provenance(patch),
                pair_win_rate=0.6,
                effect=0.1,
            ),
        ),
    )
    engine = ExperimentalEvidenceScoringEngine()
    assert (
        engine.score(session.to_draft_state(), hero, complete).confidence
        > engine.score(session.to_draft_state(), hero, meta_only).confidence
    )
