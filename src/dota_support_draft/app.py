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

    def show_ready(data: DraftBootstrapData) -> None:
        session = ManualDraftSession(data.heroes, data.patch)
        replacement = cast(MainWindow, create_main_window(session, data.personal_stats))
        windows.append(replacement)
        windows[0].close()
        replacement.show()
        thread.quit()

    def show_failure(message: str) -> None:
        windows[0].close()
        replacement = cast(
            MainWindow, create_main_window(initial_status=f"Error loading OpenDota data: {message}")
        )
        windows.append(replacement)
        replacement.show()
        thread.quit()

    thread.started.connect(loader.run)
    loader.ready.connect(show_ready)
    loader.failed.connect(show_failure)
    thread.start()
    return int(application.exec())
