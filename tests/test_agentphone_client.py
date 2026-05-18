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


# ---------------------------------------------------------------------------
# Tests 4–6 (call-maker path additions)
# ---------------------------------------------------------------------------

async def test_place_call_returns_id_from_id_field():
    """place_call extracts the call id from the 'id' field in the response."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls" and request.method == "POST":
            return httpx.Response(200, json={"id": "call_abc"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    cid = await c.place_call(agent_id="a", to_number="+15550000002",
                             initial_greeting="hi", system_prompt="s",
                             from_number_id="n")
    assert cid == "call_abc"


async def test_place_call_returns_id_from_callId_field():
    """place_call falls back to 'callId' when 'id' is absent."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls" and request.method == "POST":
            return httpx.Response(200, json={"callId": "call_xyz"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    cid = await c.place_call(agent_id="a", to_number="+15550000002",
                             initial_greeting="hi", system_prompt="s",
                             from_number_id="n")
    assert cid == "call_xyz"


async def test_place_call_raises_when_both_id_fields_missing():
    """place_call raises ValueError when neither 'id' nor 'callId' is present."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls" and request.method == "POST":
            return httpx.Response(200, json={"status": "queued"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    with pytest.raises(ValueError, match="missing call id"):
        await c.place_call(agent_id="a", to_number="+15550000002",
                           initial_greeting="hi", system_prompt="s",
                           from_number_id="n")


async def test_stream_transcript_yields_multiple_turns_and_maps_created_at():
    """Multiple 'turn' events are all yielded, and createdAt maps to created_at."""
    sse = (
        "event: connected\n"
        'data: {"callId":"call_m","status":"in_progress"}\n\n'
        "event: turn\n"
        'data: {"role":"user","content":"turn-one","createdAt":"ts1"}\n\n'
        "event: turn\n"
        'data: {"role":"agent","content":"turn-two","createdAt":"ts2"}\n\n'
        "event: turn\n"
        'data: {"role":"user","content":"turn-three","createdAt":"ts3"}\n\n'
        "event: ended\n"
        'data: {"callId":"call_m","status":"completed"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls/call_m/transcript/stream":
            return httpx.Response(200, text=sse,
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    turns = [t async for t in c.stream_transcript("call_m")]

    assert len(turns) == 3
    assert turns[0].content == "turn-one"
    assert turns[1].content == "turn-two"
    assert turns[2].content == "turn-three"
    # createdAt key mapped to created_at attribute
    assert turns[0].created_at == "ts1"
    assert turns[2].created_at == "ts3"


async def test_stream_transcript_stops_at_ended_no_extra_turns():
    """Turns emitted AFTER 'ended' are not yielded (duplicate of stop-on-ended
    but isolated to prove the count boundary is exact)."""
    sse = (
        "event: turn\n"
        'data: {"role":"agent","content":"before-end","createdAt":"t1"}\n\n'
        "event: ended\n"
        'data: {"status":"completed"}\n\n'
        "event: turn\n"
        'data: {"role":"agent","content":"after-end","createdAt":"t2"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls/call_stop/transcript/stream":
            return httpx.Response(200, text=sse,
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    turns = [t async for t in c.stream_transcript("call_stop")]
    assert len(turns) == 1
    assert turns[0].content == "before-end"


async def test_get_recording_url_returns_url_when_present():
    """get_recording_url returns the recordingUrl string when it exists."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls/call_rec":
            return httpx.Response(200, json={"recordingUrl": "https://r/rec.mp3"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    url = await c.get_recording_url("call_rec")
    assert url == "https://r/rec.mp3"


async def test_get_recording_url_returns_none_when_absent():
    """get_recording_url returns None when recordingUrl is not in the response."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls/call_norec":
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(404)

    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.agentphone.ai/v1")
    url = await c.get_recording_url("call_norec")
    assert url is None
