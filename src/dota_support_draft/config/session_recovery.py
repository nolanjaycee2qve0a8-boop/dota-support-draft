"""One explicit local session-recovery DraftState with no network or evidence data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from PySide6.QtCore import QSettings

from dota_support_draft.config.draft_snapshots import LocalDraftSnapshot, _decode, _encode
from dota_support_draft.domain import DraftState, Hero

SESSION_RECOVERY_SCHEMA_VERSION = "dota-support-draft/session-recovery/v1"
SESSION_RECOVERY_STORE_KEY = "session_recovery/v1"


@dataclass(frozen=True, slots=True)
class SessionRecoveryRead:
    draft: DraftState | None = None
    saved_at: datetime | None = None
    problem: str | None = None


class SessionRecoveryStore(Protocol):
    def load_recovery(self) -> SessionRecoveryRead: ...

    def save_recovery(self, draft: DraftState) -> None: ...

    def clear_recovery(self) -> None: ...


class QSettingsSessionRecoveryStore:
    """Current-user recovery storage; metadata is inert until an explicit confirm."""

    def __init__(self, heroes: tuple[Hero, ...], settings: QSettings | None = None) -> None:
        self._heroes = {hero.hero_id: hero for hero in heroes}
        self._settings = settings or QSettings(
            "Dota Support Draft Assistant", "Dota Support Draft Assistant"
        )

    def load_recovery(self) -> SessionRecoveryRead:
        raw = self._settings.value(SESSION_RECOVERY_STORE_KEY)
        if raw is None:
            return SessionRecoveryRead()
        try:
            document = json.loads(str(raw))
            if not isinstance(document, dict) or set(document) != {
                "schema_version",
                "saved_at",
                "draft",
            }:
                raise ValueError
            if document["schema_version"] != SESSION_RECOVERY_SCHEMA_VERSION:
                raise ValueError
            saved_at = datetime.fromisoformat(document["saved_at"])
            if saved_at.tzinfo is None:
                raise ValueError
            snapshot = _decode({"name": "recovery", "draft": document["draft"]}, self._heroes)
            return SessionRecoveryRead(snapshot.draft, saved_at)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return SessionRecoveryRead(
                problem="Local session recovery is unavailable or incompatible."
            )

    def save_recovery(self, draft: DraftState) -> None:
        encoded = _encode(LocalDraftSnapshot("recovery", draft))
        document = {
            "schema_version": SESSION_RECOVERY_SCHEMA_VERSION,
            "saved_at": datetime.now(UTC).isoformat(),
            "draft": encoded["draft"],
        }
        self._settings.setValue(
            SESSION_RECOVERY_STORE_KEY, json.dumps(document, separators=(",", ":"))
        )
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise RuntimeError("Local session recovery storage is unavailable.")

    def clear_recovery(self) -> None:
        self._settings.remove(SESSION_RECOVERY_STORE_KEY)
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise RuntimeError("Local session recovery storage is unavailable.")
