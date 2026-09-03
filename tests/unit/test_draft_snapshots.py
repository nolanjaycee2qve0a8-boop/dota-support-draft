from datetime import date

import pytest
from PySide6.QtCore import QSettings

from dota_support_draft.config import (
    LocalDraftSnapshot,
    QSettingsDraftSnapshotStore,
    normalize_snapshot_name,
)
from dota_support_draft.domain import Hero, Patch, PlannedLane, Role, TeamPosition
from dota_support_draft.draft import ManualDraftSession


def _session() -> ManualDraftSession:
    heroes = (Hero(1, "hero_one"), Hero(2, "hero_two"), Hero(3, "hero_three"))
    session = ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))
    session.add_ally(heroes[0])
    session.add_enemy(heroes[1])
    session.ban(heroes[2])
    session.set_role(Role.POSITION_5)
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    return session


def test_qsettings_snapshot_store_persists_only_named_draft_state(tmp_path) -> None:
    session = _session()
    settings = QSettings(str(tmp_path / "snapshots.ini"), QSettings.Format.IniFormat)
    store = QSettingsDraftSnapshotStore(session.heroes, settings)

    store.save_snapshot(LocalDraftSnapshot("  lane plan  ", session.to_draft_state()))
    read = store.load_snapshots()

    assert read.problem is None and [snapshot.name for snapshot in read.snapshots] == ["lane plan"]
    snapshot = read.snapshots[0]
    assert snapshot.draft.intended_role is Role.POSITION_5
    assert [pick.hero.hero_id for pick in snapshot.draft.allied_picks] == [1]
    assert [pick.hero.hero_id for pick in snapshot.draft.enemy_picks] == [2]
    assert {hero.hero_id for hero in snapshot.draft.banned_heroes} == {3}
    assert snapshot.draft.allied_picks[0].team_position is TeamPosition.UNKNOWN
    assert snapshot.draft.allied_picks[0].planned_lane is PlannedLane.UNKNOWN
    raw = str(settings.value("draft_snapshots/v1"))
    assert all(secret not in raw for secret in ("STRATZ", "account", "SAFE", "POSITION_1"))

    store.delete_snapshot("lane plan")
    assert store.load_snapshots().snapshots == ()


@pytest.mark.parametrize("name", ("", "  ", "../draft", "folder\\draft", ".", "x" * 49))
def test_snapshot_names_are_bounded_and_not_paths(name: str) -> None:
    with pytest.raises(ValueError):
        normalize_snapshot_name(name)


def test_snapshot_store_rejects_duplicate_limit_and_corrupt_documents(tmp_path) -> None:
    session = _session()
    settings = QSettings(str(tmp_path / "snapshots.ini"), QSettings.Format.IniFormat)
    store = QSettingsDraftSnapshotStore(session.heroes, settings)
    store.save_snapshot(LocalDraftSnapshot("one", session.to_draft_state()))
    with pytest.raises(ValueError, match="already exists"):
        store.save_snapshot(LocalDraftSnapshot("one", session.to_draft_state()))
    for index in range(2, 11):
        store.save_snapshot(LocalDraftSnapshot(f"snapshot {index}", session.to_draft_state()))
    with pytest.raises(ValueError, match="up to 10"):
        store.save_snapshot(LocalDraftSnapshot("one too many", session.to_draft_state()))

    settings.setValue("draft_snapshots/v1", "not-json")
    assert store.load_snapshots().snapshots == ()
    assert (
        store.load_snapshots().problem == "Saved local snapshots are unavailable or incompatible."
    )
