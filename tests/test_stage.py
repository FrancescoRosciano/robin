# tests/test_stage.py
"""Coverage for src/robin/stage.py (was 0%).

Strategy: the SSE route returns a StreamingResponse wrapping an internal
async generator closure.  We call the route handler directly and iterate
its body_iterator to cover lines 116-128 without needing a live HTTP server.
The HTML route is tested via TestClient (sync, no streaming issues).
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from robin.agentphone_client import TranscriptTurn
from robin.broadcast import TurnBroadcaster
from robin.stage import make_stage_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TURN_AGENT = TranscriptTurn(role="agent", content="Two options. Your decision.", created_at="t1")
TURN_USER = TranscriptTurn(role="user", content="Fine — cancel it.", created_at="t2")


def _make_app(broadcaster: TurnBroadcaster) -> FastAPI:
    app = FastAPI()
    app.include_router(make_stage_router(broadcaster))
    return app


def _get_stream_endpoint(broadcaster: TurnBroadcaster):
    """Return the stage_stream coroutine function from the router."""
    router = make_stage_router(broadcaster)
    for route in router.routes:
        if hasattr(route, "path") and route.path == "/stage/stream":
            return route.endpoint
    raise AssertionError("stage_stream route not found")


async def _collect_n_chunks(body_iterator, n: int, timeout: float = 5.0) -> list[str]:
    """Collect up to n chunks from the body iterator with a timeout guard."""
    chunks: list[str] = []

    async def _drain():
        async for chunk in body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
            if len(chunks) >= n:
                break

    await asyncio.wait_for(_drain(), timeout=timeout)
    return chunks


# ---------------------------------------------------------------------------
# GET /stage — HTML page
# ---------------------------------------------------------------------------

def test_stage_page_returns_200_html():
    b = TurnBroadcaster()
    r = TestClient(_make_app(b)).get("/stage")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_stage_page_contains_integrity_disclosure_verbatim():
    """INTEGRITY CHECK: the controlled-demo disclosure banner must be present word-for-word."""
    b = TurnBroadcaster()
    body = TestClient(_make_app(b)).get("/stage").text
    assert "CONTROLLED DEMO" in body, "CONTROLLED DEMO banner missing"
    assert "Robin's side is fully live." in body, "Live disclosure missing"
    assert "a briefed teammate" in body, "Teammate disclosure missing"
    assert "no real business is called." in body, "No-real-business disclosure missing"


def test_stage_page_labels_robin_and_receptionist():
    """The HTML must reference both participant labels for the projector UI."""
    body = TestClient(_make_app(TurnBroadcaster())).get("/stage").text
    assert "Robin" in body
    assert "Receptionist" in body


def test_stage_page_wires_event_source():
    """The page JS must open EventSource('/stage/stream') so the browser connects."""
    body = TestClient(_make_app(TurnBroadcaster())).get("/stage").text
    assert "EventSource('/stage/stream')" in body


# ---------------------------------------------------------------------------
# /stage/stream — StreamingResponse headers (lines 130-136)
# ---------------------------------------------------------------------------

async def test_stream_response_headers():
    """The StreamingResponse must carry the correct SSE headers."""
    b = TurnBroadcaster()
    fn = _get_stream_endpoint(b)
    resp: StreamingResponse = await fn()

    assert isinstance(resp, StreamingResponse)
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"

    # Clean up: drain the queue that subscribe() added
    b.unsubscribe(b._queues[0])


# ---------------------------------------------------------------------------
# /stage/stream — turn event framing (lines 116-122 of event_generator)
# ---------------------------------------------------------------------------

async def test_stream_yields_turn_event_for_published_turn():
    """A published turn must emerge as a correctly-framed SSE event chunk."""
    b = TurnBroadcaster()

    fn = _get_stream_endpoint(b)
    resp: StreamingResponse = await fn()

    # Publish AFTER subscribe (subscribe happens inside fn())
    await b.publish(TURN_AGENT)

    chunks = await _collect_n_chunks(resp.body_iterator, n=1)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.startswith("event: turn\n"), f"Bad event line: {chunk!r}"
    data_line = next(ln for ln in chunk.split("\n") if ln.startswith("data:"))
    payload = json.loads(data_line[len("data:"):].strip())
    assert payload == {"role": "agent", "content": "Two options. Your decision."}


# ---------------------------------------------------------------------------
# /stage/stream — heartbeat path (lines 123-124)
# ---------------------------------------------------------------------------

async def test_stream_yields_heartbeat_on_timeout(monkeypatch):
    """TimeoutError from wait_for must produce a ': heartbeat\\n\\n' chunk."""
    import robin.stage as stage_mod

    call_count = 0

    async def _patched(coro, timeout):
        nonlocal call_count
        call_count += 1
        coro.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(stage_mod.asyncio, "wait_for", _patched)

    b = TurnBroadcaster()
    fn = _get_stream_endpoint(b)
    resp: StreamingResponse = await fn()

    # Drive the generator directly — do NOT use _collect_n_chunks (which calls
    # asyncio.wait_for internally and would be intercepted by the same patch).
    chunks: list[str] = []
    async for raw in resp.body_iterator:
        chunk = raw.decode() if isinstance(raw, bytes) else raw
        chunks.append(chunk)
        break  # one chunk is enough

    assert chunks == [": heartbeat\n\n"]
    assert call_count >= 1


# ---------------------------------------------------------------------------
# /stage/stream — unsubscribe-on-disconnect (lines 125-128, finally branch)
# ---------------------------------------------------------------------------

async def test_stream_unsubscribes_queue_on_cancellation():
    """Closing the async generator after it has started must call unsubscribe."""
    b = TurnBroadcaster()
    fn = _get_stream_endpoint(b)
    resp: StreamingResponse = await fn()

    assert len(b._queues) == 1  # one queue added by subscribe() inside fn()

    # Publish a turn so the generator can yield once (enters the try block).
    await b.publish(TURN_AGENT)

    # Consume one chunk to ensure the generator body has actually run.
    async for raw in resp.body_iterator:
        _ = raw.decode() if isinstance(raw, bytes) else raw
        break

    # Now close — the finally block must call unsubscribe.
    await resp.body_iterator.aclose()
    await asyncio.sleep(0.02)
    assert b._queues == [], f"_queues not empty after aclose: {b._queues}"


async def test_stream_unsubscribes_after_aclose():
    """aclose() on an open generator must trigger the finally → unsubscribe."""
    b = TurnBroadcaster()

    fn = _get_stream_endpoint(b)
    resp: StreamingResponse = await fn()

    assert len(b._queues) == 1

    # Publish a turn so the generator yields one chunk (proves it ran past subscribe)
    await b.publish(TURN_AGENT)
    # Consume that chunk
    await _collect_n_chunks(resp.body_iterator, n=1)

    # Now explicitly close the generator
    await resp.body_iterator.aclose()
    await asyncio.sleep(0.02)
    assert b._queues == [], f"_queues not empty after aclose: {b._queues}"


# ---------------------------------------------------------------------------
# broadcast → stage integration: two subscribers both receive one published turn
# ---------------------------------------------------------------------------

async def test_two_subscribers_both_receive_published_turn():
    """Two queues subscribed to the same broadcaster each get the same turn."""
    b = TurnBroadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()

    await b.publish(TURN_AGENT)

    assert q1.get_nowait() == TURN_AGENT
    assert q2.get_nowait() == TURN_AGENT


async def test_two_stream_generators_both_receive_turn():
    """Two active generators (one per SSE connection) both get a published turn."""
    b = TurnBroadcaster()

    fn1 = _get_stream_endpoint(b)
    fn2 = _get_stream_endpoint(b)

    resp1: StreamingResponse = await fn1()
    resp2: StreamingResponse = await fn2()

    # Pre-publish after both subscribe
    await b.publish(TURN_USER)

    chunks1 = await _collect_n_chunks(resp1.body_iterator, n=1)
    chunks2 = await _collect_n_chunks(resp2.body_iterator, n=1)

    for chunks in (chunks1, chunks2):
        data_line = next(ln for ln in chunks[0].split("\n")
                          if ln.startswith("data:"))
        payload = json.loads(data_line[len("data:"):].strip())
        assert payload == {"role": "user", "content": "Fine — cancel it."}


# ---------------------------------------------------------------------------
# QueueFull slow consumer dropped; fast consumer still gets early turns
# ---------------------------------------------------------------------------

async def test_queuefull_slow_consumer_dropped_fast_consumer_unaffected():
    """publish() must not raise on a full queue; a draining subscriber gets first turns."""
    b = TurnBroadcaster(maxsize=2)

    fast_q = b.subscribe()
    _slow_q = b.subscribe()  # never drained → will fill up

    for i in range(5):
        turn = TranscriptTurn(role="agent", content=f"turn {i}", created_at=f"t{i}")
        await b.publish(turn)  # must not raise even when _slow_q is full

    # fast_q has capacity 2; got turns 0 and 1; turns 2–4 dropped
    assert fast_q.get_nowait().content == "turn 0"
    assert fast_q.get_nowait().content == "turn 1"
    with pytest.raises(asyncio.QueueEmpty):
        fast_q.get_nowait()
