import pytest
from robin import config

REQUIRED = [
    "ANTHROPIC_API_KEY", "AGENTPHONE_API_KEY", "AGENTPHONE_WEBHOOK_SECRET",
    "BROWSER_USE_API_KEY", "ROBIN_AGENT_ID", "FROM_NUMBER_ID",
    "RECEPTIONIST_TO_NUMBER", "PUBLIC_BASE_URL",
]


def _set_all(monkeypatch):
    for k in REQUIRED:
        monkeypatch.setenv(k, "x" if k != "RECEPTIONIST_TO_NUMBER" else "+15550000002")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")


def test_load_returns_settings_when_all_present(monkeypatch):
    _set_all(monkeypatch)
    s = config.load_settings()
    assert s.public_base_url == "https://example.test"
    assert s.receptionist_to_number == "+15550000002"


def test_missing_var_raises_naming_it(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("BROWSER_USE_API_KEY")
    with pytest.raises(config.ConfigError, match="BROWSER_USE_API_KEY"):
        config.load_settings()
