"""Explicit, local-only assessment for a pasted manual draft document."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from dota_support_draft.domain import DraftState, Hero, HeroPick, Patch, Role, TeamSide

MANUAL_IMPORT_SCHEMA_VERSION = "dota-support-draft/manual-import/v1"


class ManualImportStatus(StrEnum):
    PREVIEW = "PREVIEW"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ManualImportAssessment:
    """A validated replacement candidate that remains inert until the UI confirms it."""

    status: ManualImportStatus
    issue: str | None = None
    draft: DraftState | None = None
    observed_at: datetime | None = None

    @property
    def can_confirm(self) -> bool:
        return (
            self.status
            in {
                ManualImportStatus.PREVIEW,
                ManualImportStatus.NEEDS_CONFIRMATION,
            }
            and self.draft is not None
        )


class ManualImportError(ValueError):
    """A safe, concise validation error for a locally pasted document."""


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ManualImportError(f"Missing or invalid {name} object.")
    return value


def _hero_ids(value: object, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or any(type(hero_id) is not int for hero_id in value):
        raise ManualImportError(f"{name} hero IDs must be an integer array.")
    hero_ids = tuple(value)
    if len(hero_ids) != len(set(hero_ids)):
        raise ManualImportError(f"Duplicate {name} hero ID.")
    return hero_ids


def _observed_at(value: object) -> datetime | None:
    if value == "unknown":
        return None
    if not isinstance(value, str):
        raise ManualImportError(
            "observed_at must be a timezone-aware ISO-8601 timestamp or unknown."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManualImportError("Invalid observed_at timestamp.") from error
    if parsed.tzinfo is None:
        raise ManualImportError("observed_at must include a timezone.")
    return parsed.astimezone(UTC)


def _map_heroes(
    hero_ids: tuple[int, ...], catalog: dict[int, Hero], side_name: str
) -> tuple[Hero, ...]:
    heroes: list[Hero] = []
    for hero_id in hero_ids:
        hero = catalog.get(hero_id)
        if hero is None:
            raise ManualImportError(f"Unknown hero ID in {side_name} picks.")
        if not hero.is_active:
            raise ManualImportError(f"Inactive hero ID in {side_name} picks.")
        heroes.append(hero)
    return tuple(heroes)


def assess_pasted_manual_import(
    text: str,
    heroes: tuple[Hero, ...],
    patch: Patch,
    last_confirmed_observed_at: datetime | None = None,
) -> ManualImportAssessment:
    """Assess MANUAL_IMPORT/v1 text without mutating a session or starting any I/O."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ManualImportAssessment(ManualImportStatus.REJECTED, "Invalid JSON document.")
    try:
        document = _mapping(parsed, "document")
        if document.get("schema_version") != MANUAL_IMPORT_SCHEMA_VERSION:
            raise ManualImportError("Unsupported schema version.")
        provenance = _mapping(document.get("provenance"), "provenance")
        if provenance.get("kind") != "MANUAL_IMPORT":
            raise ManualImportError("Unsupported provenance kind.")
        observed_at = _observed_at(provenance.get("observed_at"))
        if last_confirmed_observed_at is not None and observed_at is not None:
            if observed_at <= last_confirmed_observed_at:
                raise ManualImportError(
                    "Stale snapshot; it is not newer than the last confirmed import."
                )
        draft = _mapping(document.get("draft"), "draft")
        if draft.get("complete") is not True:
            raise ManualImportError("Partial snapshots cannot replace the current draft.")
        if draft.get("patch_version") != patch.version:
            raise ManualImportError("Patch mismatch with the loaded draft data.")
        role_value = draft.get("intended_role")
        if role_value not in (Role.POSITION_4.value, Role.POSITION_5.value):
            raise ManualImportError("Only POSITION_4 or POSITION_5 is supported.")
        allied_ids = _hero_ids(draft.get("allied_hero_ids"), "Allied")
        enemy_ids = _hero_ids(draft.get("enemy_hero_ids"), "Enemy")
        banned_ids = _hero_ids(draft.get("banned_hero_ids"), "Banned")
        if len(allied_ids) > 5 or len(enemy_ids) > 5:
            raise ManualImportError("Allied and enemy picks each support at most five heroes.")
        if set(allied_ids) & set(enemy_ids):
            raise ManualImportError("A hero cannot be picked by both teams.")
        if (set(allied_ids) | set(enemy_ids)) & set(banned_ids):
            raise ManualImportError("A picked hero cannot also be banned.")
        catalog = {hero.hero_id: hero for hero in heroes}
        allies = _map_heroes(allied_ids, catalog, "allied")
        enemies = _map_heroes(enemy_ids, catalog, "enemy")
        banned = _map_heroes(banned_ids, catalog, "banned")
        preview = DraftState(
            tuple(HeroPick(hero, TeamSide.ALLY) for hero in allies),
            tuple(HeroPick(hero, TeamSide.ENEMY) for hero in enemies),
            Role(role_value),
            patch,
            banned_heroes=frozenset(banned),
        )
    except (ManualImportError, ValueError) as error:
        return ManualImportAssessment(ManualImportStatus.REJECTED, str(error))
    if observed_at is None:
        return ManualImportAssessment(
            ManualImportStatus.NEEDS_CONFIRMATION,
            "observed_at is unknown; review the preview before confirming.",
            preview,
        )
    return ManualImportAssessment(
        ManualImportStatus.PREVIEW,
        draft=preview,
        observed_at=observed_at,
    )
