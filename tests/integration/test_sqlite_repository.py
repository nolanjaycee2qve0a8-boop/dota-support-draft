from dota_support_draft.domain import Hero
from dota_support_draft.repositories import HeroRepository, SQLiteDatabase


def test_hero_sqlite_round_trip(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "draft.sqlite")
    database.initialize()
    repository = HeroRepository(database)
    hero = Hero(88, "npc_dota_hero_disruptor", "Disruptor")
    repository.upsert(hero)
    assert repository.get(88) == hero
