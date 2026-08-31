from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from dota_support_draft.config import (
    QSettingsPlayerAccountPreferenceStore,
    normalize_player_account_id,
    resolve_player_account_id,
)
from dota_support_draft.domain import (
    DataProvenance,
    Hero,
    Patch,
    PlayerAvailability,
    PlayerProfile,
    PlayerProfileState,
)
from dota_support_draft.draft.bootstrap import DraftBootstrapService


class MemoryPlayerPreferences:
    def __init__(self, account_id: str | None = None) -> None:
        self.account_id = account_id

    def load_account_id(self) -> str | None:
        return self.account_id

    def save_account_id(self, account_id: str) -> str:
        self.account_id = normalize_player_account_id(account_id)
        return self.account_id

    def clear_account_id(self) -> None:
        self.account_id = None


class AccountCapturingProvider:
    def __init__(self) -> None:
        self.account_ids: list[str] = []
        self.patch = Patch("p", "7.40", date(2026, 1, 1))
        self.heroes = (Hero(1, "hero_one"),)
        self.provenance = DataProvenance(
            "fixture", datetime.now(UTC), "fixture", self.patch.version, data_kind="TEST/FIXTURE"
        )

    def get_current_patch(self) -> Patch:
        return self.patch

    def get_heroes(self) -> tuple[Hero, ...]:
        return self.heroes

    def get_player_profile_state(self, profile: PlayerProfile) -> PlayerProfileState:
        self.account_ids.append(profile.account_id)
        return PlayerProfileState(profile, PlayerAvailability.PUBLIC, self.provenance)

    def get_player_hero_stats(self, _profile: PlayerProfile) -> tuple[object, ...]:
        return ()


@pytest.mark.parametrize(
    ("account_id", "expected"),
    (("42", "42"), (" 0042 ", "42"), ("4294967295", "4294967295")),
)
def test_normalize_player_account_id_accepts_public_steam32_digits(
    account_id: str, expected: str
) -> None:
    assert normalize_player_account_id(account_id) == expected


@pytest.mark.parametrize("account_id", ("", " ", "0", "-1", "name", "4294967296"))
def test_normalize_player_account_id_rejects_invalid_or_unreasonable_values(
    account_id: str,
) -> None:
    with pytest.raises(ValueError):
        normalize_player_account_id(account_id)


def test_qsettings_player_preferences_save_read_and_clear_without_workspace_state(
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "player.ini"), QSettings.Format.IniFormat)
    preferences = QSettingsPlayerAccountPreferenceStore(settings)

    assert preferences.load_account_id() is None
    assert preferences.save_account_id(" 123 ") == "123"
    assert preferences.load_account_id() == "123"
    preferences.clear_account_id()
    assert preferences.load_account_id() is None


def test_environment_account_id_overrides_local_preference_and_clear_returns_none() -> None:
    preferences = MemoryPlayerPreferences("123")

    assert resolve_player_account_id({"DOTA_SUPPORT_ACCOUNT_ID": "456"}, preferences) == "456"
    assert resolve_player_account_id({}, preferences) == "123"
    preferences.clear_account_id()
    assert resolve_player_account_id({}, preferences) is None


def test_bootstrap_uses_saved_account_then_no_account_after_clear() -> None:
    preferences = MemoryPlayerPreferences("123")
    provider = AccountCapturingProvider()
    bootstrap = DraftBootstrapService(provider)  # type: ignore[arg-type]

    bootstrap.load(resolve_player_account_id({}, preferences))
    preferences.clear_account_id()
    bootstrap.load(resolve_player_account_id({}, preferences))

    assert provider.account_ids == ["123"]
