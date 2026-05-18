"""De-risk the demo-critical OUTBOUND dial.

These tests exercise the full outbound path the way main.py wires it:

    Claude tool_use -> loop.run_turn -> _place (main.py) ->
    make_place_negotiation_call -> AgentPhoneClient.place_call ->
    HTTP POST https://api.agentphone.ai/v1/calls

They use a FAITHFUL in-test fake of the AgentPhone REST API
(`httpx.MockTransport`) so the EXACT wire request is asserted byte-for-
byte against `agentphone/agentphone-notes.md`:

    POST /v1/calls
    Authorization: Bearer <key>
    {"agentId","toNumber","initialGreeting","systemPrompt","fromNumberId"}

and against the Robin invariant: Robin SAYS target_display_number but
DIALS receptionist_to_number (never the real company).

They also pin the two failure modes that produce the reported
"it never actually dials" symptom:

  1. A real HTTP 4xx/5xx from /v1/calls must surface as a structured
     error, NOT a silently-swallowed success.
  2. The loop-level swallow: when `_place` raises (KeyError on a
     citation dict missing `operative_quote`), run_turn turns the
     failed dial into a bland tool_result string and the model just
     *talks* — no POST is ever sent. This is the concrete root cause
     of "never dials"; the test PROVES no HTTP call happened.

No real network. No secrets asserted (only header presence/shape).
"""
import json

import httpx
import pytest

from robin.agentphone_client import AgentPhoneClient
from robin.loop import run_turn
from robin.models import Citation
from robin.outbound import CallRegistry, make_place_negotiation_call
from tests.fakes import FakeLLM

# Synthetic only — never real PII (rules: tests use +1555… / fake ids).
AGENT_ID = "agt_robin_test"
FROM_NUMBER_ID = "num_robin_test"
RECEPTIONIST_TO = "+15550000002"        # the controlled simulation we DIAL
TARGET_DISPLAY = "415-776-2200"         # what Robin SAYS (never dialled)
MEMBER_NAME = "Demo User"
OUTBOUND_SYS = "OUTBOUND-PERSONA-AND-GOAL-TEXT"
GOOD_CITATIONS = [
    {"citation": "FTC Negative Option Rule, 16 CFR Part 425",
     "operative_quote": "Sellers must provide a simple cancellation "
                        "mechanism.",
     "source_url": "https://example.test/ftc"},
]


# --------------------------------------------------------------------------
# Faithful AgentPhone REST fake
# --------------------------------------------------------------------------
class _Recorder:
    """Captures every request the client makes for exact assertion."""

    def __init__(self, *, status: int = 200, body: dict | None = None,
                 raise_network: bool = False) -> None:
        self.status = status
        self.body = {"id": "call_OUT_1"} if body is None else body
        self.raise_network = raise_network
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_network:
            raise httpx.ConnectError("simulated network failure",
                                     request=request)
        if request.url.path == "/v1/calls" and request.method == "POST":
            return httpx.Response(self.status, json=self.body)
        # Faithful: a real transcript stream so the spawned capture task
        # does not explode the test with an unexpected 404.
        if request.url.path.endswith("/transcript/stream"):
            return httpx.Response(
                200,
                text=("event: ended\n"
                      'data: {"status":"completed"}\n\n'),
                headers={"content-type": "text/event-stream"})
        return httpx.Response(404)


def _client(rec: _Recorder) -> AgentPhoneClient:
    c = AgentPhoneClient(api_key="test-secret-key")
    # Preserve the real client's base_url + Authorization header; only swap
    # the transport so we never touch the network.
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(rec.handler),
        base_url="https://api.agentphone.ai/v1",
        headers={"Authorization": "Bearer test-secret-key"})
    return c


def _last_post(rec: _Recorder) -> httpx.Request:
    posts = [r for r in rec.requests
             if r.method == "POST" and r.url.path == "/v1/calls"]
    assert posts, "no POST /v1/calls was ever issued"
    return posts[-1]


