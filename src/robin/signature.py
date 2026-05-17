"""Svix webhook signature verification — single chokepoint over raw bytes."""
from svix.webhooks import Webhook, WebhookVerificationError


class SignatureError(Exception):
    """Raised when the webhook signature is absent, malformed, or invalid."""


def verify_signature(raw_body: bytes, headers: dict[str, str], secret: str) -> bool:
    """Return True iff the Svix signature is valid; else raise SignatureError.

    `headers` is the inbound request headers as a plain dict (Svix needs
    svix-id / svix-timestamp / svix-signature; lookup is case-insensitive).
    `secret` is the whsec_… value from AGENTPHONE_WEBHOOK_SECRET.
    Verifies over the RAW request bytes — never a re-serialized body.
    """
    try:
        # Replay protection: Svix enforces a ±5-minute (300 s) timestamp
        # freshness window by default — stale or future-dated deliveries
        # are rejected here, guarding against replay attacks.
        Webhook(secret).verify(raw_body, headers)
    except WebhookVerificationError as exc:
        raise SignatureError("invalid webhook signature") from exc
    except UnicodeDecodeError as exc:
        # The underlying library decodes bytes to str before HMAC check;
        # non-UTF-8 bodies cannot carry a valid signature.
        raise SignatureError("invalid webhook signature") from exc  # same generic msg — no oracle
    return True
