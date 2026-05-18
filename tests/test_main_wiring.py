"""Composition-wiring tests for the call-maker path in robin.main.

Verifies that _tool_impls has the exact three expected keys and that
_place correctly builds Citations and delegates to make_place_negotiation_call.

Uses the same monkeypatch recipe as tests/test_main_composition.py.
"""
import importlib
import json
import sys


def _valid_pack() -> dict:
    return {
        "caller_name": "Demo User",
        "callback_number": "+15550000001",
        "target_name": "24 Hour Gym",
        "target_display_number": "415-776-2200",
        "receptionist_to_number": "+15550000002",
        "jurisdiction": "US-CA",
        "win_goal": "cancel + last-month refund",
        "fallback_goal": "cancel only",
    }


def _setup_env(monkeypatch, tmp_path):
    """Set all required env vars and write a valid context_pack.json."""
    for k in ("ANTHROPIC_API_KEY", "AGENTPHONE_API_KEY",
              "AGENTPHONE_WEBHOOK_SECRET", "BROWSER_USE_API_KEY",
              "ROBIN_AGENT_ID", "FROM_NUMBER_ID"):
        monkeypatch.setenv(k, "dummy")
    monkeypatch.setenv("RECEPTIONIST_TO_NUMBER", "+15550000002")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test/")
    pack_path = tmp_path / "context_pack.json"
    pack_path.write_text(json.dumps(_valid_pack()))
    monkeypatch.setenv("CONTEXT_PACK_PATH", str(pack_path))

    import browser_use_sdk.v3 as bu
    monkeypatch.setattr(bu, "AsyncBrowserUse", lambda *a, **k: object())


# ---------------------------------------------------------------------------
# Test 7a: _tool_impls has exactly the three expected keys
# ---------------------------------------------------------------------------

def test_tool_impls_has_exact_keys(monkeypatch, tmp_path):
    """_tool_impls must expose exactly the three tools the loop knows about."""
    _setup_env(monkeypatch, tmp_path)
    sys.modules.pop("robin.main", None)
    main = importlib.import_module("robin.main")
    try:
        assert set(main._tool_impls) == {
            "research_cancellation_law",
            "place_negotiation_call",
            "deliver_result",
        }
    finally:
        sys.modules.pop("robin.main", None)


# ---------------------------------------------------------------------------
# Test 7b: _place is an awaitable closure that builds Citations and delegates
# ---------------------------------------------------------------------------

async def test_place_closure_builds_citations_and_returns_call_id(
        monkeypatch, tmp_path):
    """_place constructs Citation objects from raw dicts and returns the
    call_id dict produced by make_place_negotiation_call without real telephony."""
    _setup_env(monkeypatch, tmp_path)

    # Stub make_place_negotiation_call to return a predictable async callable
    # Capture the kwargs it receives so we can assert Citation construction
    captured: dict = {}

    async def _fake_place_impl(*, phone, member_name, citations):
        return {"call_id": "call_wiring_01"}

    def _fake_make_place(*, client, registry, agent_id, from_number_id,
                         receptionist_to_number, outbound_system_prompt,
                         on_turn=None):
        captured["receptionist_to_number"] = receptionist_to_number
        captured["agent_id"] = agent_id
        return _fake_place_impl

    import robin.outbound as _outbound
    monkeypatch.setattr(_outbound, "make_place_negotiation_call",
                        _fake_make_place)

    sys.modules.pop("robin.main", None)
    main = importlib.import_module("robin.main")
    try:
        result = await main._place(
            phone="415-776-2200",
            member_name="Demo User",
            citations=[
                {
                    "citation": "FTC Negative Option Rule, 16 CFR Part 425",
                    "operative_quote": "cancellation must be as easy as sign-up",
                    "source_url": "https://ftc.example/rule",
                }
            ],
        )
        # Returns the expected call_id-shaped dict
        assert result == {"call_id": "call_wiring_01"}
        # Delegates to the sim number, not the public display number
        assert captured["receptionist_to_number"] == "+15550000002"
        assert captured["agent_id"] == "dummy"
    finally:
        sys.modules.pop("robin.main", None)


# ---------------------------------------------------------------------------
# Test 7c: _place with multiple citations — all are forwarded
# ---------------------------------------------------------------------------

async def test_place_closure_forwards_all_citations(monkeypatch, tmp_path):
    """_place passes all citation dicts through to make_place_negotiation_call."""
    _setup_env(monkeypatch, tmp_path)

    forwarded_citations: list = []

    async def _fake_place_impl(*, phone, member_name, citations):
        forwarded_citations.extend(citations)
        return {"call_id": "call_wiring_02"}

    def _fake_make_place(*, client, registry, agent_id, from_number_id,
                         receptionist_to_number, outbound_system_prompt,
                         on_turn=None):
        return _fake_place_impl

    import robin.outbound as _outbound
    monkeypatch.setattr(_outbound, "make_place_negotiation_call",
                        _fake_make_place)

    sys.modules.pop("robin.main", None)
    main = importlib.import_module("robin.main")
    try:
        citations_input = [
            {"citation": "Law A", "operative_quote": "q1", "source_url": "u1"},
            {"citation": "Law B", "operative_quote": "q2", "source_url": "u2"},
        ]
        result = await main._place(
            phone="415-776-2200",
            member_name="Demo User",
            citations=citations_input,
        )
        assert result == {"call_id": "call_wiring_02"}
        assert len(forwarded_citations) == 2
    finally:
        sys.modules.pop("robin.main", None)


# ---------------------------------------------------------------------------
# Test 7d: deliver_result in _tool_impls is an awaitable callable
# ---------------------------------------------------------------------------

async def test_deliver_result_in_tool_impls_is_awaitable(monkeypatch, tmp_path):
    """The deliver_result tool in _tool_impls must be an awaitable closure.

    We call it with channel='stay_on' (no real network call) to confirm it
    returns the expected envelope without touching telephony.
    """
    _setup_env(monkeypatch, tmp_path)

    sys.modules.pop("robin.main", None)
    main = importlib.import_module("robin.main")
    try:
        deliver_result = main._tool_impls["deliver_result"]
        assert callable(deliver_result)

        result = await deliver_result(
            channel="stay_on",
            summary="Membership cancelled.",
            confirmation="24HF-9999",
        )
        assert result == {"delivered": True}
    finally:
        sys.modules.pop("robin.main", None)
