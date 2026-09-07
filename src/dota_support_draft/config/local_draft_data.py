"""Explicit, narrowly scoped deletion for saved local draft data only."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QSettings

from dota_support_draft.config.draft_snapshots import SNAPSHOT_STORE_KEY
from dota_support_draft.config.session_recovery import SESSION_RECOVERY_STORE_KEY


class LocalDraftDataClearStore(Protocol):
    """Deletes only the two approved saved-draft records after a UI confirmation."""

    def clear_saved_local_draft_data(self) -> None: ...


class QSettingsLocalDraftDataClearStore:
    """Remove exact saved-draft keys, restoring their prior values if the write fails."""

    _KEYS = (SNAPSHOT_STORE_KEY, SESSION_RECOVERY_STORE_KEY)

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings(
            "Dota Support Draft Assistant", "Dota Support Draft Assistant"
        )

    def clear_saved_local_draft_data(self) -> None:
        previous = {key: self._settings.value(key) for key in self._KEYS}
        for key in self._KEYS:
            self._settings.remove(key)
        self._settings.sync()
        if self._settings.status() == QSettings.Status.NoError:
            return

        for key, value in previous.items():
            if value is None:
                self._settings.remove(key)
            else:
                self._settings.setValue(key, value)
        self._settings.sync()
        raise RuntimeError("Saved local draft storage is unavailable; nothing was cleared.")
