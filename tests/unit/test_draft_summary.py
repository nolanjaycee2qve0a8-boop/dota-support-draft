from datetime import date

from dota_support_draft.domain import (
    Hero,
    HeroPick,
    Patch,
    PlannedLane,
    Role,
    TeamPosition,
    TeamSide,
)
from dota_support_draft.draft import format_manual_draft_summary


def test_summary_contains_only_stable_manual_draft_context() -> None:
    patch = Patch("p", "7.40", date(2026, 1, 1))
    ally = Hero(1, "ally", "Ally")
    enemy = Hero(2, "enemy", "Enemy")
    ban_b = Hero(3, "ban_b", "Zulu")
    ban_a = Hero(4, "ban_a", "Alpha")
    from dota_support_draft.domain import DraftState

    summary = format_manual_draft_summary(
        DraftState(
            (
                HeroPick(
                    ally,
                    TeamSide.ALLY,
                    team_position=TeamPosition.POSITION_1,
                    planned_lane=PlannedLane.SAFE,
                ),
            ),
            (HeroPick(enemy, TeamSide.ENEMY),),
            Role.POSITION_5,
            patch,
            banned_heroes=frozenset((ban_b, ban_a)),
        )
    )

    assert summary == (
        "Manual draft summary — not auto-detected or authoritative game state.\n"
        "Patch: 7.40\n"
        "Intended role: Position 5\n"
        "Allied picks: Ally\n"
        "Enemy picks: Enemy\n"
        "Bans: Alpha, Zulu\n"
        "Manual ally context:\n"
        "- Ally: P1, Safe"
    )
    assert all(term not in summary.casefold() for term in ("token", "score", "evidence", "account"))


def test_empty_draft_summary_is_explicit_and_copyable() -> None:
    from dota_support_draft.domain import DraftState

    patch = Patch("p", "7.40", date(2026, 1, 1))
    summary = format_manual_draft_summary(DraftState((), (), Role.POSITION_4, patch))

    assert "Allied picks: none" in summary
    assert "Enemy picks: none" in summary
    assert "Bans: none" in summary
    assert "Manual ally context" not in summary
