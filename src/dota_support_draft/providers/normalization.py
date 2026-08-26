from dota_support_draft.domain import Hero
from dota_support_draft.providers.dto import ProviderHeroDTO


def normalize_hero(dto: ProviderHeroDTO) -> Hero:
    """Convert adapter-specific transport data into a provider-neutral domain Hero."""
    return Hero(dto.provider_id, dto.internal_name, dto.display_name, dto.active)
