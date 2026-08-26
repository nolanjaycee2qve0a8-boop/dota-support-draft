"""Thin sqlite3 persistence boundary; no ORM is needed at this stage."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

from dota_support_draft.domain import Hero


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS heroes (
                    hero_id INTEGER PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    localized_name TEXT,
                    is_active INTEGER NOT NULL CHECK(is_active IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS patches (
                    patch_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT
                );
                """
            )


class HeroRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def upsert(self, hero: Hero) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO heroes(hero_id, canonical_name, localized_name, is_active)
                VALUES(:hero_id, :canonical_name, :localized_name, :is_active)
                ON CONFLICT(hero_id) DO UPDATE SET canonical_name=excluded.canonical_name,
                localized_name=excluded.localized_name, is_active=excluded.is_active""",
                {**asdict(hero), "is_active": int(hero.is_active)},
            )

    def get(self, hero_id: int) -> Hero | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM heroes WHERE hero_id = ?", (hero_id,)
            ).fetchone()
        if row is None:
            return None
        return Hero(
            row["hero_id"], row["canonical_name"], row["localized_name"], bool(row["is_active"])
        )


class PatchRepository:
    """Reserved storage contract for patch metadata."""


class RoleStatRepository:
    """Reserved storage contract for normalized role statistics."""


class MatchupRepository:
    """Reserved storage contract for normalized matchup statistics."""


class SynergyRepository:
    """Reserved storage contract for normalized synergy statistics."""


class PersonalStatsRepository:
    """Reserved storage contract for local personal-stat cache."""
