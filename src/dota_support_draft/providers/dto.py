"""Provider adapter DTOs. These must not cross into domain consumers."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderHeroDTO:
    provider_id: int
    internal_name: str
    display_name: str | None
    active: bool
