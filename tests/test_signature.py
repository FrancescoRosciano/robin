"""Tests for Svix webhook signature verification (TDD — write first, fail first).

The svix.webhooks.Webhook.sign(msg_id, timestamp, data_str) API is used to
construct valid signatures without hand-rolling any crypto.  All test secrets
are synthetic and safe to commit.
"""
import base64
import json
from datetime import datetime, timezone

import pytest
from svix.webhooks import Webhook

from robin.signature import SignatureError, verify_signature

# Synthetic test secret — NOT a real credential; safe to commit.
# whsec_ prefix + base64-encoded 32-byte key.
TEST_SECRET = "whsec_" + base64.b64encode(b"robin-unit-test-signing-key-32b!").decode()
OTHER_SECRET = "whsec_" + base64.b64encode(b"different-secret-key-for-tests!!").decode()

_BODY = json.dumps({"event": "agent.message", "data": {"transcript": "cancel my gym"}}).encode()
_MSG_ID = "msg_test_abc123"


def _valid_headers(body: bytes, secret: str = TEST_SECRET) -> dict:
    """Build a full set of svix headers for the given body and secret."""
    wh = Webhook(secret)
    now = datetime.now(timezone.utc)
    sig = wh.sign(_MSG_ID, now, body.decode())
    return {
        "svix-id": _MSG_ID,
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": sig,
    }


# ---------------------------------------------------------------------------
# 1. Valid signature passes
# ---------------------------------------------------------------------------

def test_valid_signature_returns_true() -> None:
    """A correctly signed request returns True."""
    headers = _valid_headers(_BODY)
    assert verify_signature(_BODY, headers, TEST_SECRET) is True


# ---------------------------------------------------------------------------
# 2. Tampered body fails
# ---------------------------------------------------------------------------

def test_tampered_body_raises_signature_error() -> None:
    """Mutating a single byte in the body invalidates the signature."""
    headers = _valid_headers(_BODY)
    tampered = bytearray(_BODY)
    tampered[0] ^= 0xFF  # flip bits in first byte
    with pytest.raises(SignatureError):
        verify_signature(bytes(tampered), headers, TEST_SECRET)


# ---------------------------------------------------------------------------
# 3. Missing signature header fails
# ---------------------------------------------------------------------------

def test_missing_signature_header_raises_signature_error() -> None:
    """Headers that lack svix-signature are rejected."""
    headers = _valid_headers(_BODY)
    headers.pop("svix-signature")
    with pytest.raises(SignatureError):
        verify_signature(_BODY, headers, TEST_SECRET)


# ---------------------------------------------------------------------------
# 4. Wrong secret fails
# ---------------------------------------------------------------------------

def test_wrong_secret_raises_signature_error() -> None:
    """A signature produced with a different secret must not verify."""
    # Sign with OTHER_SECRET, then try to verify against TEST_SECRET.
    headers = _valid_headers(_BODY, secret=OTHER_SECRET)
    with pytest.raises(SignatureError):
        verify_signature(_BODY, headers, TEST_SECRET)


# ---------------------------------------------------------------------------
# Extra: SignatureError wraps the underlying cause
# ---------------------------------------------------------------------------

def test_signature_error_chains_cause() -> None:
    """SignatureError should have a __cause__ set (WebhookVerificationError)."""
    headers = _valid_headers(_BODY, secret=OTHER_SECRET)
    with pytest.raises(SignatureError) as exc_info:
        verify_signature(_BODY, headers, TEST_SECRET)
    assert exc_info.value.__cause__ is not None
