"""Offscreen confirmation regressions for the narrow saved-local-draft clear scope."""

from datetime import UTC, date, datetime

from PySide6.QtCore import QPoint, QRect, QThread
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QScrollArea, QWidget

from dota_support_draft.config import (
    LocalDraftSnapshot,
    QSettingsLocalDraftDataClearStore,
    SessionRecoveryRead,
    SnapshotStoreRead,
)
from dota_support_draft.config.draft_snapshots import SNAPSHOT_STORE_KEY
from dota_support_draft.config.session_recovery import SESSION_RECOVERY_STORE_KEY
from dota_support_draft.domain import DraftState, Hero, Patch, PlannedLane, TeamPosition
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


class MemorySnapshotStore:
    def __init__(self, snapshots: tuple[LocalDraftSnapshot, ...] = ()) -> None:
        self.snapshots = snapshots

    def load_snapshots(self) -> SnapshotStoreRead:
        return SnapshotStoreRead(self.snapshots)

    def save_snapshot(self, snapshot: LocalDraftSnapshot) -> None:
        self.snapshots = (*self.snapshots, snapshot)

    def delete_snapshot(self, name: str) -> None:
        self.snapshots = tuple(snapshot for snapshot in self.snapshots if snapshot.name != name)


class MemoryRecoveryStore:
    def __init__(self, draft: DraftState | None = None) -> None:
        self.draft = draft

    def load_recovery(self) -> SessionRecoveryRead:
        return SessionRecoveryRead(
            self.draft, datetime.now(UTC) if self.draft is not None else None
        )

    def save_recovery(self, draft: DraftState) -> None:
        self.draft = draft

    def clear_recovery(self) -> None:
        self.draft = None


class MemoryClearStore:
    def __init__(
        self, snapshots: MemorySnapshotStore, recovery: MemoryRecoveryStore, *, fail: bool = False
    ) -> None:
        self.snapshots, self.recovery, self.fail, self.calls = snapshots, recovery, fail, 0

    def clear_saved_local_draft_data(self) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("Saved local draft storage is unavailable; nothing was cleared.")
        self.snapshots.snapshots = ()
        self.recovery.draft = None


class NoNetworkPairService:
    rank_bracket = None

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, _input_data: object) -> object:
        self.calls += 1
        raise AssertionError("Clearing saved local draft data must not request pair evidence")


def _button(window: QWidget, object_name: str) -> QPushButton:
    button = window.findChild(QPushButton, object_name)
    assert button is not None
    return button


def _scroll_to_control(scroll: QScrollArea, widget: QWidget) -> None:
    contents = scroll.widget()
    assert contents is not None
    target_y = widget.mapTo(contents, QPoint(0, 0)).y()
    scroll.verticalScrollBar().setValue(
        min(max(target_y - 12, 0), scroll.verticalScrollBar().maximum())
    )
    QApplication.processEvents()
    viewport = QRect(scroll.viewport().mapToGlobal(QPoint(0, 0)), scroll.viewport().size())
    assert viewport.contains(QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size()))


