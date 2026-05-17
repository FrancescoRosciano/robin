"""Svix webhook signature verification — single chokepoint over raw bytes."""
import json

from svix.webhooks import Webhook, WebhookVerificationError


class SignatureError(Exception):
    """Raised when the webhook signature is absent, malformed, or invalid."""


class MalformedJSONError(Exception):
    """Raised when the webhook body is validly signed but contains malformed JSON."""


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
    except json.JSONDecodeError as exc:
        # Svix's verify() parses JSON internally; trap decode errors
        # as a distinct exception to handle at the app layer.
        raise MalformedJSONError("malformed JSON in webhook body") from exc
    except WebhookVerificationError as exc:
        raise SignatureError("invalid webhook signature") from exc
    except UnicodeDecodeError as exc:
        # The underlying library decodes bytes to str before HMAC check;
        # non-UTF-8 bodies cannot carry a valid signature.
        raise SignatureError("invalid webhook signature") from exc  # same generic msg — no oracle
    return True
