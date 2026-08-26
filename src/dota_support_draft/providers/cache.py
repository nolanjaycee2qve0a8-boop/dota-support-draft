from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CachedJson:
    payload: Any
    retrieved_at: datetime
    from_cache: bool
    stale: bool = False


class DiskJsonCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def read(self, identity: str, ttl: timedelta) -> CachedJson | None:
        path = self._path(identity)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            retrieved_at = datetime.fromisoformat(raw["retrieved_at"])
            if retrieved_at.tzinfo is None or datetime.now(UTC) - retrieved_at > ttl:
                return None
            return CachedJson(raw["payload"], retrieved_at, from_cache=True)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def write(self, identity: str, payload: Any, retrieved_at: datetime) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(identity)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"retrieved_at": retrieved_at.isoformat(), "payload": payload}),
            encoding="utf-8",
        )
        os.replace(temporary, target)

    def _path(self, identity: str) -> Path:
        return self.directory / f"{hashlib.sha256(identity.encode()).hexdigest()}.json"