def _window_with_saved_data():  # type: ignore[no-untyped-def]
    heroes = (Hero(1, "hero_one", "Hero One"), Hero(2, "hero_two", "Hero Two"))
    session = ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))
    session.add_ally(heroes[0])
    session.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    saved = LocalDraftSnapshot("local opening", session.to_draft_state())
    snapshots = MemorySnapshotStore((saved,))
    recovery = MemoryRecoveryStore(session.to_draft_state())
    clear_store = MemoryClearStore(snapshots, recovery)
    pair_service = NoNetworkPairService()
    window = create_main_window(
        session,
        snapshot_store=snapshots,
        recovery_store=recovery,
        draft_data_clear_store=clear_store,
        pair_service=pair_service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    return window, session, snapshots, recovery, clear_store, pair_service


def test_clear_saved_local_draft_data_requires_confirmation_and_preserves_current_state() -> None:
    """Cancel and close remain inert; only explicit confirmation clears the two saved records."""
    app = QApplication.instance() or QApplication([])
    window, session, snapshots, recovery, clear_store, pair_service = _window_with_saved_data()
    before = session.to_draft_state()
    window.resize(2559, 664)
    window.show()
    app.processEvents()
    search = window.findChild(QLineEdit, "candidate-search")
    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    confirmation = window.findChild(QWidget, "clear-saved-local-draft-data-confirmation")
    message = window.findChild(QLabel, "clear-saved-local-draft-data-message")
    clear_button = _button(window, "clear-saved-local-draft-data")
    confirm = _button(window, "confirm-clear-saved-local-draft-data")
    cancel = _button(window, "cancel-clear-saved-local-draft-data")
    controller = window.pair_refresh_controller
    assert (
        search is not None
        and scroll is not None
        and confirmation is not None
        and message is not None
        and controller is not None
    )
    search.setText("hero")
    _scroll_to_control(scroll, clear_button)
    clear_button.click()
    app.processEvents()
    assert confirmation.isVisible() and "1 named local snapshot(s)" in message.text()
    assert "local opening" not in message.text()
    _scroll_to_control(scroll, confirm)
    assert not QRect(clear_button.mapToGlobal(QPoint(0, 0)), clear_button.size()).intersects(
        QRect(confirmation.mapToGlobal(QPoint(0, 0)), confirmation.size())
    )
    cancel.click()
    assert not confirmation.isVisible() and clear_store.calls == 0
    assert snapshots.snapshots and recovery.draft is not None and session.to_draft_state() == before

    clear_button.click()
    window.close()
    assert clear_store.calls == 0 and snapshots.snapshots and recovery.draft is not None

    window.show()
    before_generation = controller.generation
    before_calls = pair_service.calls
    clear_button.click()
    confirm.click()
    app.processEvents()
    assert clear_store.calls == 1 and snapshots.snapshots == () and recovery.draft is None
    assert session.to_draft_state() == before and search.text() == "hero"
    assert (
        pair_service.calls == before_calls
        and controller.generation == before_generation
        and controller.active_thread is None
    )
    assert window.findChildren(QThread) == []
    window.close()


def test_clear_saved_local_draft_data_no_data_and_storage_failure_are_inert() -> None:
    """No-data and failed confirmation leave snapshots, recovery, draft, and workers untouched."""
    app = QApplication.instance() or QApplication([])
    window, session, snapshots, recovery, clear_store, pair_service = _window_with_saved_data()
    clear_store.fail = True
    before = session.to_draft_state()
    window.show()
    clear_button = _button(window, "clear-saved-local-draft-data")
    confirm = _button(window, "confirm-clear-saved-local-draft-data")
    status = window.findChild(QLabel, "clear-saved-local-draft-data-status")
    assert status is not None
    clear_button.click()
    confirm.click()
    app.processEvents()
    assert "nothing was cleared" in status.text().lower()
    assert clear_store.calls == 1 and snapshots.snapshots and recovery.draft is not None
    assert session.to_draft_state() == before and pair_service.calls == 0
    window.close()

    empty_snapshots = MemorySnapshotStore()
    empty_recovery = MemoryRecoveryStore()
    empty_clear = MemoryClearStore(empty_snapshots, empty_recovery)
    empty_window = create_main_window(
        ManualDraftSession(
            (Hero(1, "hero_one", "Hero One"),), Patch("p", "7.40", date(2026, 1, 1))
        ),
        snapshot_store=empty_snapshots,
        recovery_store=empty_recovery,
        draft_data_clear_store=empty_clear,
    )
    empty_window.show()
    _button(empty_window, "clear-saved-local-draft-data").click()
    empty_status = empty_window.findChild(QLabel, "clear-saved-local-draft-data-status")
    empty_confirmation = empty_window.findChild(
        QWidget, "clear-saved-local-draft-data-confirmation"
    )
    assert empty_status is not None and empty_confirmation is not None
    assert "Nothing was cleared" in empty_status.text() and not empty_confirmation.isVisible()
    assert empty_clear.calls == 0 and empty_window.findChildren(QThread) == []
    empty_window.close()


def test_qsettings_clear_helper_removes_only_exact_saved_draft_keys(tmp_path) -> None:
    """The storage helper must not use a group/prefix deletion that reaches unrelated settings."""
    from PySide6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "local-draft-data.ini"), QSettings.Format.IniFormat)
    settings.setValue(SNAPSHOT_STORE_KEY, "saved snapshots")
    settings.setValue(SESSION_RECOVERY_STORE_KEY, "saved recovery")
    settings.setValue("player/account_id", "123456")
    settings.setValue("unrelated/local-preference", "keep")
    settings.sync()

    QSettingsLocalDraftDataClearStore(settings).clear_saved_local_draft_data()

    assert not settings.contains(SNAPSHOT_STORE_KEY)
    assert not settings.contains(SESSION_RECOVERY_STORE_KEY)
    assert settings.value("player/account_id") == "123456"
    assert settings.value("unrelated/local-preference") == "keep"
