from dota_support_draft.domain import (
    Hero,
    PersonalHeroStat,
    PlayerAvailability,
    PlayerProfile,
    PlayerProfileState,
)
from dota_support_draft.draft.presentation import (
    build_candidate_rows,
    filter_candidates,
    format_optional_count,
    format_optional_rate,
    format_player_status,
)


def test_personal_history_join_and_order(provenance) -> None:
    a, b = Hero(1, "a", "Beta"), Hero(2, "b", "Alpha")
    rows = build_candidate_rows((a, b), (PersonalHeroStat(a, 2, 0, 0.0, None, provenance),))
    assert rows[0].hero is a and rows[1].personal_matches is None


def test_zero_values_remain_known(provenance) -> None:
    hero = Hero(1, "a")
    row = build_candidate_rows((hero,), (PersonalHeroStat(hero, 0, 0, 0.0, None, provenance),))[0]
    assert (row.personal_matches, row.personal_wins, row.personal_win_rate) == (0, 0, 0.0) and (
        format_optional_count(None),
        format_optional_count(0),
        format_optional_rate(0.0),
    ) == ("—", "0", "0%")


def test_search_is_trimmed_case_insensitive_and_empty() -> None:
    rows = build_candidate_rows((Hero(1, "a", "Alpha"),))
    assert filter_candidates(rows, " ALP ") and not filter_candidates(rows, "none")


def test_player_status_semantics(provenance) -> None:
    profile = PlayerProfileState(
        PlayerProfile("synthetic", "Name"), PlayerAvailability.PUBLIC, provenance
    )
    assert format_player_status(None, None)[0] == "Player: Not configured" and format_player_status(
        profile, "bad"
    ) == ("Player: Name", "bad")
