from __future__ import annotations

from typing import Protocol, cast

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from dota_support_draft.config import PlayerAccountPreferenceStore, QSettingsDraftSnapshotStore
from dota_support_draft.draft.bootstrap import DraftBootstrapData, DraftBootstrapService
from dota_support_draft.draft.pair_evidence import DraftPairEvidenceService
from dota_support_draft.draft.session import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


class MainWindowProtocol(Protocol):
    def show(self) -> None: ...
    def close(self) -> bool: ...


class BootstrapWorker(QObject):  # type: ignore[misc]  # PySide6 QObject stub is incomplete.
    ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: DraftBootstrapService, account_id: str | None) -> None:
        super().__init__()
        self._service = service
        self._account_id = account_id
        self.executing_thread: QThread | None = None

    @Slot()  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def run(self) -> None:
        self.executing_thread = QThread.currentThread()
        try:
            self.ready.emit(self._service.load(self._account_id))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class ApplicationController(QObject):  # type: ignore[misc]  # PySide6 QObject stub is incomplete.
    def __init__(
        self,
        application: QApplication,
        service: DraftBootstrapService,
        account_id: str | None,
        pair_service: DraftPairEvidenceService | None = None,
        player_preferences: PlayerAccountPreferenceStore | None = None,
    ) -> None:
        super().__init__(application)
        self.loading: MainWindowProtocol = cast(MainWindowProtocol, create_main_window())
        self.replacement: MainWindowProtocol | None = None
        self.callback_thread: QThread | None = None
        self.thread = QThread(self)
        self.worker = BootstrapWorker(service, account_id)
        self.pair_service = pair_service
        self.player_preferences = player_preferences
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.ready.connect(self.on_ready, Qt.ConnectionType.QueuedConnection)
        self.worker.failed.connect(self.on_failed, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)

    def start(self) -> None:
        self.loading.show()
        self.thread.start()

    @Slot(object)  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def on_ready(self, data: object) -> None:
        bootstrap = cast(DraftBootstrapData, data)
        self.callback_thread = QThread.currentThread()
        self.replacement = cast(
            MainWindowProtocol,
            create_main_window(
                ManualDraftSession(bootstrap.heroes, bootstrap.patch),
                bootstrap.personal_stats,
                player=bootstrap.player,
                personal_error=bootstrap.personal_error,
                evidence_by_role=bootstrap.evidence_by_role,
                stratz_freshness_warning=(
                    bootstrap.stratz_freshness.message if bootstrap.stratz_freshness else None
                ),
                pair_service=self.pair_service,
                player_preferences=self.player_preferences,
                snapshot_store=QSettingsDraftSnapshotStore(bootstrap.heroes),
            ),
        )
        self.replacement.show()
        self.loading.close()

    @Slot(str)  # type: ignore[untyped-decorator]  # PySide6 Slot lacks typed decorator metadata.
    def on_failed(self, message: str) -> None:
        self.callback_thread = QThread.currentThread()
        self.replacement = cast(
            MainWindowProtocol,
            create_main_window(initial_status=f"Error loading OpenDota data: {message}"),
        )
        self.replacement.show()
        self.loading.close()

    def stop(self) -> None:
        if self.replacement is not None:
            controller = getattr(self.replacement, "pair_refresh_controller", None)
            if controller is not None:
                controller.stop()
        if self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(1500)
