"""Fail-fast configuration. Validate every required secret at startup."""
import os
from dataclasses import dataclass

_REQUIRED = (
    "ANTHROPIC_API_KEY", "AGENTPHONE_API_KEY", "AGENTPHONE_WEBHOOK_SECRET",
    "BROWSER_USE_API_KEY", "ROBIN_AGENT_ID", "FROM_NUMBER_ID",
    "RECEPTIONIST_TO_NUMBER", "PUBLIC_BASE_URL",
)


class ConfigError(RuntimeError):
    """Raised at startup when a required environment variable is missing."""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    agentphone_api_key: str
    agentphone_webhook_secret: str
    browser_use_api_key: str
    robin_agent_id: str
    from_number_id: str
    receptionist_to_number: str
    public_base_url: str


def load_settings() -> Settings:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            "missing required environment variable(s): " + ", ".join(missing)
        )
    g = os.environ.__getitem__
    return Settings(
        anthropic_api_key=g("ANTHROPIC_API_KEY"),
        agentphone_api_key=g("AGENTPHONE_API_KEY"),
        agentphone_webhook_secret=g("AGENTPHONE_WEBHOOK_SECRET"),
        browser_use_api_key=g("BROWSER_USE_API_KEY"),
        robin_agent_id=g("ROBIN_AGENT_ID"),
        from_number_id=g("FROM_NUMBER_ID"),
        receptionist_to_number=g("RECEPTIONIST_TO_NUMBER"),
        public_base_url=g("PUBLIC_BASE_URL").rstrip("/"),
    )
