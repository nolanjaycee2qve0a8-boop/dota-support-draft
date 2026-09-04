"""Explicit local named manual-draft snapshots with no provider or network dependency."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from PySide6.QtCore import QSettings

from dota_support_draft.domain import DraftState, Hero, HeroPick, Patch, Role, TeamSide

SNAPSHOT_SCHEMA_VERSION = "dota-support-draft/local-snapshots/v1"
SNAPSHOT_STORE_KEY = "draft_snapshots/v1"
MAX_DRAFT_SNAPSHOTS = 10
MAX_SNAPSHOT_NAME_LENGTH = 48


@dataclass(frozen=True, slots=True)
class LocalDraftSnapshot:
    """A named, explicitly saved DraftState without presentation or evidence state."""

    name: str
    draft: DraftState


@dataclass(frozen=True, slots=True)
class SnapshotStoreRead:
    snapshots: tuple[LocalDraftSnapshot, ...]
    problem: str | None = None


class DraftSnapshotStore(Protocol):
    def load_snapshots(self) -> SnapshotStoreRead: ...

    def save_snapshot(self, snapshot: LocalDraftSnapshot) -> None: ...

    def delete_snapshot(self, name: str) -> None: ...


def normalize_snapshot_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("Enter a snapshot name.")
    if len(normalized) > MAX_SNAPSHOT_NAME_LENGTH:
        raise ValueError(f"Snapshot names must be at most {MAX_SNAPSHOT_NAME_LENGTH} characters.")
    if normalized in {".", ".."} or any(character in normalized for character in "\\/:"):
        raise ValueError("Snapshot names cannot contain path-like characters.")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError("Snapshot names cannot contain control characters.")
    return normalized


def _date_value(value: date | datetime) -> str:
    return value.isoformat()


def _encode(snapshot: LocalDraftSnapshot) -> dict[str, object]:
    draft = snapshot.draft
    return {
        "name": snapshot.name,
        "draft": {
            "patch": {
                "patch_id": draft.patch.patch_id,
                "version": draft.patch.version,
                "starts_at": _date_value(draft.patch.starts_at),
                "ends_at": _date_value(draft.patch.ends_at) if draft.patch.ends_at else None,
            },
            "intended_role": draft.intended_role.value,
            "allied_hero_ids": [pick.hero.hero_id for pick in draft.allied_picks],
            "enemy_hero_ids": [pick.hero.hero_id for pick in draft.enemy_picks],
            "banned_hero_ids": sorted(hero.hero_id for hero in draft.banned_heroes),
        },
    }


def _parse_date(value: object) -> date | datetime:
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value)
    return parsed.date() if "T" not in value else parsed


def _decode(item: object, heroes: dict[int, Hero]) -> LocalDraftSnapshot:
    if not isinstance(item, dict) or set(item) != {"name", "draft"}:
        raise ValueError
    if not isinstance(item["name"], str):
        raise ValueError
    name = normalize_snapshot_name(item["name"])
    raw_draft = item["draft"]
    if not isinstance(raw_draft, dict) or set(raw_draft) != {
        "patch",
        "intended_role",
        "allied_hero_ids",
        "enemy_hero_ids",
        "banned_hero_ids",
    }:
        raise ValueError
    raw_patch = raw_draft["patch"]
    if not isinstance(raw_patch, dict) or set(raw_patch) != {
        "patch_id",
        "version",
        "starts_at",
        "ends_at",
    }:
        raise ValueError
    if not all(isinstance(raw_patch[field], str) for field in ("patch_id", "version", "starts_at")):
        raise ValueError
    ends_at = raw_patch["ends_at"]
    if ends_at is not None and not isinstance(ends_at, str):
        raise ValueError
    patch = Patch(
        raw_patch["patch_id"],
        raw_patch["version"],
        _parse_date(raw_patch["starts_at"]),
        _parse_date(ends_at) if ends_at is not None else None,
    )
    if not isinstance(raw_draft["intended_role"], str):
        raise ValueError
    role = Role(raw_draft["intended_role"])

    def resolve(field: str) -> tuple[Hero, ...]:
        raw_ids = raw_draft[field]
        if not isinstance(raw_ids, list) or any(type(hero_id) is not int for hero_id in raw_ids):
            raise ValueError
        values = tuple(heroes[hero_id] for hero_id in raw_ids)
        if len(set(values)) != len(values) or any(not hero.is_active for hero in values):
            raise ValueError
        return values

    allies, enemies, banned = (
        resolve("allied_hero_ids"),
        resolve("enemy_hero_ids"),
        resolve("banned_hero_ids"),
    )
    if len(allies) > 5 or len(enemies) > 5:
        raise ValueError
    if set(allies) & set(enemies) or (set(allies) | set(enemies)) & set(banned):
        raise ValueError
    return LocalDraftSnapshot(
        name,
        DraftState(
            tuple(HeroPick(hero, TeamSide.ALLY) for hero in allies),
            tuple(HeroPick(hero, TeamSide.ENEMY) for hero in enemies),
            role,
            patch,
            banned_heroes=frozenset(banned),
        ),
    )


class QSettingsDraftSnapshotStore:
    """Current-user QSettings storage; listed metadata is inert until an explicit load confirm."""

    def __init__(self, heroes: tuple[Hero, ...], settings: QSettings | None = None) -> None:
        self._heroes = {hero.hero_id: hero for hero in heroes}
        self._settings = settings or QSettings(
            "Dota Support Draft Assistant", "Dota Support Draft Assistant"
        )

    def load_snapshots(self) -> SnapshotStoreRead:
        raw = self._settings.value(SNAPSHOT_STORE_KEY)
        if raw is None:
            return SnapshotStoreRead(())
        try:
            document = json.loads(str(raw))
            if not isinstance(document, dict) or set(document) != {"schema_version", "snapshots"}:
                raise ValueError
            if document["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
                raise ValueError
            raw_snapshots = document["snapshots"]
            if not isinstance(raw_snapshots, list) or len(raw_snapshots) > MAX_DRAFT_SNAPSHOTS:
                raise ValueError
            snapshots = tuple(_decode(item, self._heroes) for item in raw_snapshots)
            if len({snapshot.name for snapshot in snapshots}) != len(snapshots):
                raise ValueError
            return SnapshotStoreRead(snapshots)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return SnapshotStoreRead((), "Saved local snapshots are unavailable or incompatible.")

    def _write(self, snapshots: tuple[LocalDraftSnapshot, ...]) -> None:
        document = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshots": [_encode(snapshot) for snapshot in snapshots],
        }
        self._settings.setValue(SNAPSHOT_STORE_KEY, json.dumps(document, separators=(",", ":")))
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise RuntimeError("Local snapshot storage is unavailable.")

    def save_snapshot(self, snapshot: LocalDraftSnapshot) -> None:
        normalized = LocalDraftSnapshot(normalize_snapshot_name(snapshot.name), snapshot.draft)
        read = self.load_snapshots()
        if read.problem is not None:
            raise RuntimeError(read.problem)
        if any(existing.name == normalized.name for existing in read.snapshots):
            raise ValueError("A snapshot with that name already exists; choose a different name.")
        if len(read.snapshots) >= MAX_DRAFT_SNAPSHOTS:
            raise ValueError(f"Save up to {MAX_DRAFT_SNAPSHOTS} local snapshots; delete one first.")
        self._write((*read.snapshots, normalized))

    def delete_snapshot(self, name: str) -> None:
        normalized = normalize_snapshot_name(name)
        read = self.load_snapshots()
        if read.problem is not None:
            raise RuntimeError(read.problem)
        remaining = tuple(snapshot for snapshot in read.snapshots if snapshot.name != normalized)
        if len(remaining) == len(read.snapshots):
            raise ValueError("Select a saved snapshot first.")
        self._write(remaining)
