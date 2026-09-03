from datetime import date

from PySide6.QtCore import QPoint, QRect, QThread
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTextEdit,
)

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


def _global_rect(widget) -> QRect:
    return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())


def _assert_not_overlapping(first, second) -> None:
    assert not _global_rect(first).intersects(_global_rect(second))


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


def test_expanded_snapshot_list_has_clickable_geometry_and_collapses_cleanly() -> None:
    """The explicitly expanded list keeps two saved snapshots visible and selectable."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one", "Hero One"), Hero(2, "hero_two", "Hero Two"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    ally_snapshot = ManualDraftSession(heroes, patch)
    ally_snapshot.add_ally(heroes[0])
    enemy_snapshot = ManualDraftSession(heroes, patch)
    enemy_snapshot.add_enemy(heroes[1])
    store = MemorySnapshotStore()
    store.snapshots = (
        LocalDraftSnapshot("ally opening", ally_snapshot.to_draft_state()),
        LocalDraftSnapshot("enemy opening", enemy_snapshot.to_draft_state()),
    )
    window = create_main_window(ManualDraftSession(heroes, patch), snapshot_store=store)
    window.resize(1200, 900)
    window.show()
    toggle = _button(window, "toggle-local-snapshots")
    saved = window.findChild(QListWidget, "local-snapshot-list")
    splitter = window.findChild(QSplitter, "draft-content-splitter")
    assert saved is not None and splitter is not None and not saved.isVisible()

    toggle.click()
    app.processEvents()
    assert saved.isVisible() and saved.height() >= 82 and saved.viewport().height() >= 70
    assert saved.count() == 2
    assert saved.visualItemRect(saved.item(0)).height() > 0
    assert saved.visualItemRect(saved.item(1)).height() > 0
    saved.setCurrentRow(1)
    assert saved.currentItem() is not None and "enemy opening" in saved.currentItem().text()
    assert _button(window, "preview-local-snapshot").isEnabled()
    assert _button(window, "delete-local-snapshot").isEnabled()

    toggle.click()
    app.processEvents()
    assert not saved.isVisible() and splitter.sizes()[1] == 0
    window.close()


def test_constrained_window_scrolls_without_snapshot_or_import_overlap() -> None:
    """A 664px-tall window scrolls instead of compressing expanded local sections."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one", "Hero One"), Hero(2, "hero_two", "Hero Two"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    first = ManualDraftSession(heroes, patch)
    first.add_ally(heroes[0])
    second = ManualDraftSession(heroes, patch)
    second.add_enemy(heroes[1])
    store = MemorySnapshotStore()
    store.snapshots = (
        LocalDraftSnapshot("first", first.to_draft_state()),
        LocalDraftSnapshot("second", second.to_draft_state()),
    )
    window = create_main_window(ManualDraftSession(heroes, patch), snapshot_store=store)
    window.resize(2559, 664)
    window.show()
    app.processEvents()
    toggle_snapshots = _button(window, "toggle-local-snapshots")
    toggle_snapshots.click()
    app.processEvents()

    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    saved = window.findChild(QListWidget, "local-snapshot-list")
    search = window.findChild(QLineEdit, "candidate-search")
    team_position = window.findChild(QComboBox, "ally-team-position")
    planned_lane = window.findChild(QComboBox, "ally-planned-lane")
    assert (
        scroll is not None
        and saved is not None
        and search is not None
        and team_position is not None
        and planned_lane is not None
    )
    assert scroll.verticalScrollBar().maximum() > 0
    assert saved.isVisible() and saved.height() >= 82 and saved.count() == 2

    snapshot_widgets = (
        window.findChild(QLineEdit, "local-snapshot-name"),
        saved,
        window.findChild(QLabel, "local-snapshot-status"),
        window.findChild(QPushButton, "save-local-snapshot"),
        window.findChild(QPushButton, "preview-local-snapshot"),
        window.findChild(QPushButton, "cancel-local-snapshot-load"),
        window.findChild(QPushButton, "confirm-local-snapshot-load"),
        window.findChild(QPushButton, "delete-local-snapshot"),
    )
    assert all(widget is not None and not widget.rect().isEmpty() for widget in snapshot_widgets)
    for widget in snapshot_widgets:
        assert widget is not None
        _assert_not_overlapping(widget, search)
        _assert_not_overlapping(widget, team_position)
        _assert_not_overlapping(widget, planned_lane)
    for index, widget in enumerate(snapshot_widgets):
        assert widget is not None
        for other in snapshot_widgets[index + 1 :]:
            assert other is not None
            _assert_not_overlapping(widget, other)

    toggle_snapshots.click()
    _button(window, "toggle-manual-import").click()
    app.processEvents()
    import_text = window.findChild(QTextEdit, "manual-import-text")
    import_validate = window.findChild(QPushButton, "validate-manual-import")
    assert import_text is not None and import_validate is not None
    _assert_not_overlapping(import_text, search)
    _assert_not_overlapping(import_text, team_position)
    _assert_not_overlapping(import_text, planned_lane)
    _assert_not_overlapping(import_validate, search)
    _assert_not_overlapping(import_validate, team_position)
    _assert_not_overlapping(import_validate, planned_lane)
    window.close()
