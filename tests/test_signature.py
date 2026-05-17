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


# ---------------------------------------------------------------------------
# 5. Stale timestamp is rejected (replay-window protection)
# ---------------------------------------------------------------------------

def test_stale_timestamp_raises_signature_error() -> None:
    """A cryptographically valid signature with a stale timestamp is rejected.

    Svix enforces a ±5-minute (300 s) freshness window by default.
    A timestamp ~400 s in the past is outside that window and must be
    refused even though the HMAC itself is correct.
    """
    from datetime import timedelta

    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=400)
    wh = Webhook(TEST_SECRET)
    sig = wh.sign(_MSG_ID, stale_ts, _BODY.decode())
    headers: dict[str, str] = {
        "svix-id": _MSG_ID,
        "svix-timestamp": str(int(stale_ts.timestamp())),
        "svix-signature": sig,
    }
    with pytest.raises(SignatureError):
        verify_signature(_BODY, headers, TEST_SECRET)


# ---------------------------------------------------------------------------
# 6. Non-UTF-8 body raises SignatureError (UnicodeDecodeError branch coverage)
# ---------------------------------------------------------------------------

def test_non_utf8_body_raises_signature_error() -> None:
    """A body that is not valid UTF-8 must raise SignatureError.

    This exercises the except UnicodeDecodeError branch in verify_signature.
    Headers are plausibly shaped (correct key names, string values) — the
    body decode failure fires before any HMAC comparison.
    """
    bad_body = b"\xff\xfe\xff"  # invalid UTF-8 sequence
    # Build headers that look structurally valid (Svix will attempt to decode
    # the body before the HMAC check and hit UnicodeDecodeError).
    fake_headers: dict[str, str] = {
        "svix-id": _MSG_ID,
        "svix-timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "svix-signature": "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    with pytest.raises(SignatureError):
        verify_signature(bad_body, fake_headers, TEST_SECRET)
