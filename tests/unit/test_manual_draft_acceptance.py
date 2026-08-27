from datetime import date

import pytest

from dota_support_draft.domain import Hero, Role
from dota_support_draft.domain.models import Patch, TeamSide
from dota_support_draft.draft import ManualDraftError, ManualDraftSession


@pytest.fixture
def heroes() -> tuple[Hero, ...]:
    return tuple(Hero(i, f"hero_{i}", f"Hero {i}", i != 7) for i in range(1, 8))


@pytest.fixture
def session(heroes) -> ManualDraftSession:
    return ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))


def test_manual_session_starts_empty(session) -> None:
    assert not session.allies and not session.enemies and not session.bans


def test_manual_session_defaults_to_position_4(session) -> None:
    assert session.role is Role.POSITION_4


def test_manual_session_can_select_position_5(session) -> None:
    session.set_role(Role.POSITION_5)
    assert session.role is Role.POSITION_5


def test_invalid_runtime_role_rejected(session) -> None:
    with pytest.raises(ManualDraftError):
        session.set_role("SUPPORT")  # type: ignore[arg-type]


def test_add_ally(session, heroes) -> None:
    session.add_ally(heroes[0])
    assert session.allies == [heroes[0]]


def test_add_enemy(session, heroes) -> None:
    session.add_enemy(heroes[0])
    assert session.enemies == [heroes[0]]


def test_maximum_five_allies(session, heroes) -> None:
    for hero in heroes[:5]:
        session.add_ally(hero)
    with pytest.raises(ManualDraftError):
        session.add_ally(heroes[5])


def test_maximum_five_enemies(session, heroes) -> None:
    for hero in heroes[:5]:
        session.add_enemy(hero)
    with pytest.raises(ManualDraftError):
        session.add_enemy(heroes[5])


@pytest.mark.parametrize("action", ["add_ally", "add_enemy"])
def test_duplicate_pick_rejected(session, heroes, action) -> None:
    getattr(session, action)(heroes[0])
    with pytest.raises(ManualDraftError):
        getattr(session, action)(heroes[0])


def test_cross_team_duplicate_rejected(session, heroes) -> None:
    session.add_ally(heroes[0])
    with pytest.raises(ManualDraftError):
        session.add_enemy(heroes[0])


def test_ban_pick_conflicts(session, heroes) -> None:
    session.ban(heroes[0])
    with pytest.raises(ManualDraftError):
        session.add_ally(heroes[0])
    session.unban(heroes[0])
    session.add_enemy(heroes[0])
    with pytest.raises(ManualDraftError):
        session.ban(heroes[0])


def test_remove_and_unban_restore_candidates(session, heroes) -> None:
    session.add_ally(heroes[0])
    session.remove_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.remove_enemy(heroes[1])
    session.ban(heroes[2])
    session.unban(heroes[2])
    assert {heroes[0], heroes[1], heroes[2]} <= set(session.candidates)


def test_inactive_and_unknown_rejected(session, heroes) -> None:
    with pytest.raises(ManualDraftError):
        session.add_ally(heroes[6])
    with pytest.raises(ManualDraftError):
        session.add_ally(Hero(99, "unknown"))


def test_clear_preserves_role_and_patch(session, heroes) -> None:
    session.set_role(Role.POSITION_5)
    session.add_ally(heroes[0])
    session.ban(heroes[1])
    patch = session.patch
    session.clear()
    assert (
        session.role is Role.POSITION_5
        and session.patch is patch
        and not session.allies
        and not session.bans
    )


def test_candidates_are_deterministic(session) -> None:
    assert [hero.hero_id for hero in session.candidates] == sorted(
        hero.hero_id for hero in session.candidates
    )


def test_draft_state_preserves_sides_role_patch_bans(session, heroes) -> None:
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.ban(heroes[2])
    state = session.to_draft_state()
    assert (
        state.allied_picks[0].side is TeamSide.ALLY
        and state.enemy_picks[0].side is TeamSide.ENEMY
        and state.patch is session.patch
        and heroes[2] in state.banned_heroes
    )
