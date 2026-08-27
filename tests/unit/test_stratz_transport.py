import io
from urllib.error import HTTPError, URLError

import pytest

from dota_support_draft.providers import stratz
from dota_support_draft.providers.errors import (
    ProviderAuthenticationRequired,
    ProviderMalformedResponse,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderTransportError,
)
from dota_support_draft.providers.stratz import UrllibGraphQLTransport


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://api.stratz.com/graphql", code, "failure", None, io.BytesIO())


@pytest.mark.parametrize("status", (401, 403))
def test_unauthorized_http_statuses_are_typed(monkeypatch, status) -> None:
    monkeypatch.setattr(
        stratz, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(_http_error(status))
    )
    with pytest.raises(ProviderAuthenticationRequired):
        UrllibGraphQLTransport().post("query X { x }", {}, "token", 1)


def test_rate_limit_and_server_failure_are_typed(monkeypatch) -> None:
    monkeypatch.setattr(
        stratz, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(_http_error(429))
    )
    with pytest.raises(ProviderRateLimited):
        UrllibGraphQLTransport().post("query X { x }", {}, None, 1)
    monkeypatch.setattr(
        stratz, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(_http_error(500))
    )
    with pytest.raises(ProviderTransportError):
        UrllibGraphQLTransport().post("query X { x }", {}, None, 1)


def test_timeouts_are_typed(monkeypatch) -> None:
    monkeypatch.setattr(
        stratz, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError())
    )
    with pytest.raises(ProviderTimeout):
        UrllibGraphQLTransport().post("query X { x }", {}, None, 1)
    monkeypatch.setattr(
        stratz, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(URLError(TimeoutError()))
    )
    with pytest.raises(ProviderTimeout):
        UrllibGraphQLTransport().post("query X { x }", {}, None, 1)


class InvalidJsonResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b"not-json"


def test_invalid_json_is_typed(monkeypatch) -> None:
    monkeypatch.setattr(stratz, "urlopen", lambda *args, **kwargs: InvalidJsonResponse())
    with pytest.raises(ProviderMalformedResponse):
        UrllibGraphQLTransport().post("query X { x }", {}, None, 1)
