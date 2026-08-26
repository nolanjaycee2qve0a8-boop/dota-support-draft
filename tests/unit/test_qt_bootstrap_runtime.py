import time
from datetime import date

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from dota_support_draft.domain import Hero, Patch
from dota_support_draft.draft.bootstrap import DraftBootstrapData
from dota_support_draft.ui.bootstrap_controller import ApplicationController


class SlowService:
    def __init__(self, fail: bool = False) -> None:
        self.fail, self.worker_thread = fail, None

    def load(self, account_id: str | None) -> DraftBootstrapData:
        self.worker_thread = QThread.currentThread()
        time.sleep(0.5)
        if self.fail:
            raise RuntimeError("fake failure")
        return DraftBootstrapData(Patch("p", "7.40", date(2026, 1, 1)), (Hero(1, "hero"),))


def wait(app: QApplication, predicate) -> None:
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_worker_and_gui_heartbeat_success() -> None:
    app = QApplication.instance() or QApplication([])
    service = SlowService()
    controller = ApplicationController(app, service, None)
    beats = [0]
    timer = QTimer()
    timer.timeout.connect(lambda: beats.__setitem__(0, beats[0] + 1))
    timer.start(25)
    controller.start()
    wait(
        app,
        lambda: (
            service.worker_thread is not None and beats[0] > 0 and controller.replacement is None
        ),
    )
    wait(app, lambda: controller.replacement is not None and not controller.thread.isRunning())
    timer.stop()
    assert (
        service.worker_thread != app.thread()
        and controller.callback_thread == app.thread()
        and not controller.loading.isVisible()
    )


def test_failure_transition_stays_on_gui_thread() -> None:
    app = QApplication.instance() or QApplication([])
    controller = ApplicationController(app, SlowService(True), None)
    controller.start()
    wait(app, lambda: controller.replacement is not None and not controller.thread.isRunning())
    assert controller.callback_thread == app.thread() and not controller.loading.isVisible()


def test_close_during_bootstrap_stops_thread_with_bounded_wait() -> None:
    app = QApplication.instance() or QApplication([])
    service = SlowService()
    controller = ApplicationController(app, service, None)
    controller.start()
    wait(app, lambda: service.worker_thread is not None and controller.thread.isRunning())
    controller.stop()
    wait(app, lambda: not controller.thread.isRunning())
    controller.loading.close()
