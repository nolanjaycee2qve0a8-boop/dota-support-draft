import sys
from typing import Protocol, cast

from dota_support_draft.config import Settings
from dota_support_draft.draft.bootstrap import DraftBootstrapData, DraftBootstrapService
from dota_support_draft.draft.session import ManualDraftSession
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.opendota import OpenDotaProvider
from dota_support_draft.ui import create_main_window


class MainWindow(Protocol):
    def close(self) -> bool: ...
    def show(self) -> None: ...


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        message = "PySide6 is required for the desktop shell. Install project dependencies first."
        raise RuntimeError(message) from error
    from PySide6.QtCore import QObject, QThread, Signal

    class Loader(QObject):  # type: ignore[misc]  # Optional PySide6 has no installed type package here.
        ready = Signal(object)
        failed = Signal(str)

        def run(self) -> None:
            try:
                settings = Settings.from_environment()
                data = DraftBootstrapService(
                    OpenDotaProvider(DiskJsonCache(settings.cache_directory))
                ).load(settings.player_account_id)
                self.ready.emit(data)
            except Exception as error:
                self.failed.emit(str(error))

    application = QApplication(sys.argv)
    window = cast(MainWindow, create_main_window())
    window.show()
    thread = QThread()
    loader = Loader()
    loader.moveToThread(thread)
    windows = [window]

    # Keep both objects alive through the queued result transition and release them on finish.
    thread.finished.connect(loader.deleteLater)
    thread.finished.connect(thread.deleteLater)

    def show_ready(data: DraftBootstrapData) -> None:
        session = ManualDraftSession(data.heroes, data.patch)
        replacement = cast(
            MainWindow,
            create_main_window(
                session, data.personal_stats, player=data.player, personal_error=data.personal_error
            ),
        )
        windows.append(replacement)
        replacement.show()
        windows[0].close()
        thread.quit()

    def show_failure(message: str) -> None:
        replacement = cast(
            MainWindow, create_main_window(initial_status=f"Error loading OpenDota data: {message}")
        )
        windows.append(replacement)
        replacement.show()
        windows[0].close()
        thread.quit()

    thread.started.connect(loader.run)
    loader.ready.connect(show_ready)
    loader.failed.connect(show_failure)
    thread.start()

    # Avoid Qt destroying a still-running QThread if the user closes during bootstrap.
    def stop_worker() -> None:
        if thread.isRunning():
            thread.quit()
            thread.wait()

    application.aboutToQuit.connect(stop_worker)
    return int(application.exec())
