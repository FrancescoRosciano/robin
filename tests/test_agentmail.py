"""W2 AgentMail close-loop tests (scaffold — RED until implemented)."""
import asyncio
import json  # noqa: F401 — used in Task 8 context_pack tests

import pytest  # noqa: F401 — used implicitly by pytest fixtures


def _pack(email: str = "test@example.com"):
    """Build a ContextPack with synthetic data only."""
    from robin.models import ContextPack

    return ContextPack(
        caller_name="Test Caller",
        callback_number="+15550000001",
        target_name="24 Hour Gym",
        target_display_number="415-776-2200",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA",
        win_goal="cancel",
        fallback_goal="cancel",
        email=email,
    )


_DONE_PAYLOAD = {
    "summary": "Membership cancelled and last-month refund secured.",
    "confirmation": "24HF-4471",
    "channel": "stay_on",
    "out": {"delivered": True},
}


async def _drain():
    """Run every pending task to completion (best-effort)."""
    await asyncio.sleep(0)
    await asyncio.gather(
        *(asyncio.all_tasks() - {asyncio.current_task()}),
        return_exceptions=True,
    )


async def test_hook_noop_when_flag_absent(monkeypatch):
    """With ROBIN_AGENTMAIL_ENABLED unset, the hook returns without side-effects."""
    monkeypatch.delenv("ROBIN_AGENTMAIL_ENABLED", raising=False)
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    from robin.integrations.agentmail import make_email_outcome_hook

    hook = make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "Cancelled.",
        "confirmation": "24HF-4471",
        "channel": "stay_on",
        "out": {"delivered": True},
    }
    # Must return without error; no network calls
    await hook(call_id="call-001", payload=payload)
    # If we reach here without exception, test passes


async def test_hook_noop_when_flag_is_zero(monkeypatch):
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "0")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")
    from robin.integrations.agentmail import make_email_outcome_hook

    hook = make_email_outcome_hook(_pack("test@example.com"))
    await hook(call_id="call-002", payload={
        "summary": "done", "confirmation": "X",
        "channel": None, "out": {"delivered": True},
    })
    # No exception, no send


async def test_done_outcome_sends_caller_email(monkeypatch):
    """On DONE with pack.email set, send is called with correct to/subject/confirmation."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient(
        inbox_id="inbox-test-01",
        inbox_email="robin-confirms@agentmail.to",
    )
    # Pre-seed the inbox singleton so _ensure_inbox skips creation
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    pack = _pack("test@example.com")
    hook = am_mod.make_email_outcome_hook(pack)
    payload = {
        "summary": "Membership cancelled and last-month refund secured.",
        "confirmation": "24HF-4471",
        "channel": "stay_on",
        "out": {"delivered": True},
    }

    await hook(call_id="call-003", payload=payload)

    # Drain all pending tasks so the create_task coroutine runs
    await asyncio.sleep(0)       # one iteration of the event loop
    # Allow the send coroutines inside _send_emails to complete
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)

    # Two sends: caller confirmation + complaint draft
    assert len(fake.sent) == 2

    # Caller email
    caller_msg = next(m for m in fake.sent if m["to"] == "test@example.com")
    assert "24HF-4471" in caller_msg["text"]
    assert "cancel" in caller_msg["subject"].lower()

    # Complaint draft (synthetic gym address)
    complaint_msg = next(
        m for m in fake.sent
        if m["to"] == "cancellations@24hourfitness-demo.invalid"
    )
    assert "24HF-4471" in complaint_msg["text"]
    assert "DRAFTED BY ROBIN" in complaint_msg["text"]


async def test_fallback_confirmation_used_when_absent(monkeypatch):
    """When payload has no confirmation, uses _FALLBACK_CONFIRMATION."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "Cancelled.",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": True},
    }
    await hook(call_id="call-004", payload=payload)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    assert any("24HF-4471" in m["text"] for m in fake.sent)


async def test_missing_email_skips_caller_send(monkeypatch):
    """pack.email == "" → caller email is skipped; complaint draft still sent."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack(""))
    await hook(call_id="call-005", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    # Caller email NOT in sent (no empty-to send)
    assert not any(m["to"] == "" for m in fake.sent)
    # Complaint draft still attempted
    assert any("24hourfitness-demo.invalid" in m["to"] for m in fake.sent)


async def test_non_done_outcome_no_send(monkeypatch):
    """When out['delivered'] is False, no email is sent."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "Blocked.",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": False},
    }
    await hook(call_id="call-006", payload=payload)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    assert fake.sent == []


