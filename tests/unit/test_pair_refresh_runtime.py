import time
from datetime import date

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from dota_support_draft.domain import DraftState, Hero, HeroPick, Patch, Role, TeamSide
from dota_support_draft.draft.pair_evidence import (
    PairEvidenceContext,
    PairEvidenceInput,
    PairEvidenceResult,
)
from dota_support_draft.ui.pair_refresh import PairEvidenceRefreshController, PairRefreshState


def _input(identity: int) -> PairEvidenceInput:
    candidate, related = Hero(100 + identity, "candidate"), Hero(identity, "related")
    patch = Patch("p", "7.40", date(2026, 1, 1))
    draft = DraftState((HeroPick(related, TeamSide.ALLY),), (), Role.POSITION_4, patch)
    context = PairEvidenceContext(
        "7.40", Role.POSITION_4, (identity,), (), (candidate.hero_id,), None
    )
    return PairEvidenceInput(0, context, draft, (candidate,), None)


def _wait(app: QApplication, predicate, seconds: float = 3) -> None:
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


class SlowPairService:
    def __init__(self, delay: float = 0.12) -> None:
        self.delay, self.generations, self.threads = delay, [], []

    def refresh(self, input_data: PairEvidenceInput) -> PairEvidenceResult:
        self.generations.append(input_data.generation)
        self.threads.append(QThread.currentThread())
        time.sleep(self.delay)
        return PairEvidenceResult(input_data.generation, input_data.context)


def test_pair_worker_runs_off_gui_thread_and_heartbeat_continues() -> None:
    app = QApplication.instance() or QApplication([])
    service, applied, states = SlowPairService(), [], []
    current = [_input(1).context]
    controller = PairEvidenceRefreshController(
        service,
        lambda: current[0],
        lambda result: applied.append((result, QThread.currentThread())),
        lambda state, message: states.append(state),
        debounce_ms=0,
    )
    beats = [0]
    timer = QTimer()
    timer.timeout.connect(lambda: beats.__setitem__(0, beats[0] + 1))
    timer.start(10)
    controller.schedule(_input(1))
    _wait(app, lambda: bool(applied))
    timer.stop()
    assert service.threads[0] != app.thread()
    assert applied[0][1] == app.thread() and beats[0] > 0
    assert PairRefreshState.READY in states
    controller.stop()


def test_busy_refresh_keeps_only_latest_pending_and_discards_stale_result() -> None:
    app = QApplication.instance() or QApplication([])
    service, applied = SlowPairService(0.18), []
    current = [_input(1).context]
    controller = PairEvidenceRefreshController(
        service,
        lambda: current[0],
        lambda result: applied.append(result),
        lambda state, message: None,
        debounce_ms=0,
    )
    controller.schedule(_input(1))
    _wait(app, lambda: bool(service.generations))
    for identity in (2, 3, 4):
        current[0] = _input(identity).context
        controller.schedule(_input(identity))
    _wait(app, lambda: len(service.generations) == 2 and bool(applied))
    assert service.generations == [1, 4]
    assert len(applied) == 1 and applied[0].context == current[0]
    controller.stop()


def test_reset_like_no_related_context_invalidates_active_result() -> None:
    app = QApplication.instance() or QApplication([])
    service, applied = SlowPairService(0.12), []
    current = [_input(1).context]
    controller = PairEvidenceRefreshController(
        service,
        lambda: current[0],
        applied.append,
        lambda state, message: None,
        debounce_ms=0,
    )
    controller.schedule(_input(1))
    _wait(app, lambda: bool(service.generations))
    current[0] = None
    controller.schedule(
        PairEvidenceInput(
            0,
            PairEvidenceContext("7.40", Role.POSITION_4, (), (), (), None),
            _input(1).draft,
            (),
            None,
        )
    )
    _wait(app, lambda: controller.active_thread is None)
    assert applied == []
    controller.stop()


def test_stop_during_active_pair_refresh_has_bounded_wait() -> None:
    app = QApplication.instance() or QApplication([])
    service = SlowPairService(0.15)
    current = [_input(1).context]
    controller = PairEvidenceRefreshController(
        service, lambda: current[0], lambda result: None, lambda state, message: None, debounce_ms=0
    )
    controller.schedule(_input(1))
    _wait(app, lambda: bool(service.generations))
    controller.stop()
    _wait(app, lambda: controller.active_thread is None)


def test_shutdown_drops_active_result_pending_and_later_schedule() -> None:
    app = QApplication.instance() or QApplication([])
    service, applied, completed = SlowPairService(0.18), [], []
    first, pending, later = _input(1), _input(2), _input(3)
    current = [first.context]
    controller = PairEvidenceRefreshController(
        service,
        lambda: current[0],
        applied.append,
        lambda state, message: None,
        debounce_ms=0,
    )
    controller.schedule(first)
    _wait(app, lambda: service.generations == [1])
    current[0] = pending.context
    controller.schedule(pending)
    app.processEvents()
    assert controller.begin_shutdown(lambda: completed.append(QThread.currentThread()))
    controller.begin_shutdown(lambda: completed.append("replacement"))
    controller.schedule(later)
    _wait(app, lambda: controller.active_thread is None and len(completed) == 1)
    assert service.generations == [1]
    assert applied == []
    assert completed == [app.thread()]
    assert controller.findChildren(QThread) == []


def test_repeated_refreshes_retire_threads_without_accumulating_children() -> None:
    app = QApplication.instance() or QApplication([])
    service = SlowPairService(0.02)
    current = [_input(1).context]
    controller = PairEvidenceRefreshController(
        service, lambda: current[0], lambda result: None, lambda state, message: None, debounce_ms=0
    )
    for identity in range(1, 4):
        current[0] = _input(identity).context
        controller.schedule(_input(identity))
        _wait(
            app,
            lambda expected=identity: (
                controller.active_thread is None and len(service.generations) == expected
            ),
        )
        app.processEvents()
    assert controller.findChildren(QThread) == []
    controller.stop()
