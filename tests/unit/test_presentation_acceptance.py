from dataclasses import replace

import pytest

from dota_support_draft.domain import (
    Hero,
    PersonalHeroStat,
    PlayerAvailability,
    PlayerProfile,
    PlayerProfileState,
)
from dota_support_draft.draft.presentation import (
    CandidateRow,
    CandidateSortColumn,
    build_candidate_rows,
    filter_candidates,
    format_optional_count,
    format_optional_rate,
    format_player_status,
    sort_candidate_rows,
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


def _sortable_rows() -> tuple[CandidateRow, ...]:
    return (
        CandidateRow(
            Hero(1, "bravo", "Bravo"),
            None,
            None,
            None,
            experimental_score=0.6,
            evidence_confidence=0.5,
            explanation="Bravo why",
            experimental_components=(
                ("meta", 0.4),
                ("counter", None),
                ("synergy", 0.2),
                ("personal", 0.3),
            ),
        ),
        CandidateRow(
            Hero(2, "alpha", "Alpha"),
            None,
            None,
            None,
            experimental_score=0.2,
            evidence_confidence=0.3,
            explanation="Alpha why",
            experimental_components=(
                ("meta", None),
                ("counter", 0.8),
                ("synergy", 0.1),
                ("personal", None),
            ),
        ),
        CandidateRow(
            Hero(3, "charlie", "Charlie"),
            None,
            None,
            None,
            experimental_score=None,
            evidence_confidence=None,
            explanation="Charlie why",
            experimental_components=(
                ("meta", 0.2),
                ("counter", 0.1),
                ("synergy", None),
                ("personal", 0.2),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("column", "ascending", "descending"),
    (
        (CandidateSortColumn.HERO, (2, 1, 3), (3, 1, 2)),
        (CandidateSortColumn.EXPERIMENTAL_SCORE, (2, 1, 3), (1, 2, 3)),
        (CandidateSortColumn.CONFIDENCE, (2, 1, 3), (1, 2, 3)),
        (CandidateSortColumn.META, (3, 1, 2), (1, 3, 2)),
        (CandidateSortColumn.COUNTER, (3, 2, 1), (2, 3, 1)),
        (CandidateSortColumn.SYNERGY, (2, 1, 3), (1, 2, 3)),
        (CandidateSortColumn.PERSONAL, (3, 1, 2), (1, 3, 2)),
        (CandidateSortColumn.WHY, (2, 1, 3), (3, 1, 2)),
    ),
)
def test_candidate_sort_uses_typed_values_and_keeps_unavailable_last(
    column, ascending, descending
) -> None:
    rows = _sortable_rows()
    assert tuple(row.hero.hero_id for row in sort_candidate_rows(rows, column)) == ascending
    assert tuple(
        row.hero.hero_id for row in sort_candidate_rows(rows, column, descending=True)
    ) == (descending)


def test_candidate_sort_keeps_default_order_for_typed_value_ties() -> None:
    rows = _sortable_rows()
    tied_rows = (
        replace(rows[1], experimental_score=0.5),
        replace(rows[0], experimental_score=0.5),
        rows[2],
    )
    assert tuple(
        row.hero.hero_id
        for row in sort_candidate_rows(tied_rows, CandidateSortColumn.EXPERIMENTAL_SCORE)
    ) == (2, 1, 3)
