from datetime import date

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from dota_support_draft.config import normalize_player_account_id
from dota_support_draft.domain import Hero, Patch
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


class MemoryPlayerPreferences:
    def __init__(self) -> None:
        self.account_id: str | None = None

    def load_account_id(self) -> str | None:
        return self.account_id

    def save_account_id(self, account_id: str) -> str:
        self.account_id = normalize_player_account_id(account_id)
        return self.account_id

    def clear_account_id(self) -> None:
        self.account_id = None


class NoNetworkPairService:
    rank_bracket = None

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, _input_data: object) -> object:
        self.calls += 1
        raise AssertionError("Player configuration must not refresh pair evidence")


def _button(window, object_name: str) -> QPushButton:
    button = window.findChild(QPushButton, object_name)
    assert button is not None
    return button


def test_player_configuration_is_local_restart_required_and_zero_network() -> None:
    app = QApplication.instance() or QApplication([])
    preferences = MemoryPlayerPreferences()
    pair_service = NoNetworkPairService()
    heroes = (Hero(1, "hero_one", "Hero One"),)
    window = create_main_window(
        ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1))),
        pair_service=pair_service,  # type: ignore[arg-type]
        player_preferences=preferences,
    )
    window.show()
    account_input = window.findChild(QLineEdit, "player-account-input")
    config_status = window.findChild(QLabel, "player-config-status")
    application_status = window.findChild(QLabel, "application-status")
    assert (
        account_input is not None and config_status is not None and application_status is not None
    )

    account_input.setText("not-an-account")
    _button(window, "configure-player").click()
    assert preferences.account_id is None
    assert "digits only" in config_status.text()

    account_input.setText(" 123 ")
    _button(window, "configure-player").click()
    assert preferences.account_id == "123"
    assert "restart required" in config_status.text()
    assert "Player account saved" in application_status.text()
    assert "Public account" not in application_status.text()
    assert pair_service.calls == 0

    _button(window, "clear-player").click()
    assert preferences.account_id is None
    assert "restart required" in config_status.text()
    assert pair_service.calls == 0
    app.processEvents()
    window.close()
