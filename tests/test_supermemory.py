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
