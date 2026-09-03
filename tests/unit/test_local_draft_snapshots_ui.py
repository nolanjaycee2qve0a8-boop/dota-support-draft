from datetime import date

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget, QPushButton, QTableWidget

from dota_support_draft.config import LocalDraftSnapshot, SnapshotStoreRead, normalize_snapshot_name
from dota_support_draft.domain import Hero, Patch, PlannedLane, TeamPosition
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


class MemorySnapshotStore:
    def __init__(self) -> None:
        self.snapshots: tuple[LocalDraftSnapshot, ...] = ()

    def load_snapshots(self) -> SnapshotStoreRead:
        return SnapshotStoreRead(self.snapshots)

    def save_snapshot(self, snapshot: LocalDraftSnapshot) -> None:
        name = normalize_snapshot_name(snapshot.name)
        if any(existing.name == name for existing in self.snapshots):
            raise ValueError("A snapshot with that name already exists; choose a different name.")
        self.snapshots = (*self.snapshots, LocalDraftSnapshot(name, snapshot.draft))

    def delete_snapshot(self, name: str) -> None:
        self.snapshots = tuple(snapshot for snapshot in self.snapshots if snapshot.name != name)


class NoNetworkPairService:
    rank_bracket = None

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, _input_data: object) -> object:
        self.calls += 1
        raise AssertionError("Snapshot save/preview/delete must not request pair evidence")


def _button(window, name: str) -> QPushButton:
    button = window.findChild(QPushButton, name)
    assert button is not None
    return button


def test_explicit_local_snapshot_save_preview_cancel_load_delete_and_history_are_local() -> None:
    """Snapshots are inert until confirmed and use the normal one-step load."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one", "Hero One"), Hero(2, "hero_two", "Hero Two"))
    session = ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))
    session.add_ally(heroes[0])
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    store = MemorySnapshotStore()
    pair_service = NoNetworkPairService()
    window = create_main_window(
        session,
        pair_service=pair_service,  # type: ignore[arg-type]
        snapshot_store=store,
        pair_debounce_ms=10_000,
    )
    window.show()
    name = window.findChild(QLineEdit, "local-snapshot-name")
    saved = window.findChild(QListWidget, "local-snapshot-list")
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    controller = window.pair_refresh_controller
    assert name is not None and saved is not None and table is not None and search is not None
    assert controller is not None
    assert saved.count() == 0 and controller.generation == 0 and pair_service.calls == 0

    table.selectRow(0)
    _button(window, "add-candidate-comparison").click()
    search.setText("Hero Two")
    app.processEvents()
    assert (
        controller.generation == 0
        and pair_service.calls == 0
        and controller.findChildren(QThread) == []
    )
    search.clear()

    name.setText(" opening ")
    _button(window, "save-local-snapshot").click()
    assert [snapshot.name for snapshot in store.snapshots] == ["opening"]
    assert saved.count() == 1 and controller.generation == 0 and pair_service.calls == 0
    assert controller.findChildren(QThread) == []

    session.add_enemy(heroes[1])
    saved.setCurrentRow(0)
    _button(window, "preview-local-snapshot").click()
    _button(window, "cancel-local-snapshot-load").click()
    assert [hero.hero_id for hero in session.enemies] == [2]
    assert (
        controller.generation == 0
        and pair_service.calls == 0
        and controller.findChildren(QThread) == []
    )

    _button(window, "preview-local-snapshot").click()
    _button(window, "confirm-local-snapshot-load").click()
    assert [hero.hero_id for hero in session.allies] == [1] and session.enemies == []
    assert session.ally_assignments[heroes[0]] == (TeamPosition.POSITION_1, PlannedLane.SAFE)
    assert controller.generation == 1 and pair_service.calls == 0
    assert controller.findChildren(QThread) == []

    _button(window, "draft-undo-action").click()
    assert [hero.hero_id for hero in session.enemies] == [2]
    assert controller.generation == 2 and pair_service.calls == 0
    _button(window, "delete-local-snapshot").click()
    assert store.snapshots == () and saved.count() == 0
    assert (
        controller.generation == 2
        and pair_service.calls == 0
        and controller.findChildren(QThread) == []
    )
    app.processEvents()
    window.close()


def test_existing_snapshot_metadata_never_applies_at_window_start() -> None:
    """A startup list is informational; a user must still Preview then Confirm to load it."""
    _app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one", "Hero One"), Hero(2, "hero_two", "Hero Two"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    saved_session = ManualDraftSession(heroes, patch)
    saved_session.add_enemy(heroes[1])
    store = MemorySnapshotStore()
    store.snapshots = (LocalDraftSnapshot("saved enemy", saved_session.to_draft_state()),)
    current = ManualDraftSession(heroes, patch)
    current.add_ally(heroes[0])
    pair_service = NoNetworkPairService()
    window = create_main_window(
        current,
        pair_service=pair_service,  # type: ignore[arg-type]
        snapshot_store=store,
        pair_debounce_ms=10_000,
    )
    window.show()
    saved = window.findChild(QListWidget, "local-snapshot-list")
    controller = window.pair_refresh_controller
    assert saved is not None and controller is not None
    assert saved.count() == 1
    assert [hero.hero_id for hero in current.allies] == [1] and current.enemies == []
    assert (
        controller.generation == 0
        and pair_service.calls == 0
        and controller.findChildren(QThread) == []
    )
    window.close()
