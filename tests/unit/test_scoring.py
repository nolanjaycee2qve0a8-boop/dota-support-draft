from datetime import date

import pytest

from dota_support_draft.domain import DraftState, HeroRoleStat, Patch, Role
from dota_support_draft.scoring import BaselineDraftScoringEngine


def test_recommendation_has_positive_and_negative_reasons(hero, patch) -> None:
    result = BaselineDraftScoringEngine().score(
        DraftState((), (), Role.POSITION_4, patch), hero, ()
    )
    assert {reason.polarity.value for reason in result.reasons} == {"positive", "negative"}


def test_scoring_is_deterministic(hero, patch) -> None:
    draft = DraftState((), (), Role.POSITION_4, patch)
    engine = BaselineDraftScoringEngine()
    assert engine.score(draft, hero, ()) == engine.score(draft, hero, ())


def test_patch_mismatch_is_detected(hero, patch, provenance) -> None:
    wrong_patch = Patch("7.39", "7.39", date(2026, 7, 1))
    stat = HeroRoleStat(hero, Role.POSITION_4, wrong_patch, 10, 5, 0.5, provenance)
    with pytest.raises(ValueError, match="patch mismatches"):
        BaselineDraftScoringEngine().score(
            DraftState((), (), Role.POSITION_4, patch), hero, (stat,)
        )
