class ProviderError(RuntimeError):
    """Base class for explicit external-data failures."""


class ProviderTransportError(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class ProviderNotFound(ProviderError):
    pass


class ProviderMalformedResponse(ProviderError):
    pass


class PlayerDataUnavailable(ProviderError):
    pass


class ProviderCapabilityUnavailable(ProviderError):
    pass


class PatchResolutionError(ProviderError):
    pass
