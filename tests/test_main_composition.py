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


def test_main_composes_app_with_routes(monkeypatch, tmp_path):
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

    sys.modules.pop("robin.main", None)
    main = importlib.import_module("robin.main")
    try:
        paths = {r.path for r in main.app.routes}
        assert "/webhook" in paths
        assert "/fixture/law.html" in paths
        assert "/healthz" in paths
        assert set(main._tool_impls) == {
            "research_cancellation_law", "place_negotiation_call",
            "deliver_result"}
    finally:
        sys.modules.pop("robin.main", None)
