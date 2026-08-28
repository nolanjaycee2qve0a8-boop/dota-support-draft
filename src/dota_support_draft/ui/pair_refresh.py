"""Qt lifecycle boundary for debounced, latest-state-wins pair evidence refreshes."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from dota_support_draft.draft import (
    DraftPairEvidenceService,
    PairEvidenceContext,
    PairEvidenceInput,
)
from dota_support_draft.draft.pair_evidence import PairEvidenceResult


class PairRefreshState(StrEnum):
    IDLE = "IDLE"
    DEBOUNCING = "DEBOUNCING"
    LOADING = "LOADING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class PairServiceProtocol(Protocol):
    def refresh(self, input_data: PairEvidenceInput) -> PairEvidenceResult: ...


class PairEvidenceWorker(QObject):  # type: ignore[misc]  # PySide6 QObject stub is incomplete.
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: PairServiceProtocol, input_data: PairEvidenceInput) -> None:
        super().__init__()
        self._service, self._input = service, input_data
        self.executing_thread: QThread | None = None

    @Slot()  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def run(self) -> None:
        self.executing_thread = QThread.currentThread()
        try:
            self.completed.emit(self._service.refresh(self._input))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class PairEvidenceRefreshController(QObject):  # type: ignore[misc]  # PySide6 QObject stub is incomplete.
    """One active worker plus one replaceable pending snapshot; HTTP is cooperative only."""

    DEBOUNCE_MS = 250

    def __init__(
        self,
        service: DraftPairEvidenceService,
        current_context: Callable[[], PairEvidenceContext | None],
        apply_result: Callable[[PairEvidenceResult], None],
        set_state: Callable[[PairRefreshState, str | None], None],
        debounce_ms: int = DEBOUNCE_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if debounce_ms < 0:
            raise ValueError("Debounce interval cannot be negative")
        self._service = service
        self._current_context, self._apply_result, self._set_state = (
            current_context,
            apply_result,
            set_state,
        )
        self._generation = 0
        self._pending: PairEvidenceInput | None = None
        self._active: PairEvidenceInput | None = None
        self._thread: QThread | None = None
        self._worker: PairEvidenceWorker | None = None
        self._shutting_down = False
        self._shutdown_complete: Callable[[], None] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._dispatch_latest)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def active_thread(self) -> QThread | None:
        return self._thread

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down

    def schedule(self, input_data: PairEvidenceInput) -> None:
        if self._shutting_down:
            return
        self._generation += 1
        input_data = PairEvidenceInput(
            self._generation,
            input_data.context,
            input_data.draft,
            input_data.shortlist,
            input_data.rank_bracket,
        )
        if not input_data.context.ally_ids and not input_data.context.enemy_ids:
            self._pending = None
            self._timer.stop()
            self._set_state(PairRefreshState.IDLE, None)
            return
        self._pending = input_data
        self._set_state(PairRefreshState.DEBOUNCING, None)
        self._timer.start()

    @Slot()  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def _dispatch_latest(self) -> None:
        if self._shutting_down or self._active is not None or self._pending is None:
            return
        input_data, self._pending = self._pending, None
        self._active = input_data
        self._set_state(PairRefreshState.LOADING, None)
        thread = QThread(self)
        worker = PairEvidenceWorker(self._service, input_data)
        self._thread, self._worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object)  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def _on_completed(self, result: object) -> None:
        pair_result = result if isinstance(result, PairEvidenceResult) else None
        if pair_result is not None and self._is_current(pair_result):
            self._apply_result(pair_result)
            if pair_result.counter_error and pair_result.synergy_error:
                self._set_state(
                    PairRefreshState.ERROR,
                    "Pair evidence unavailable; current-week Meta remains active",
                )
            elif pair_result.counter_error or pair_result.synergy_error:
                self._set_state(PairRefreshState.PARTIAL, "Pair evidence partial")
            else:
                self._set_state(PairRefreshState.READY, None)

    @Slot(str)  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def _on_failed(self, message: str) -> None:
        if (
            not self._shutting_down
            and self._active is not None
            and self._active.generation == self._generation
        ):
            self._set_state(PairRefreshState.ERROR, f"Pair evidence unavailable: {message}")

    @Slot()  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def _on_thread_finished(self) -> None:
        self._active = None
        self._thread = None
        self._worker = None
        if self._shutting_down:
            callback, self._shutdown_complete = self._shutdown_complete, None
            if callback is not None:
                QTimer.singleShot(0, callback)
        elif self._pending is not None:
            self._timer.start(0)

    def _is_current(self, result: PairEvidenceResult) -> bool:
        return (
            not self._shutting_down
            and result.generation == self._generation
            and result.context == self._current_context()
        )

    def begin_shutdown(self, on_complete: Callable[[], None] | None = None) -> bool:
        """Reject future work without blocking GUI; return whether a worker must retire first."""
        if self._shutting_down:
            if on_complete is not None and self._shutdown_complete is None:
                self._shutdown_complete = on_complete
            return self._active is not None
        self._shutting_down = True
        self._generation += 1
        self._pending = None
        self._timer.stop()
        self._shutdown_complete = on_complete
        self._set_state(PairRefreshState.SHUTTING_DOWN, "Finishing pair refresh before closing…")
        return self._active is not None

    def stop(self) -> None:
        """Application-controller hook; worker retirement remains cooperative and non-blocking."""
        self.begin_shutdown()
