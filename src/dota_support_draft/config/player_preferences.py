"""Local public player-account preferences with no provider or network dependency."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from PySide6.QtCore import QSettings

PLAYER_ACCOUNT_ID_KEY = "player/account_id"
MAX_STEAM32_ACCOUNT_ID = 4_294_967_295


class PlayerAccountPreferenceStore(Protocol):
    """A local store for a public OpenDota/Steam32 account identifier."""

    def load_account_id(self) -> str | None: ...

    def save_account_id(self, account_id: str) -> str: ...

    def clear_account_id(self) -> None: ...


def normalize_player_account_id(account_id: str) -> str:
    """Return a canonical Steam32 account ID or raise a user-displayable error."""
    normalized = account_id.strip()
    if not normalized:
        raise ValueError("Enter a public numeric Steam32/OpenDota account ID.")
    if not normalized.isascii() or not normalized.isdecimal():
        raise ValueError(
            "Account ID must contain digits only; Steam64 IDs and names are not supported."
        )
    numeric_id = int(normalized)
    if not 1 <= numeric_id <= MAX_STEAM32_ACCOUNT_ID:
        raise ValueError("Account ID must be within the valid Steam32 numeric range.")
    return str(numeric_id)


class QSettingsPlayerAccountPreferenceStore:
    """Windows user-level QSettings-backed public account ID storage."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings(
            "Dota Support Draft Assistant", "Dota Support Draft Assistant"
        )

    def load_account_id(self) -> str | None:
        stored = self._settings.value(PLAYER_ACCOUNT_ID_KEY)
        if stored is None:
            return None
        try:
            return normalize_player_account_id(str(stored))
        except ValueError:
            return None

    def save_account_id(self, account_id: str) -> str:
        normalized = normalize_player_account_id(account_id)
        self._settings.setValue(PLAYER_ACCOUNT_ID_KEY, normalized)
        self._settings.sync()
        return normalized

    def clear_account_id(self) -> None:
        self._settings.remove(PLAYER_ACCOUNT_ID_KEY)
        self._settings.sync()


def resolve_player_account_id(
    environment: Mapping[str, str], preferences: PlayerAccountPreferenceStore
) -> str | None:
    """Resolve account identity with the environment override preceding local preferences."""
    environment_account_id = environment.get("DOTA_SUPPORT_ACCOUNT_ID")
    if environment_account_id is not None and environment_account_id.strip():
        return environment_account_id.strip()
    return preferences.load_account_id()
