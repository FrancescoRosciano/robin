"""Tests for the FastAPI composition root (app.py).

Uses Svix signing (same pattern as test_signature.py) — NOT hmac.
All secrets are synthetic and safe to commit.
"""
import base64
import json
from datetime import datetime, timezone

import httpx
import pytest
from svix.webhooks import Webhook

from robin.app import build_app

# Synthetic test secret — NOT a real credential; safe to commit.
SECRET = "whsec_" + base64.b64encode(b"robin-app-test-signing-key-32by!").decode()


def _svix_headers(body: bytes, secret: str = SECRET) -> dict:
    wh = Webhook(secret)
    now = datetime.now(timezone.utc)
    sig = wh.sign("msg_app_test", now, body.decode())
    return {
        "svix-id": "msg_app_test",
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": sig,
    }


@pytest.fixture
def app(tmp_path):
    law = tmp_path / "law.html"
    law.write_text("<html><body><h2 class='citation'>X</h2></body></html>")

    class _Msg:
        content = [{"type": "text", "text": "Hi, this is Robin."}]
        stop_reason = "end_turn"

    class _LLM:
        async def create(self, **kw):
            return _Msg()

    return build_app(secret=SECRET, law_html_path=str(law), llm=_LLM(),
                     tool_impls={})


async def test_healthz(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/healthz")
    assert r.status_code == 200


async def test_law_fixture_served(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/fixture/law.html")
    assert r.status_code == 200
    assert "citation" in r.text


async def test_webhook_rejects_bad_signature(app):
    transport = httpx.ASGITransport(app=app)
    body = json.dumps({"event": "agent.message", "channel": "voice",
                        "data": {"transcript": "hi"}}).encode()
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body,
                         headers={"svix-id": "x", "svix-timestamp": "1",
                                  "svix-signature": "v1,bad"})
    assert r.status_code == 401


async def test_webhook_streams_ndjson_on_valid_signature(app):
    transport = httpx.ASGITransport(app=app)
    body = json.dumps({"event": "agent.message", "channel": "voice",
                        "data": {"transcript": "hi"}}).encode()
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))
    assert r.status_code == 200
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines[0]["interim"] is True
    assert lines[-1]["text"] == "Hi, this is Robin."
