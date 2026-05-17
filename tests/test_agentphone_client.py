import httpx
import pytest
from robin.agentphone_client import AgentPhoneClient, TranscriptTurn


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/calls" and request.method == "POST":
        return httpx.Response(200, json={"id": "call_x"})
    if request.url.path == "/v1/calls/call_x/transcript/stream":
        return httpx.Response(
            200, text=open("tests/fixtures/transcript_done.sse").read(),
            headers={"content-type": "text/event-stream"})
    if request.url.path == "/v1/calls/call_x":
        return httpx.Response(200, json={"recordingUrl": "https://r/c.mp3",
                                         "recordingAvailable": True})
    return httpx.Response(404)


def _client() -> AgentPhoneClient:
    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="https://api.agentphone.ai/v1")
    return c


async def test_place_call_returns_call_id():
    cid = await _client().place_call(
        agent_id="agt", to_number="+15550000002",
        initial_greeting="Hi, this is Robin.", system_prompt="SYS",
        from_number_id="num")
    assert cid == "call_x"


async def test_stream_transcript_yields_turns_until_ended():
    turns = [t async for t in _client().stream_transcript("call_x")]
    assert all(isinstance(t, TranscriptTurn) for t in turns)
    assert turns[-1].content.endswith("24HF-4471.")
    assert turns[0].role in ("user", "agent")


async def test_get_recording_url():
    assert await _client().get_recording_url("call_x") == "https://r/c.mp3"


async def test_place_call_raises_when_response_lacks_call_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls" and request.method == "POST":
            return httpx.Response(200, json={})  # no id, no callId
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    with pytest.raises(ValueError, match="missing call id"):
        await c.place_call(agent_id="a", to_number="+15550000002",
                           initial_greeting="hi", system_prompt="s",
                           from_number_id="n")


async def test_stream_transcript_stops_on_ended_ignores_poison_after():
    sse = (
        "event: connected\n"
        'data: {"callId":"call_z","status":"in_progress"}\n\n'
        "event: turn\n"
        'data: {"role":"user","content":"first","createdAt":"t1"}\n\n'
        "event: ended\n"
        'data: {"callId":"call_z","status":"completed"}\n\n'
        "event: turn\n"
        'data: {"role":"agent","content":"POISON-AFTER-ENDED","createdAt":"t9"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls/call_z/transcript/stream":
            return httpx.Response(200, text=sse,
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    turns = [t async for t in c.stream_transcript("call_z")]
    assert [t.content for t in turns] == ["first"]
    assert all("POISON" not in t.content for t in turns)
