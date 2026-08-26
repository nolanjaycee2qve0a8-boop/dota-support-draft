from dota_support_draft.config import Settings


def test_secrets_only_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENDOTA_API_TOKEN", "local-token")
    assert Settings.from_environment().opendota_api_token == "local-token"
