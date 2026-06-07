from gateway.config import Config


def test_vikunja_config_defaults():
    c = Config()
    assert c.vikunja.base_url == ""
    assert c.vikunja.api_token == ""


def test_vikunja_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_VIKUNJA__BASE_URL", "https://vikunja.example.com")
    monkeypatch.setenv("GATEWAY_VIKUNJA__API_TOKEN", "tok-abc123")
    c = Config()
    assert c.vikunja.base_url == "https://vikunja.example.com"
    assert c.vikunja.api_token == "tok-abc123"
