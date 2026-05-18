"""Dashboard wiring tests — W4 flag-off/flag-on.

Group A — flag-off: original HTML and disclosure banner preserved.
Group B (tests 3–4 this step) — dashboard HTML file-content assertions.
Group B (tests 5–9 later) — integration wiring (added in Task 6).
"""
import pathlib

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
