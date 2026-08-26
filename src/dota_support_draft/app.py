import sys

from dota_support_draft.config import Settings
from dota_support_draft.draft.bootstrap import DraftBootstrapService
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.opendota import OpenDotaProvider
from dota_support_draft.ui.bootstrap_controller import ApplicationController


def main() -> int:
    from PySide6.QtWidgets import QApplication

    application = QApplication(sys.argv)
    settings = Settings.from_environment()
    controller = ApplicationController(
        application,
        DraftBootstrapService(OpenDotaProvider(DiskJsonCache(settings.cache_directory))),
        settings.player_account_id,
    )
    application.aboutToQuit.connect(controller.stop)
    controller.start()
    return int(application.exec())
