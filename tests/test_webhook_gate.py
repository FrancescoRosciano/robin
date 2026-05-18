"""Regression tests for app.py /webhook gate logic.

Pins the ROBIN_SKIP_WEBHOOK_VERIFY flag behaviour, signature rejection,
malformed-JSON handling, and happy-path NDJSON streaming.

How the skip flag works
-----------------------
`_SKIP_VERIFY` is read at module import time via `os.environ.get(...)`.
`build_app()` does NOT accept it as a parameter — the flag is a
module-level constant.  To toggle it between tests we must monkeypatch
the env var AND reload the module so the constant is re-evaluated, then
rebuild the app from the freshly-loaded module.

All secrets are synthetic.  No real Svix keys, no real telephony, no PII.
Phone numbers use +1555… space.
"""
import base64
import importlib
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from svix.webhooks import Webhook

# ---------------------------------------------------------------------------
# Synthetic test secret — NOT a real credential; safe to commit.
# ---------------------------------------------------------------------------
_SECRET = "whsec_" + base64.b64encode(b"robin-gate-test-key-32byteslong!").decode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svix_headers(body: bytes, secret: str = _SECRET) -> dict:
    """Generate valid Svix signature headers for the given body."""
    wh = Webhook(secret)
    now = datetime.now(timezone.utc)
    sig = wh.sign("msg_gate_test", now, body.decode())
    return {
        "svix-id": "msg_gate_test",
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": sig,
    }


def _valid_body(transcript: str = "cancel my gym membership") -> bytes:
    return json.dumps({
        "event": "agent.message",
        "channel": "voice",
        "data": {"transcript": transcript},
        "recentHistory": [],
    }).encode()


class _Msg:
    content = [{"type": "text", "text": "Robin here."}]
    stop_reason = "end_turn"


class _TrackingLLM:
    """Records whether create() was called."""
    def __init__(self):
        self.called = False

    async def create(self, *, system, messages, tools):
        self.called = True
        return _Msg()


def _build(monkeypatch, tmp_path, *, skip_verify: bool):
    """Reload robin.app with the env flag set/unset, return (app, llm)."""
    if skip_verify:
        monkeypatch.setenv("ROBIN_SKIP_WEBHOOK_VERIFY", "1")
    else:
        monkeypatch.delenv("ROBIN_SKIP_WEBHOOK_VERIFY", raising=False)

    import robin.app as app_mod
    importlib.reload(app_mod)

    law = tmp_path / "law.html"
    law.write_text("<html><body>law fixture</body></html>")

    llm = _TrackingLLM()
    app = app_mod.build_app(
        secret=_SECRET,
        law_html_path=str(law),
        llm=llm,
        tool_impls={},
        system_prompt="You are Robin.",
    )
    return app, llm


# ---------------------------------------------------------------------------
# 1. Skip flag ON — unsigned request still reaches the loop and streams 200
# ---------------------------------------------------------------------------

def test_skip_flag_on_unsigned_request_reaches_loop_and_streams_200(
        monkeypatch, tmp_path):
    # Arrange
    app, llm = _build(monkeypatch, tmp_path, skip_verify=True)
    body = _valid_body("cancel my gym")

    # Act — POST with NO Svix headers at all (completely unsigned)
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/webhook",
        content=body,
        headers={"content-type": "application/json"},
    )

    # Assert
    assert response.status_code == 200
    lines = [json.loads(ln) for ln in response.text.splitlines() if ln.strip()]
    assert lines[0]["interim"] is True
    assert llm.called, "LLM loop must have been invoked"


# ---------------------------------------------------------------------------
# 2. Skip flag OFF — bad signature → 401, loop NOT invoked
# ---------------------------------------------------------------------------

def test_skip_flag_off_bad_signature_returns_401_loop_not_invoked(
        monkeypatch, tmp_path):
    # Arrange
    app, llm = _build(monkeypatch, tmp_path, skip_verify=False)
    body = _valid_body("cancel my gym")

    # Act — deliberately wrong signature
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "svix-id": "msg_bad",
            "svix-timestamp": "1700000000",
            "svix-signature": "v1,badbadbadbadbadbadbadbadbadbadbadbadbadbad=",
        },
    )

    # Assert
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid signature"}
    assert not llm.called, "Loop must NOT be invoked on a bad signature"


# ---------------------------------------------------------------------------
# 3. Malformed JSON body (skip ON) → 400
# ---------------------------------------------------------------------------

def test_malformed_json_body_with_skip_on_returns_400(monkeypatch, tmp_path):
    # Arrange
    app, llm = _build(monkeypatch, tmp_path, skip_verify=True)
    body = b"this is not { json at all"

    # Act
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/webhook",
        content=body,
        headers={"content-type": "application/json"},
    )

    # Assert
    assert response.status_code == 400
    assert response.json() == {"detail": "bad request"}


# ---------------------------------------------------------------------------
# 4. Happy path — valid signature, valid JSON → 200 NDJSON stream
# ---------------------------------------------------------------------------

def test_happy_path_valid_signature_streams_ndjson(monkeypatch, tmp_path):
    # Arrange
    app, llm = _build(monkeypatch, tmp_path, skip_verify=False)
    body = _valid_body("I want to cancel my gym membership at 24 Hour Gym")

    # Act
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/webhook",
        content=body,
        headers=_svix_headers(body),
    )

    # Assert
    assert response.status_code == 200
    lines = [json.loads(ln) for ln in response.text.splitlines() if ln.strip()]
    assert len(lines) >= 2, "Must emit at least interim ack + final"
    assert lines[0]["interim"] is True
    final = lines[-1]
    assert "text" in final
    assert "interim" not in final


# ---------------------------------------------------------------------------
# 5. Wrong secret (skip OFF) → 401 (confirms secret is actually checked)
# ---------------------------------------------------------------------------

def test_wrong_secret_returns_401(monkeypatch, tmp_path):
    # Arrange — build app with _SECRET but sign with a different key
    app, llm = _build(monkeypatch, tmp_path, skip_verify=False)
    body = _valid_body("test")
    wrong_secret = "whsec_" + base64.b64encode(b"wrong-key-32-bytes-long-padding!").decode()

    # Act
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/webhook",
        content=body,
        headers=_svix_headers(body, secret=wrong_secret),
    )

    # Assert
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 6. Transcript extracted correctly from nested payload
# ---------------------------------------------------------------------------

def test_transcript_extracted_from_data_dict(monkeypatch, tmp_path):
    """Verify the webhook correctly reaches into data.transcript."""
    captured = {}

    class _CaptureLLM:
        async def create(self, *, system, messages, tools):
            captured["messages"] = messages
            return _Msg()

    if True:  # skip_verify for simplicity
        monkeypatch.setenv("ROBIN_SKIP_WEBHOOK_VERIFY", "1")
    import robin.app as app_mod
    importlib.reload(app_mod)
    law = tmp_path / "law.html"
    law.write_text("<html/>")
    app = app_mod.build_app(
        secret=_SECRET,
        law_html_path=str(law),
        llm=_CaptureLLM(),
        tool_impls={},
    )

    body = json.dumps({
        "event": "agent.message",
        "channel": "voice",
        "data": {"transcript": "Please cancel my account"},
        "recentHistory": [],
    }).encode()

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post("/webhook", content=body,
                           headers={"content-type": "application/json"})

    assert response.status_code == 200
    assert captured["messages"][-1]["content"] == "Please cancel my account"