# --------------------------------------------------------------------------
# 1. Exact request shape — matches agentphone-notes.md
# --------------------------------------------------------------------------
async def test_outbound_dial_sends_exact_agentphone_request():
    rec = _Recorder(body={"id": "call_OUT_1"})
    tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)

    res = await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                     citations=GOOD_CITATIONS)

    assert res == {"call_id": "call_OUT_1"}
    req = _last_post(rec)

    # Method + path (base_url already carries /v1).
    assert req.method == "POST"
    assert req.url.path == "/v1/calls"
    assert str(req.url) == "https://api.agentphone.ai/v1/calls"

    # Auth header present and Bearer-shaped — value NOT asserted.
    auth = req.headers.get("authorization", "")
    assert auth.startswith("Bearer ")
    assert len(auth) > len("Bearer ")

    body = json.loads(req.content)
    assert set(body) == {"agentId", "toNumber", "initialGreeting",
                          "systemPrompt", "fromNumberId"}
    assert body["agentId"] == AGENT_ID
    assert body["fromNumberId"] == FROM_NUMBER_ID
    assert body["systemPrompt"] == OUTBOUND_SYS
    assert MEMBER_NAME in body["initialGreeting"]

    # The Robin integrity invariant: DIAL the simulation, never the
    # public/real company number Robin merely SAYS.
    assert body["toNumber"] == RECEPTIONIST_TO
    assert TARGET_DISPLAY not in body["toNumber"]


async def test_outbound_dial_records_call_id_in_registry():
    rec = _Recorder(body={"id": "call_REG_9"})
    registry = CallRegistry()
    tool = make_place_negotiation_call(
        client=_client(rec), registry=registry, agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)

    res = await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                     citations=GOOD_CITATIONS)

    assert res["call_id"] == "call_REG_9"
    # The capture task is spawned against the same call id (registry is
    # populated once the faithful 'ended' stream is consumed).
    import asyncio
    await asyncio.sleep(0.05)
    assert registry.get("call_REG_9") is not None


async def test_outbound_dial_extracts_call_id_from_callId_field():
    """agentphone-notes.md: response may key the id as `callId`."""
    rec = _Recorder(body={"callId": "call_ALT"})
    tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)
    res = await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                     citations=GOOD_CITATIONS)
    assert res == {"call_id": "call_ALT"}


# --------------------------------------------------------------------------
# 2. Errors must SURFACE, not be silently swallowed
# --------------------------------------------------------------------------
async def test_http_500_is_surfaced_not_swallowed():
    rec = _Recorder(status=500, body={"detail": "boom"})
    tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)

    with pytest.raises(httpx.HTTPStatusError):
        await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                   citations=GOOD_CITATIONS)
    # It really tried (the dial was attempted, not skipped).
    assert _last_post(rec) is not None


async def test_http_4xx_is_surfaced_not_swallowed():
    rec = _Recorder(status=422, body={"detail": "bad number"})
    tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)
    with pytest.raises(httpx.HTTPStatusError):
        await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                   citations=GOOD_CITATIONS)


async def test_network_error_is_surfaced_not_swallowed():
    rec = _Recorder(raise_network=True)
    tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)
    with pytest.raises(httpx.ConnectError):
        await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                   citations=GOOD_CITATIONS)


async def test_missing_call_id_in_response_raises():
    rec = _Recorder(body={"status": "queued"})  # no id / callId
    tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)
    with pytest.raises(ValueError, match="missing call id"):
        await tool(phone=TARGET_DISPLAY, member_name=MEMBER_NAME,
                   citations=GOOD_CITATIONS)


