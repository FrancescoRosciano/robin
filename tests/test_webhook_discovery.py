"""Tests for the call-receiver path: human calls Robin, AgentPhone POSTs each
voice turn to /webhook, Robin runs a discovery dialogue, streams NDJSON back.

All secrets are synthetic and safe to commit.
All phone numbers use +1555... (synthetic) to avoid real PII.
"""
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from svix.webhooks import Webhook

from robin.app import build_app
from robin.context_pack import load_context_pack
from robin.prompts import render_inbound_system_prompt
from tests.fakes import FakeLLM

# ---------------------------------------------------------------------------
# Synthetic test secret — NOT a real credential; safe to commit.
# ---------------------------------------------------------------------------
SECRET = "whsec_" + base64.b64encode(b"robin-recv-test-signing-key-32by!").decode()

FIXTURES = Path(__file__).parent / "fixtures"
CONTEXT_PACK_PATH = str(FIXTURES / "context_pack.valid.json")


def _svix_headers(body: bytes, secret: str = SECRET) -> dict:
    wh = Webhook(secret)
    now = datetime.now(timezone.utc)
    sig = wh.sign("msg_recv_test", now, body.decode())
    return {
        "svix-id": "msg_recv_test",
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": sig,
    }


def _text_msg(text: str, stop_reason: str = "end_turn"):
    """Build a minimal Anthropic-shaped message with one text block."""
    class _Msg:
        content = [{"type": "text", "text": text}]
    _Msg.stop_reason = stop_reason
    return _Msg()


def _tool_use_msg(tool_id: str, name: str, inp: dict):
    """Build an Anthropic-shaped message that requests one tool call."""
    class _Msg:
        content = [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}]
        stop_reason = "tool_use"
    return _Msg()


def _build_app(llm, tool_impls=None, system_prompt="You are Robin.",
               tmp_path=None):
    """Create a testable app with a temp law fixture file."""
    if tmp_path is None:
        import tempfile
        tmp = Path(tempfile.mkdtemp())
    else:
        tmp = tmp_path
    law = tmp / "law.html"
    law.write_text("<html><body><h2 class='citation'>X</h2></body></html>")
    return build_app(
        secret=SECRET,
        law_html_path=str(law),
        llm=llm,
        tool_impls=tool_impls or {},
        system_prompt=system_prompt,
    )


def _signed_body(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def _ndjson_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. Multi-turn discovery threads recentHistory into LLM messages
# ---------------------------------------------------------------------------

async def test_multi_turn_history_threads_into_llm_messages(tmp_path):
    """POST a turn with prior recentHistory; assert LLM sees correct roles
    and the NDJSON stream is well-formed (interim ack first, final last)."""
    llm = FakeLLM([_text_msg("24 Hour Gym — got it, I'll take care of it.")])
    app = _build_app(llm, tmp_path=tmp_path)

    history = [
        {"direction": "inbound", "content": "cancel my gym"},
        {"direction": "outbound", "content": "Which gym?"},
    ]
    payload = {
        "event": "agent.message",
        "channel": "voice",
        "recentHistory": history,
        "data": {"transcript": "24 Hour Gym"},
    }
    body = _signed_body(payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))

    assert r.status_code == 200

    # Verify LLM received correctly mapped roles
    assert len(llm.calls) == 1
    messages = llm.calls[0]["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "user"]
    assert messages[-1]["content"] == "24 Hour Gym"

    # Verify NDJSON stream: first line interim ack, last line final (no interim)
    lines = _ndjson_lines(r.text)
    assert lines[0]["interim"] is True
    assert "interim" not in lines[-1]
    assert lines[-1]["text"] == "24 Hour Gym — got it, I'll take care of it."


# ---------------------------------------------------------------------------
# 2. Discovery asks clarifying question then places a call (tool_use mid-dialogue)
# ---------------------------------------------------------------------------

async def test_tool_use_mid_dialogue_calls_stub_and_streams_correctly(tmp_path):
    """A tool_use turn followed by a final text turn exercises the full
    keepalive → tool → final path through the webhook endpoint."""
    tool_record: list[dict] = []

    async def place_negotiation_call(**kwargs):
        tool_record.append(kwargs)
        return {"status": "OK", "call_id": "call_fake_001"}

    llm = FakeLLM([
        _tool_use_msg("tu1", "place_negotiation_call",
                      {"caller_name": "Demo User", "jurisdiction": "US-CA"}),
        _text_msg("Calling them now."),
    ])
    app = _build_app(
        llm,
        tool_impls={"place_negotiation_call": place_negotiation_call},
        tmp_path=tmp_path,
    )

    payload = {
        "event": "agent.message",
        "channel": "voice",
        "recentHistory": [],
        "data": {"transcript": "yes please call them"},
    }
    body = _signed_body(payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))

    assert r.status_code == 200
    lines = _ndjson_lines(r.text)

    # First line must be the interim ack
    assert lines[0]["interim"] is True

    # At least one keepalive interim line must appear between first and last
    middle = lines[1:-1]
    keepalives = [ln for ln in middle if ln.get("interim") is True]
    assert len(keepalives) >= 1, "expected at least one keepalive interim line"

    # Final line must be the LLM text with no interim key
    assert "interim" not in lines[-1]
    assert lines[-1]["text"] == "Calling them now."

    # Tool stub must have been awaited with the model's input
    assert len(tool_record) == 1
    assert tool_record[0]["caller_name"] == "Demo User"
    assert tool_record[0]["jurisdiction"] == "US-CA"


