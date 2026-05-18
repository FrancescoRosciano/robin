"""W2 AgentMail close-loop tests (scaffold — RED until implemented)."""
import asyncio
import json

import pytest


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
    assert False, "not implemented"


async def test_hook_noop_when_flag_is_zero(monkeypatch):
    assert False, "not implemented"


async def test_done_outcome_sends_caller_email(monkeypatch):
    assert False, "not implemented"


async def test_fallback_confirmation_used_when_absent(monkeypatch):
    assert False, "not implemented"


async def test_missing_email_skips_caller_send(monkeypatch):
    assert False, "not implemented"


async def test_non_done_outcome_no_send(monkeypatch):
    assert False, "not implemented"


async def test_ambiguous_outcome_no_send(monkeypatch):
    assert False, "not implemented"


async def test_send_raises_swallowed_and_logged(monkeypatch):
    assert False, "not implemented"


async def test_hook_returns_before_send_completes(monkeypatch):
    assert False, "not implemented"


async def test_inbox_created_once_across_two_calls(monkeypatch):
    assert False, "not implemented"


def test_context_pack_accepts_email():
    assert False, "not implemented"


def test_context_pack_email_defaults_to_empty():
    assert False, "not implemented"


def test_load_context_pack_passes_email(tmp_path):
    assert False, "not implemented"


def test_load_context_pack_email_absent_defaults_empty(tmp_path):
    assert False, "not implemented"


async def test_flag_off_regression_no_side_effects(monkeypatch):
    assert False, "not implemented"