# --------------------------------------------------------------------------
# 3. ROOT-CAUSE PIN: the loop swallows a failed dial -> Robin never dials
#
#    Reproduces main.py `_place` doing `c["operative_quote"]` (required
#    key) on a citation dict the model produced WITHOUT that key. _place
#    raises KeyError; loop.run_turn catches it (loop.py ~L90) and emits a
#    bland tool_result string. NO HTTP POST is ever sent. The model then
#    just talks. This is exactly "it never actually dials".
# --------------------------------------------------------------------------
def _tool_use_msg(tool_name: str, tool_input: dict):
    class _Msg:
        stop_reason = "tool_use"
        content = [{"type": "tool_use", "id": "tu_1",
                    "name": tool_name, "input": tool_input}]
    return _Msg()


def _final_msg(text: str):
    class _Msg:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": text}]
    return _Msg()


async def _drain(agen):
    return [c async for c in agen]


async def test_loop_swallows_failed_dial_when_citation_key_missing():
    """main.py._place reconstruction: Citation(c['citation'],
    c['operative_quote'], ...) — a model-produced citation missing
    'operative_quote' makes _place raise KeyError, which run_turn
    swallows. PROVE: no POST /v1/calls, and the caller hears a non-dial
    message instead. This is the demo-killer."""
    rec = _Recorder()
    real_tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)

    async def place_like_main(phone, member_name, citations):
        # Faithful copy of src/robin/main.py:_place lines 40-48.
        cites = [Citation(c["citation"], c["operative_quote"],
                          c.get("source_url", "")) for c in citations]
        assert cites is not None
        return await real_tool(phone=phone, member_name=member_name,
                               citations=citations)

    # Model calls the dial tool with a citation that has NO
    # operative_quote (realistic: research reformatted / amnesia).
    llm = FakeLLM([
        _tool_use_msg("place_negotiation_call",
                      {"phone": TARGET_DISPLAY,
                       "member_name": MEMBER_NAME,
                       "citations": [{"citation": "FTC Rule"}]}),
        _final_msg("Sorry, I hit a snag and could not place the call."),
    ])
    chunks = await _drain(run_turn(
        "cancel my gym membership", [], system="SYS", llm=llm,
        tool_impls={"place_negotiation_call": place_like_main}))

    # The bug's fingerprint: NOT ONE byte went to AgentPhone.
    assert [r for r in rec.requests
            if r.method == "POST"] == [], (
        "REGRESSION EXPECTATION: with the main.py bug, the dial is "
        "swallowed and no POST is sent. If this fails, the bug is fixed.")
    # The caller just gets a text turn; the failure was swallowed into a
    # tool_result the model saw, never surfaced as a real error.
    assert chunks[-1]["text"]
    assert "interim" not in chunks[-1]


async def test_loop_dials_when_citations_are_well_formed():
    """Control: with complete citations, the SAME wiring DOES POST.
    Proves the failure above is the missing-key path, not the harness."""
    rec = _Recorder(body={"id": "call_OK"})
    real_tool = make_place_negotiation_call(
        client=_client(rec), registry=CallRegistry(), agent_id=AGENT_ID,
        from_number_id=FROM_NUMBER_ID,
        receptionist_to_number=RECEPTIONIST_TO,
        outbound_system_prompt=OUTBOUND_SYS)

    async def place_like_main(phone, member_name, citations):
        cites = [Citation(c["citation"], c["operative_quote"],
                          c.get("source_url", "")) for c in citations]
        assert cites
        return await real_tool(phone=phone, member_name=member_name,
                               citations=citations)

    llm = FakeLLM([
        _tool_use_msg("place_negotiation_call",
                      {"phone": TARGET_DISPLAY,
                       "member_name": MEMBER_NAME,
                       "citations": GOOD_CITATIONS}),
        _final_msg("Done — I've placed the call."),
    ])
    await _drain(run_turn("cancel my gym membership", [], system="SYS",
                          llm=llm, tool_impls={
                              "place_negotiation_call": place_like_main}))

    req = _last_post(rec)
    body = json.loads(req.content)
    assert body["toNumber"] == RECEPTIONIST_TO
    assert body["agentId"] == AGENT_ID
