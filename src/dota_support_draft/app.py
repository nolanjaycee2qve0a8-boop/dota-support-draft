import os
import sys

from dota_support_draft.config import (
    QSettingsPlayerAccountPreferenceStore,
    Settings,
    resolve_player_account_id,
)
from dota_support_draft.draft.bootstrap import DraftBootstrapService
from dota_support_draft.draft.pair_evidence import DraftPairEvidenceService
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.opendota import OpenDotaProvider
from dota_support_draft.providers.stratz import StratzProvider
from dota_support_draft.ui.bootstrap_controller import ApplicationController


def main() -> int:
    from PySide6.QtWidgets import QApplication

    application = QApplication(sys.argv)
    settings = Settings.from_environment()
    player_preferences = QSettingsPlayerAccountPreferenceStore()
    player_account_id = resolve_player_account_id(os.environ, player_preferences)
    cache = DiskJsonCache(settings.cache_directory)
    stratz = StratzProvider(cache, settings.stratz_api_token)
    controller = ApplicationController(
        application,
        DraftBootstrapService(OpenDotaProvider(cache), stratz, settings.stratz_rank_bracket),
        player_account_id,
        DraftPairEvidenceService(stratz, settings.stratz_rank_bracket),
        player_preferences,
    )
    application.aboutToQuit.connect(controller.stop)
    controller.start()
    return int(application.exec())
