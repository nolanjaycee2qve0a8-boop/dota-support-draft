import pytest

from dota_support_draft.domain import DraftState, HeroPick, Role, TeamSide


def test_rejects_same_hero_on_both_teams(hero, patch) -> None:
    with pytest.raises(ValueError, match="both teams"):
        DraftState(
            (HeroPick(hero, TeamSide.ALLY),),
            (HeroPick(hero, TeamSide.ENEMY),),
            Role.POSITION_4,
            patch,
        )


def test_rejects_picked_candidate(hero, other_hero, patch) -> None:
    draft = DraftState((HeroPick(hero, TeamSide.ALLY),), (), Role.POSITION_4, patch)
    with pytest.raises(ValueError, match="Picked"):
        draft.validates_candidate(hero)
    draft.validates_candidate(other_hero)


def test_rejects_banned_candidate(hero, patch) -> None:
    draft = DraftState((), (), Role.POSITION_5, patch, banned_heroes=frozenset({hero}))
    with pytest.raises(ValueError, match="Banned"):
        draft.validates_candidate(hero)


def test_support_roles_remain_distinct(hero, patch) -> None:
    position_four = DraftState((), (), Role.POSITION_4, patch)
    position_five = DraftState((), (), Role.POSITION_5, patch)
    assert position_four.intended_role is not position_five.intended_role


def test_rejects_unsupported_role(hero, patch) -> None:
    with pytest.raises(ValueError):
        DraftState((), (), "SUPPORT", patch)  # type: ignore[arg-type]
