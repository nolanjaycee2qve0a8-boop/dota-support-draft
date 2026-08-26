"""Named integration placeholders. No network requests exist in DOTA-001."""

from dota_support_draft.providers.base import DotaDataProvider


class OpenDotaProvider(DotaDataProvider):
    pass


class STRATZProvider(DotaDataProvider):
    pass


class StaticDataProvider(DotaDataProvider):
    pass
