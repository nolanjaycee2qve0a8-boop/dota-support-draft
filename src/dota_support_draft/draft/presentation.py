from __future__ import annotations

from dataclasses import dataclass

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
