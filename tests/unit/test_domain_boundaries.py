from datetime import UTC, datetime

import pytest

from dota_support_draft.domain import DataProvenance, PersonalHeroStat, Role
from dota_support_draft.providers.dto import ProviderHeroDTO
from dota_support_draft.providers.normalization import normalize_hero


def test_provenance_is_required() -> None:
    with pytest.raises(TypeError):
        DataProvenance()  # type: ignore[call-arg]


def test_provider_dto_is_normalized_before_domain_use() -> None:
    dto = ProviderHeroDTO(3, "npc_dota_hero_dazzle", "Dazzle", True)
    hero = normalize_hero(dto)
    assert hero.hero_id == dto.provider_id
    assert not hasattr(hero, "provider_id")


def test_personal_stat_expresses_long_and_recent_performance(hero, provenance) -> None:
    stat = PersonalHeroStat(
        hero, 100, 60, 0.6, 0.8, provenance, Role.POSITION_5, 12, 0.75, datetime.now(UTC)
    )
    assert (stat.matches, stat.recent_matches, stat.recent_win_rate) == (100, 12, 0.75)


def test_profile_identity_is_not_part_of_domain_defaults() -> None:
    from dota_support_draft.domain import PlayerProfile

    assert PlayerProfile("configured-by-user").account_id == "configured-by-user"
