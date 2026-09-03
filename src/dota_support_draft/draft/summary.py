"""Local, privacy-minimal text presentation for a manually entered draft."""

from __future__ import annotations

from dota_support_draft.domain import DraftState, Hero, PlannedLane, Role, TeamPosition


def _display_name(hero: Hero) -> str:
    return hero.localized_name or hero.canonical_name


def _hero_names(heroes: tuple[Hero, ...]) -> str:
    return ", ".join(_display_name(hero) for hero in heroes) or "none"


def format_manual_draft_summary(draft: DraftState) -> str:
    """Return stable local draft text without recommendations, accounts, or provider data."""
    role = "Position 4" if draft.intended_role is Role.POSITION_4 else "Position 5"
    lines = [
        "Manual draft summary — not auto-detected or authoritative game state.",
        f"Patch: {draft.patch.version}",
        f"Intended role: {role}",
        f"Allied picks: {_hero_names(tuple(pick.hero for pick in draft.allied_picks))}",
        f"Enemy picks: {_hero_names(tuple(pick.hero for pick in draft.enemy_picks))}",
        "Bans: "
        + _hero_names(
            tuple(
                sorted(
                    draft.banned_heroes,
                    key=lambda hero: (_display_name(hero).casefold(), hero.hero_id),
                )
            )
        ),
    ]
    assigned_allies = tuple(
        pick
        for pick in draft.allied_picks
        if pick.team_position is not TeamPosition.UNKNOWN
        or pick.planned_lane is not PlannedLane.UNKNOWN
    )
    if assigned_allies:
        lines.append("Manual ally context:")
        lines.extend(
            "- "
            + _display_name(pick.hero)
            + f": {pick.team_position.name.replace('POSITION_', 'P')}, "
            + pick.planned_lane.value.title()
            for pick in assigned_allies
        )
    return "\n".join(lines)
