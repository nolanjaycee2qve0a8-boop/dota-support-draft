from datetime import date

from PySide6.QtCore import QPoint, QRect, QThread
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
)

from dota_support_draft.config import SessionRecoveryRead
from dota_support_draft.domain import DraftState, Hero, Patch, PlannedLane, TeamPosition
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


class MemoryRecoveryStore:
    def __init__(self, draft: DraftState | None = None) -> None:
        self.draft = draft
        self.save_calls = 0
        self.clear_calls = 0

    def load_recovery(self) -> SessionRecoveryRead:
        return SessionRecoveryRead(self.draft)

    def save_recovery(self, draft: DraftState) -> None:
        self.save_calls += 1
        self.draft = draft

    def clear_recovery(self) -> None:
        self.clear_calls += 1
        self.draft = None


class NoNetworkPairService:
    rank_bracket = None

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, _input_data: object) -> object:
        self.calls += 1
        raise AssertionError("Session recovery must not perform pair network work directly")


def _button(window, name: str) -> QPushButton:
    button = window.findChild(QPushButton, name)
    assert button is not None
    return button


def _global_rect(widget) -> QRect:
    return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())


def test_session_recovery_is_inert_until_confirmed_and_tracks_only_draft_changes() -> None:
    """Recovery writes valid draft mutations, then restores only through Preview and Confirm."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one", "Hero One"), Hero(2, "hero_two", "Hero Two"))
    patch = Patch("p", "7.40", date(2026, 1, 1))
    original = ManualDraftSession(heroes, patch)
    original.add_ally(heroes[0])
    original.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    store = MemoryRecoveryStore()
    pair_service = NoNetworkPairService()
    window = create_main_window(
        original,
        recovery_store=store,
        pair_service=pair_service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    window.show()
    table = window.findChild(QTableWidget, "candidate-table")
    assert table is not None and window.pair_refresh_controller is not None
    table.selectRow(0)
    _button(window, "add-enemy").click()
    assert store.save_calls == 1 and store.draft is not None
    assert [pick.hero.hero_id for pick in store.draft.enemy_picks] == [2]
    assert pair_service.calls == 0 and window.pair_refresh_controller.findChildren(QThread) == []
    window.close()

    current = ManualDraftSession(heroes, patch)
    current.add_ally(heroes[0])
    current.set_ally_assignment(heroes[0], TeamPosition.POSITION_1, PlannedLane.SAFE)
    restored_pair_service = NoNetworkPairService()
    restored = create_main_window(
        current,
        recovery_store=store,
        pair_service=restored_pair_service,  # type: ignore[arg-type]
        pair_debounce_ms=10_000,
    )
    restored.show()
    status = restored.findChild(QLabel, "session-recovery-status")
    controller = restored.pair_refresh_controller
    assert status is not None and controller is not None
    assert [hero.hero_id for hero in current.allies] == [1] and current.enemies == []
    assert "available" in status.text().lower() and controller.generation == 0

    _button(restored, "preview-session-recovery").click()
    _button(restored, "cancel-session-recovery").click()
    assert current.enemies == [] and controller.generation == 0 and store.clear_calls == 0
    _button(restored, "preview-session-recovery").click()
    _button(restored, "confirm-session-recovery").click()
    assert [hero.hero_id for hero in current.enemies] == [2]
    assert current.ally_assignments[heroes[0]] == (TeamPosition.POSITION_1, PlannedLane.SAFE)
    assert controller.generation == 1 and restored_pair_service.calls == 0
    assert controller.findChildren(QThread) == []

    _button(restored, "draft-undo-action").click()
    assert current.enemies == [] and store.save_calls == 3 and controller.generation == 2
    _button(restored, "discard-session-recovery").click()
    assert store.draft is None and store.clear_calls == 1 and controller.generation == 2
    _button(restored, "reset-draft").click()
    assert store.draft is None and store.clear_calls == 2 and controller.generation == 3
    assert store.clear_calls == 2 and controller.generation == 3
    app.processEvents()
    restored.close()


def test_constrained_window_keeps_recovery_controls_separate_with_scrolling() -> None:
    """Recovery controls remain non-overlapping in the same constrained layout as snapshots."""
    app = QApplication.instance() or QApplication([])
    heroes = (Hero(1, "hero_one"), Hero(2, "hero_two"))
    window = create_main_window(
        ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1))),
        recovery_store=MemoryRecoveryStore(),
    )
    window.resize(2559, 664)
    window.show()
    _button(window, "toggle-local-snapshots").click()
    app.processEvents()
    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    search = window.findChild(QLineEdit, "candidate-search")
    position = window.findChild(QComboBox, "ally-team-position")
    lane = window.findChild(QComboBox, "ally-planned-lane")
    controls = (
        window.findChild(QLabel, "session-recovery-status"),
        window.findChild(QPushButton, "preview-session-recovery"),
        window.findChild(QPushButton, "cancel-session-recovery"),
        window.findChild(QPushButton, "confirm-session-recovery"),
        window.findChild(QPushButton, "discard-session-recovery"),
    )
    assert scroll is not None and scroll.verticalScrollBar().maximum() > 0
    assert search is not None and position is not None and lane is not None
    assert all(widget is not None and not widget.rect().isEmpty() for widget in controls)
    for index, widget in enumerate(controls):
        assert widget is not None
        assert not _global_rect(widget).intersects(_global_rect(search))
        assert not _global_rect(widget).intersects(_global_rect(position))
        assert not _global_rect(widget).intersects(_global_rect(lane))
        for other in controls[index + 1 :]:
            assert other is not None
            assert not _global_rect(widget).intersects(_global_rect(other))
    window.close()
