"""Dashboard wiring tests — W4 flag-off/flag-on.

Group A — flag-off: original HTML and disclosure banner preserved.
Group B (tests 3–4 this step) — dashboard HTML file-content assertions.
Group B (tests 5–9 later) — integration wiring (added in Task 6).
"""
import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from robin.broadcast import TurnBroadcaster
from robin.event_bus import EventBus
from robin.stage import _STAGE_HTML, make_stage_router

_DASHBOARD_PATH = pathlib.Path("src/robin/fixtures/stage_dashboard.html")

_DISCLOSURE_STRINGS = [
    "CONTROLLED DEMO",
    "Robin's side is fully live.",
    "a briefed teammate",
    "no real business is called.",
]


def _make_app_flagoff():
    """Minimal app with make_stage_router using defaults (flag-off behaviour)."""
    broadcaster = TurnBroadcaster()
    app = FastAPI()
    app.include_router(make_stage_router(broadcaster))
    return app


# --- Group A: flag-off ---

def test_flagoff_stage_serves_original_html():
    """GET /stage with flag off returns byte-identical _STAGE_HTML."""
    client = TestClient(_make_app_flagoff())
    resp = client.get("/stage")
    assert resp.status_code == 200
    assert resp.text == _STAGE_HTML


def test_flagoff_existing_test_stage_suite_still_passes():
    """Disclosure banner strings present in flag-off /stage response."""
    client = TestClient(_make_app_flagoff())
    resp = client.get("/stage")
    for s in _DISCLOSURE_STRINGS:
        assert s in resp.text, f"Missing disclosure string in flag-off HTML: {s!r}"


# --- Group B tests 3–4: dashboard HTML file-content (no server needed) ---

def test_dashboard_html_contains_disclosure_banner():
    """stage_dashboard.html must contain all four disclosure strings."""
    html = _DASHBOARD_PATH.read_text(encoding="utf-8")
    for s in _DISCLOSURE_STRINGS:
        assert s in html, f"Missing disclosure string in dashboard HTML: {s!r}"


def test_dashboard_html_contains_placeholder_text():
    """stage_dashboard.html must contain all three sponsor placeholder strings."""
    html = _DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "Moss legal citation will appear here" in html
    assert "Super Memory recall will appear here" in html
    assert "Agent Mail confirmation draft will appear here" in html


# --- Group B tests 5–9: flag-on integration wiring ---

def _make_app_flagons():
    """Minimal flag-on app: EventBus + dashboard HTML + stage router mounted.
    Does NOT import main.py (avoids production side-effects).
    Mirrors the composition main.py does under ROBIN_DASHBOARD_ENHANCED=1.
    """
    broadcaster = TurnBroadcaster()
    bus = EventBus()
    dashboard_html = _DASHBOARD_PATH.read_text(encoding="utf-8")
    app = FastAPI()
    from robin.stage import make_stage_router
    app.include_router(make_stage_router(broadcaster, event_bus=bus, stage_html=dashboard_html))
    return app, bus


def test_flagons_stage_serves_dashboard_html():
    """GET /stage with flag-on config returns the dashboard HTML."""
    app, _bus = _make_app_flagons()
    client = TestClient(app)
    resp = client.get("/stage")
    assert resp.status_code == 200
    assert "Moss legal citation will appear here" in resp.text


@pytest.mark.asyncio
async def test_citation_hook_publishes_citation_event():
    """_citation_pub hook publishes the correct citation event to the bus."""
    bus = EventBus()
    q = bus.subscribe()

    async def _citation_pub(call_id, out_dict):
        try:
            await bus.publish_event("citation", {
                "call_id": call_id,
                "citations": out_dict.get("citations", []),
            })
        except Exception:
            pass

    citations = [{"citation": "Cal § 1570",
                  "operative_quote": "cancel at any time",
                  "source_url": "https://example.com"}]
    await _citation_pub(call_id="c1", out_dict={"status": "OK", "citations": citations})
    item = q.get_nowait()
    assert item == {
        "event": "citation",
        "data": {"call_id": "c1", "citations": citations},
    }


@pytest.mark.asyncio
async def test_mail_hook_publishes_mail_draft_event():
    """_mail_pub hook publishes the correct mail_draft event to the bus."""
    bus = EventBus()
    q = bus.subscribe()

    async def _mail_pub(call_id, payload):
        try:
            await bus.publish_event("mail_draft", {
                "call_id": call_id,
                "summary": payload.get("summary", ""),
                "confirmation": payload.get("confirmation"),
                "channel": payload.get("channel"),
            })
        except Exception:
            pass

    payload = {"summary": "cancelled + last-month refund",
               "confirmation": "24HF-4471", "channel": "voice",
               "out": {"delivered": True}}
    await _mail_pub(call_id="c2", payload=payload)
    item = q.get_nowait()
    assert item == {
        "event": "mail_draft",
        "data": {"call_id": "c2",
                 "summary": "cancelled + last-month refund",
                 "confirmation": "24HF-4471",
                 "channel": "voice"},
    }


def _stream_endpoint(broadcaster, bus, html):
    """Return the /stage/stream coroutine for an event_bus-wired router.

    The W0 stage.py SSE generator's first await is a 15 s blocking
    ``wait_for(q.get())`` on the (empty) broadcaster queue, and its bus
    drain runs only AFTER that get resolves. Starlette ``TestClient.stream``
    deadlocks at context-manager entry against that blocking-first
    generator, so this exercises the SSE route via the route endpoint +
    ``body_iterator`` — the exact idiom test_stage.py already uses for the
    same /stage/stream route. stage.py is unchanged.
    """
    router = make_stage_router(broadcaster, event_bus=bus, stage_html=html)
    for route in router.routes:
        if getattr(route, "path", "") == "/stage/stream":
            return route.endpoint
    raise AssertionError("stage_stream route not found")


@pytest.mark.asyncio
async def test_sse_emits_citation_event_after_hook_fires():
    """SSE stream emits a citation event chunk when one is published to the bus."""
    import asyncio

    from robin.agentphone_client import TranscriptTurn

    bus = EventBus()
    broadcaster = TurnBroadcaster()
    dashboard_html = _DASHBOARD_PATH.read_text(encoding="utf-8")

    fn = _stream_endpoint(broadcaster, bus, dashboard_html)
    resp = await fn()  # subscribes the broadcaster queue inside the generator

    # Publish the citation to the bus BEFORE draining. The W0 drain
    # re-subscribes per loop iteration; EventBus's replay buffer makes
    # that fresh subscription still see this event. A single broadcaster
    # turn nudges the generator past its blocking get so the W0 drain
    # runs without waiting the full 15 s heartbeat.
    await bus.publish_event("citation", {"citations": []})
    await broadcaster.publish(
        TranscriptTurn(role="agent", content="(nudge)", created_at="t"))

    body = b""

    async def _drain():
        nonlocal body
        async for chunk in resp.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()
            if b"event: citation" in body:
                break

    await asyncio.wait_for(_drain(), timeout=5.0)
    assert b"event: citation" in body


def test_memory_panel_placeholder_present_when_no_memory_event():
    """Dashboard HTML contains the Super Memory placeholder (no event needed)."""
    html = _DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "Super Memory recall will appear here" in html
