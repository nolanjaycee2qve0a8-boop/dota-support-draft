from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from dota_support_draft.domain import Hero, PersonalHeroStat
from dota_support_draft.scoring import ExperimentalRecommendation


@dataclass(frozen=True, slots=True)
class CandidateRow:
    hero: Hero
    personal_matches: int | None
    personal_wins: int | None
    personal_win_rate: float | None
    status: str = "Eligible — scoring not enabled"
    experimental_score: float | None = None
    evidence_confidence: float | None = None
    explanation: str | None = None
    experimental_components: tuple[tuple[str, float | None], ...] = ()

    @property
    def display_name(self) -> str:
        return self.hero.localized_name or self.hero.canonical_name


class CandidateSortColumn(IntEnum):
    """Candidate table columns with type-aware, local display-order semantics."""

    HERO = 0
    EXPERIMENTAL_SCORE = 1
    CONFIDENCE = 2
    META = 3
    COUNTER = 4
    SYNERGY = 5
    PERSONAL = 6
    WHY = 7


def sort_candidate_rows(
    rows: tuple[CandidateRow, ...], column: CandidateSortColumn, descending: bool = False
) -> tuple[CandidateRow, ...]:
    """Sort local display rows; unavailable numeric evidence is always last and ties stay stable."""

    def component(row: CandidateRow, name: str) -> float | None:
        return dict(row.experimental_components).get(name)

    def value(row: CandidateRow) -> str | float | None:
        match column:
            case CandidateSortColumn.HERO:
                return row.display_name.casefold()
            case CandidateSortColumn.EXPERIMENTAL_SCORE:
                return row.experimental_score
            case CandidateSortColumn.CONFIDENCE:
                return row.evidence_confidence
            case CandidateSortColumn.META:
                return component(row, "meta")
            case CandidateSortColumn.COUNTER:
                return component(row, "counter")
            case CandidateSortColumn.SYNERGY:
                return component(row, "synergy")
            case CandidateSortColumn.PERSONAL:
                return component(row, "personal")
            case CandidateSortColumn.WHY:
                return (row.explanation or row.status).casefold()

    available = [row for row in rows if value(row) is not None]
    unavailable = [row for row in rows if value(row) is None]

    def available_value(row: CandidateRow) -> str | float:
        result = value(row)
        assert result is not None
        return result

    return tuple(sorted(available, key=available_value, reverse=descending) + unavailable)


def format_optional_count(value: int | None) -> str:
    return "—" if value is None else str(value)


def format_optional_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def format_player_status(
    player: object | None, personal_error: str | None
) -> tuple[str, str | None]:
    if player is None:
        return "Player: Not configured", personal_error
    availability = getattr(player, "availability", None)
    profile = getattr(player, "profile", None)
    if getattr(availability, "value", availability) == "PUBLIC":
        return (
            f"Player: {getattr(profile, 'display_name', None) or 'Public account'}",
            personal_error,
        )
    return "Player: Unavailable", personal_error


def build_candidate_rows(
    heroes: tuple[Hero, ...],
    personal_stats: tuple[PersonalHeroStat, ...] = (),
    recommendations: tuple[ExperimentalRecommendation, ...] = (),
) -> tuple[CandidateRow, ...]:
    by_id = {stat.hero.hero_id: stat for stat in personal_stats}
    recommendation_by_id = {item.hero.hero_id: item for item in recommendations}
    rows = tuple(
        CandidateRow(
            hero,
            stat.matches if stat else None,
            stat.wins if stat else None,
            stat.win_rate if stat else None,
            (
                "Experimental recommendation"
                if recommendation_by_id.get(hero.hero_id)
                and recommendation_by_id[hero.hero_id].experimental_score is not None
                else "Familiarity only — public recommendation evidence unavailable"
                if recommendation_by_id.get(hero.hero_id)
                else "Eligible — scoring not enabled"
            ),
            recommendation_by_id[hero.hero_id].experimental_score
            if hero.hero_id in recommendation_by_id
            else None,
            recommendation_by_id[hero.hero_id].confidence
            if hero.hero_id in recommendation_by_id
            else None,
            "; ".join(reason.explanation for reason in recommendation_by_id[hero.hero_id].reasons)
            if hero.hero_id in recommendation_by_id
            else None,
            recommendation_by_id[hero.hero_id].components
            if hero.hero_id in recommendation_by_id
            else (),
        )
        for hero in heroes
        for stat in (by_id.get(hero.hero_id),)
    )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.experimental_score is None,
                -(row.experimental_score or 0.0),
                -(row.personal_matches or 0),
                row.display_name.casefold(),
                row.hero.hero_id,
            ),
        )
    )


def filter_candidates(rows: tuple[CandidateRow, ...], query: str) -> tuple[CandidateRow, ...]:
    term = query.casefold().strip()
    return tuple(row for row in rows if term in row.display_name.casefold())
