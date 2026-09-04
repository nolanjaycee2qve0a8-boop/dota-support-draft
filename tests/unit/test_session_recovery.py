from datetime import date

from PySide6.QtCore import QSettings

from dota_support_draft.config import QSettingsSessionRecoveryStore
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


def test_session_recovery_persists_only_draft_state_and_clear(tmp_path) -> None:
    session = _session()
    settings = QSettings(str(tmp_path / "recovery.ini"), QSettings.Format.IniFormat)
    store = QSettingsSessionRecoveryStore(session.heroes, settings)

    store.save_recovery(session.to_draft_state())
    recovery = store.load_recovery()

    assert recovery.problem is None and recovery.draft is not None and recovery.saved_at is not None
    assert recovery.draft.intended_role is Role.POSITION_5
    assert [pick.hero.hero_id for pick in recovery.draft.allied_picks] == [1]
    assert recovery.draft.allied_picks[0].team_position is TeamPosition.UNKNOWN
    raw = str(settings.value("session_recovery/v1"))
    assert all(value not in raw for value in ("STRATZ", "account", "SAFE", "POSITION_1"))

    store.clear_recovery()
    assert store.load_recovery().draft is None


def test_corrupt_session_recovery_is_inert_and_safe(tmp_path) -> None:
    session = _session()
    settings = QSettings(str(tmp_path / "recovery.ini"), QSettings.Format.IniFormat)
    settings.setValue("session_recovery/v1", "not-json")
    store = QSettingsSessionRecoveryStore(session.heroes, settings)

    recovery = store.load_recovery()

    assert recovery.draft is None
    assert recovery.problem == "Local session recovery is unavailable or incompatible."
