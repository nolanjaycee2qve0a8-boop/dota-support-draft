from datetime import UTC, date, datetime

import pytest

from dota_support_draft.domain import DataProvenance, Hero, Patch


@pytest.fixture
def patch() -> Patch:
    return Patch("7.40", "7.40", date(2026, 8, 1))


@pytest.fixture
def provenance() -> DataProvenance:
    return DataProvenance(
        "fixture",
        datetime(2026, 8, 2, tzinfo=UTC),
        "unit test",
        "7.40",
        10,
        data_kind="TEST/FIXTURE",
    )


@pytest.fixture
def hero() -> Hero:
    return Hero(1, "npc_dota_hero_crystal_maiden", "Crystal Maiden")


@pytest.fixture
def other_hero() -> Hero:
    return Hero(2, "npc_dota_hero_witch_doctor", "Witch Doctor")