async def test_ambiguous_outcome_no_send(monkeypatch):
    """delivered=True but no confirmation and no success keywords → no send."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "something happened",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": True},
    }
    await hook(call_id="call-006b", payload=payload)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    assert fake.sent == []


async def test_send_raises_swallowed_and_logged(monkeypatch):
    """An exception inside _send_emails is swallowed; obs.log_event called."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    logged: list[str] = []
    import robin.obs as obs_mod
    original_log = obs_mod.log_event

    def _capture_log(event, **kw):
        logged.append(event)
        original_log(event, **kw)

    monkeypatch.setattr(obs_mod, "log_event", _capture_log)

    # Monkeypatch _send_emails to raise
    import robin.integrations.agentmail as am_mod

    async def _bad_send(**kw):
        raise RuntimeError("network gone")

    monkeypatch.setattr(am_mod, "_send_emails", _bad_send)

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    await hook(call_id="call-007", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)

    assert any("agentmail" in e for e in logged)
    # Hook itself did not raise — test reaching here proves it


async def test_hook_returns_before_send_completes(monkeypatch):
    """Hook must return without blocking on the send task."""
    import time

    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod

    send_started = asyncio.Event()
    send_done = asyncio.Event()

    async def _slow_send(**kw):
        send_started.set()
        await asyncio.sleep(0.1)   # simulate 100 ms network
        send_done.set()

    monkeypatch.setattr(am_mod, "_send_emails", _slow_send)

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    t0 = time.monotonic()
    await hook(call_id="call-008", payload=_DONE_PAYLOAD)
    elapsed = time.monotonic() - t0

    # Hook returned before the 100 ms sleep finished
    assert elapsed < 0.05, f"hook blocked for {elapsed:.3f}s"
    assert not send_done.is_set(), "send completed before hook returned"

    # Clean up the background task
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)


async def test_inbox_created_once_across_two_calls(monkeypatch):
    """_ensure_inbox must call inboxes.create exactly once even for two hook calls."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    # Reset singletons so _ensure_inbox actually creates
    monkeypatch.setattr(am_mod, "_client", None)
    monkeypatch.setattr(am_mod, "_inbox_id", None)
    monkeypatch.setattr(am_mod, "_inbox_email", None)
    monkeypatch.setattr(am_mod, "_inbox_lock", None)

    fake = FakeAgentMailClient()
    # Monkeypatch AsyncAgentMail constructor so _get_or_create_client returns the fake
    monkeypatch.setattr("agentmail.AsyncAgentMail", lambda **kw: fake)

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))

    # Two hook calls
    await hook(call_id="call-009", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    await hook(call_id="call-010", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)

    assert len(fake.created) == 1, (
        f"Expected inbox.create called once, got {len(fake.created)}"
    )


def test_context_pack_accepts_email():
    from robin.models import ContextPack
    pack = ContextPack(
        caller_name="A", callback_number="+15550000001",
        target_name="B", target_display_number="C",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA", win_goal="w", fallback_goal="f",
        email="test@example.com",
    )
    assert pack.email == "test@example.com"


def test_context_pack_email_defaults_to_empty():
    from robin.models import ContextPack
    pack = ContextPack(
        caller_name="A", callback_number="+15550000001",
        target_name="B", target_display_number="C",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA", win_goal="w", fallback_goal="f",
    )
    assert pack.email == ""


def test_load_context_pack_passes_email(tmp_path):
    from robin.context_pack import load_context_pack
    pack_data = {
        "caller_name": "Demo", "callback_number": "+15550000001",
        "target_name": "24 Hour Gym", "target_display_number": "415-776-2200",
        "receptionist_to_number": "+15550000002",
        "jurisdiction": "US-CA", "win_goal": "cancel", "fallback_goal": "cancel",
        "email": "test@example.com",
    }
    p = tmp_path / "cp.json"
    p.write_text(json.dumps(pack_data))
    pack = load_context_pack(str(p))
    assert pack.email == "test@example.com"


def test_load_context_pack_email_absent_defaults_empty(tmp_path):
    """context_pack.json without 'email' key → pack.email == ""."""
    from robin.context_pack import load_context_pack
    pack_data = {
        "caller_name": "Demo", "callback_number": "+15550000001",
        "target_name": "24 Hour Gym", "target_display_number": "415-776-2200",
        "receptionist_to_number": "+15550000002",
        "jurisdiction": "US-CA", "win_goal": "cancel", "fallback_goal": "cancel",
    }
    p = tmp_path / "cp.json"
    p.write_text(json.dumps(pack_data))
    pack = load_context_pack(str(p))
    assert pack.email == ""


async def test_flag_off_regression_no_side_effects(monkeypatch):
    assert False, "not implemented"