# ---------------------------------------------------------------------------
# 3. Real inbound discovery system prompt drives the call
# ---------------------------------------------------------------------------

async def test_real_inbound_system_prompt_reaches_llm(tmp_path):
    """build_app wired with render_inbound_system_prompt(load_context_pack(...))
    must deliver the fully rendered (no {{ }} slots) prompt as system= to LLM."""
    pack = load_context_pack(CONTEXT_PACK_PATH)
    system = render_inbound_system_prompt(pack)

    # Sanity: rendered prompt has no unfilled slots
    assert "{{" not in system and "}}" not in system

    llm = FakeLLM([_text_msg("Discovery response.")])
    app = _build_app(llm, system_prompt=system, tmp_path=tmp_path)

    payload = {
        "event": "agent.message",
        "channel": "voice",
        "recentHistory": [],
        "data": {"transcript": "I want to cancel my gym membership"},
    }
    body = _signed_body(payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))

    assert r.status_code == 200
    assert len(llm.calls) == 1
    received_system = llm.calls[0]["system"]
    assert received_system == system
    assert "{{" not in received_system
    assert "}}" not in received_system
    # Spot-check that context pack values were injected
    assert pack.caller_name in received_system
    assert pack.target_name in received_system
    assert pack.jurisdiction in received_system


# ---------------------------------------------------------------------------
# 4. Payload robustness through the real signed path (parametrize)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload_override,label", [
    ({"event": "agent.message", "channel": "voice"}, "missing_data"),
    ({"event": "agent.message", "channel": "voice", "data": {}}, "missing_transcript"),
    ({"event": "agent.message", "channel": "voice", "recentHistory": [],
      "data": {"transcript": ""}}, "empty_transcript"),
    ({"event": "agent.message", "channel": "voice", "recentHistory": [],
      "data": {"transcript": "hello"}}, "empty_history"),
])
async def test_robustness_graceful_200_with_ndjson(payload_override, label,
                                                    tmp_path):
    """Validly-signed payloads with missing/empty fields must yield 200 and a
    well-formed NDJSON stream that starts with the interim ack (no 500s)."""
    llm = FakeLLM([_text_msg("Robin here, how can I help?")])
    app = _build_app(llm, tmp_path=tmp_path)

    body = _signed_body(payload_override)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))

    assert r.status_code == 200, f"expected 200 for case={label}, got {r.status_code}"
    lines = _ndjson_lines(r.text)
    assert len(lines) >= 1, f"expected at least one NDJSON line for case={label}"
    assert lines[0].get("interim") is True, (
        f"first line must be interim ack for case={label}"
    )


# ---------------------------------------------------------------------------
# 5. Signature / JSON failures still enforced on the receiver path
# ---------------------------------------------------------------------------

async def test_bad_signature_returns_401(tmp_path):
    """A request with an invalid signature must be rejected before any logic."""
    llm = FakeLLM([_text_msg("Should not be reached.")])
    app = _build_app(llm, tmp_path=tmp_path)

    body = json.dumps({"event": "agent.message", "data": {"transcript": "hi"}}).encode()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/webhook", content=body,
            headers={"svix-id": "x", "svix-timestamp": "1",
                     "svix-signature": "v1,badsig"},
        )

    assert r.status_code == 401
    assert r.json() == {"detail": "invalid signature"}
    assert len(llm.calls) == 0, "LLM must not be invoked on rejected request"


async def test_validly_signed_non_json_returns_400(tmp_path):
    """Validly signed but non-JSON body must be rejected as bad request."""
    llm = FakeLLM([_text_msg("Should not be reached.")])
    app = _build_app(llm, tmp_path=tmp_path)

    body = b"this is not json"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))

    assert r.status_code == 400
    assert r.json() == {"detail": "bad request"}
    assert len(llm.calls) == 0, "LLM must not be invoked on malformed body"


# ---------------------------------------------------------------------------
# 6. Six-turn tool cap is observable to the caller
# ---------------------------------------------------------------------------

async def test_six_turn_tool_cap_terminates_stream(tmp_path):
    """Eight consecutive tool_use msgs from LLM must cause the loop to cap
    at exactly 6 LLM calls and emit a non-interim final chunk to the caller."""
    call_count = 0

    async def no_op_tool(**kwargs):
        nonlocal call_count
        call_count += 1
        return {"status": "OK"}

    scripted = [
        _tool_use_msg(f"t{i}", "research_cancellation_law", {"jurisdiction": "US-CA"})
        for i in range(8)
    ]
    llm = FakeLLM(scripted)
    app = _build_app(
        llm,
        tool_impls={"research_cancellation_law": no_op_tool},
        tmp_path=tmp_path,
    )

    payload = {
        "event": "agent.message",
        "channel": "voice",
        "recentHistory": [],
        "data": {"transcript": "cancel my gym please"},
    }
    body = _signed_body(payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook", content=body, headers=_svix_headers(body))

    assert r.status_code == 200
    lines = _ndjson_lines(r.text)

    # Stream must terminate with a non-interim final chunk
    assert "interim" not in lines[-1], "last chunk must not have interim=True"
    assert "text" in lines[-1], "last chunk must carry a text field"

    # LLM must have been called exactly 6 times (cap enforced)
    assert len(llm.calls) == 6, (
        f"expected exactly 6 LLM calls (cap), got {len(llm.calls)}"
    )
