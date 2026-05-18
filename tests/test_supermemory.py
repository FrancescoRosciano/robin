# tests/test_supermemory.py
import os
import pytest

pytestmark = pytest.mark.asyncio


async def test_enricher_returns_empty_string_when_flag_off(monkeypatch):
    """Flag absent → enricher no-ops → empty string, no network call."""
    monkeypatch.delenv("ROBIN_MEMORY_ENABLED", raising=False)
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=["some history"])
    enricher = make_recall_enricher(client, "p15550001234")
    result = await enricher(call_id="call_test")
    assert result == ""
    assert client.search.calls == []  # no network call made


async def test_persist_hook_is_noop_when_flag_off(monkeypatch):
    """Flag absent → outcome hook no-ops → no add() call, no exception."""
    monkeypatch.delenv("ROBIN_MEMORY_ENABLED", raising=False)
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    from robin.integrations.supermemory import make_persist_outcome_hook
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient()
    hook = make_persist_outcome_hook(client, "p15550001234")
    await hook(call_id="call_test",
               payload={"summary": "cancelled", "confirmation": "24HF-4471",
                        "channel": None, "out": {"delivered": True}})
    assert client.added == []


async def test_enricher_returns_empty_string_when_key_absent(monkeypatch):
    """Flag set but no key → enricher no-ops."""
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    enricher = make_recall_enricher(FakeSupermemoryClient(), "p15550001234")
    assert await enricher(call_id=None) == ""


async def test_enricher_formats_history_block(monkeypatch):
    """Enricher with history items returns a [CALLER HISTORY] block."""
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=[
        "Cancelled 24 Hour Gym membership. Last-month refund. conf=24HF-4471",
        "Caller prefers no hold music",
    ])
    enricher = make_recall_enricher(client, "p14155551234")
    result = await enricher(call_id="call_abc")
    assert result.startswith("[CALLER HISTORY]")
    assert "24HF-4471" in result
    assert "hold music" in result
    # Search was called with the right tag
    assert client.search.calls[0]["container_tag"] == "p14155551234"


async def test_enricher_returns_empty_string_when_no_results(monkeypatch):
    """Zero results → empty string (no header block)."""
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=[])
    enricher = make_recall_enricher(client, "p14155550000")
    assert await enricher(call_id="call_xyz") == ""


async def test_enricher_returns_empty_string_on_timeout(monkeypatch):
    """asyncio.TimeoutError from fetch → return "" (never raise)."""
    import asyncio
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=[], raise_exc=asyncio.TimeoutError())
    enricher = make_recall_enricher(client, "p15550009999")
    result = await enricher(call_id="call_timeout")
    assert result == ""


async def test_enricher_returns_empty_string_on_api_error(monkeypatch):
    """Any exception from the SDK → return "" (never raise)."""
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(
        items=[], raise_exc=RuntimeError("SDK unavailable"))
    enricher = make_recall_enricher(client, "p15550008888")
    result = await enricher(call_id="call_error")
    assert result == ""


async def test_persist_hook_schedules_task_and_returns_immediately(monkeypatch):
    """Outcome hook must return without awaiting the persist network call."""
    import asyncio
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    from robin.integrations.supermemory import make_persist_outcome_hook
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient()
    hook = make_persist_outcome_hook(client, "p14155557777")
    payload = {"summary": "Cancelled gym. Got refund.", "confirmation": "24HF-4471",
               "channel": "voice", "out": {"delivered": True}}
    # The hook itself must return before client.add is awaited
    await hook(call_id="call_abc", payload=payload)
    # After draining the event loop, the task should have run
    await asyncio.sleep(0)  # let the scheduled task execute
    assert len(client.added) == 1
    assert "24HF-4471" in client.added[0]["content"]
    assert client.added[0]["container_tag"] == "p14155557777"


async def test_persist_hook_never_raises_on_add_failure(monkeypatch):
    """add() raising must be swallowed; hook must not propagate."""
    import asyncio
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    from robin.integrations.supermemory import make_persist_outcome_hook
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(add_raise=RuntimeError("storage down"))
    hook = make_persist_outcome_hook(client, "p15550006666")
    # Must not raise
    await hook(call_id="call_fail",
               payload={"summary": "test", "confirmation": None,
                        "channel": None, "out": {}})
    await asyncio.sleep(0)
    # No assert needed; the test passing means no exception was propagated
