from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    cache_directory: Path
    logging_level: str = "INFO"
    player_account_id: str | None = None
    opendota_api_token: str | None = None
    stratz_api_token: str | None = None
    stratz_rank_bracket: str | None = None

    @classmethod
    def from_environment(cls) -> Settings:
        root = Path(os.environ.get("DOTA_SUPPORT_DATA_DIR", ".dota-support-draft"))
        return cls(
            database_path=Path(os.environ.get("DOTA_SUPPORT_DATABASE", root / "draft.sqlite")),
            cache_directory=Path(os.environ.get("DOTA_SUPPORT_CACHE_DIR", root / "cache")),
            logging_level=os.environ.get("DOTA_SUPPORT_LOG_LEVEL", "INFO"),
            player_account_id=os.environ.get("DOTA_SUPPORT_ACCOUNT_ID"),
            opendota_api_token=os.environ.get("OPENDOTA_API_TOKEN"),
            stratz_api_token=os.environ.get("STRATZ_API_TOKEN"),
            stratz_rank_bracket=os.environ.get("STRATZ_RANK_BRACKET"),
        )
