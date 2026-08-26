from datetime import date

import pytest

from dota_support_draft.domain import Hero, Patch, PersonalHeroStat, Role
from dota_support_draft.draft import (
    ManualDraftError,
    ManualDraftSession,
    build_candidate_rows,
    filter_candidates,
)


@pytest.fixture
def heroes() -> tuple[Hero, ...]:
    return tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 8))


@pytest.fixture
def session(heroes) -> ManualDraftSession:
    return ManualDraftSession(heroes, Patch("x", "7.40", date(2026, 1, 1)))


def test_session_invariants_and_draft_conversion(session, heroes) -> None:
    session.set_role(Role.POSITION_5)
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.ban(heroes[2])
    assert session.to_draft_state().intended_role is Role.POSITION_5
    assert {hero.hero_id for hero in session.candidates} == {4, 5, 6, 7}
    with pytest.raises(ManualDraftError):
        session.add_enemy(heroes[0])
    with pytest.raises(ManualDraftError):
        session.ban(heroes[1])


def test_max_removal_unban_and_search(session, heroes) -> None:
    for hero in heroes[:5]:
        session.add_ally(hero)
    with pytest.raises(ManualDraftError):
        session.add_ally(heroes[5])
    session.remove_ally(heroes[0])
    session.ban(heroes[0])
    session.unban(heroes[0])
    assert heroes[0] in session.candidates
    assert (
        filter_candidates(build_candidate_rows(session.candidates), "HERO 1")[0].hero == heroes[0]
    )


def test_personal_history_orders_without_role_claim(session, heroes, provenance) -> None:
    stats = (PersonalHeroStat(heroes[1], 10, 6, 0.6, None, provenance),)
    row = build_candidate_rows(heroes, stats)[0]
    assert row.hero == heroes[1] and row.personal_matches == 10 and "scoring not" in row.status
