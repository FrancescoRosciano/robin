"""Tests for EventBus — mirrors test_broadcast.py exactly,
replacing TurnBroadcaster/TranscriptTurn with EventBus/dict."""
import asyncio

import pytest

from robin.event_bus import EventBus


@pytest.mark.asyncio
async def test_subscribe_returns_queue():
    bus = EventBus(maxsize=8)
    q = bus.subscribe()
    assert isinstance(q, asyncio.Queue)
    assert q.maxsize == 8


@pytest.mark.asyncio
async def test_two_subscribers_both_receive_event():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    await bus.publish_event("citation", {"citations": [{"citation": "Cal § 1570"}]})
    item1 = q1.get_nowait()
    item2 = q2.get_nowait()
    assert item1 == {"event": "citation", "data": {"citations": [{"citation": "Cal § 1570"}]}}
    assert item2 == item1


@pytest.mark.asyncio
async def test_unsubscribed_queue_does_not_receive():
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)
    await bus.publish_event("citation", {"citations": []})
    assert q.empty()


@pytest.mark.asyncio
async def test_full_queue_drops_event_without_raising():
    bus = EventBus(maxsize=1)
    q = bus.subscribe()
    await bus.publish_event("citation", {"citations": []})  # fills the queue
    # second publish must not raise even though the queue is full
    await bus.publish_event("citation", {"citations": []})
    assert q.qsize() == 1  # only the first item; second was dropped


@pytest.mark.asyncio
async def test_publish_event_typed_payload_round_trip():
    bus = EventBus()
    q = bus.subscribe()
    citations = [{"citation": "Cal. Health & Safety Code § 1570",
                  "operative_quote": "cancel at any time",
                  "source_url": "https://example.com"}]
    await bus.publish_event("citation", {"citations": citations})
    item = q.get_nowait()
    assert item == {"event": "citation", "data": {"citations": citations}}


@pytest.mark.asyncio
async def test_unsubscribe_is_idempotent():
    """Unsubscribing the same queue twice must not raise."""
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)
    bus.unsubscribe(q)  # second call hits the ValueError guard — must be a no-op
    await bus.publish_event("citation", {"citations": []})
    assert q.empty()


@pytest.mark.asyncio
async def test_subscribe_preloads_replay_buffer_and_respects_queue_bound():
    """A late subscriber receives buffered events; pre-load stops at the bound.

    Publish 3 events, then subscribe with maxsize=2. The replay pre-load
    must fill exactly 2 (oldest-first) and stop on QueueFull — the third
    buffered event is dropped, never raised.
    """
    bus = EventBus(maxsize=2)
    await bus.publish_event("citation", {"n": 1})
    await bus.publish_event("citation", {"n": 2})
    await bus.publish_event("citation", {"n": 3})

    q = bus.subscribe()  # created AFTER all three publishes
    assert q.qsize() == 2  # bound respected; pre-load broke on full
    first = q.get_nowait()
    second = q.get_nowait()
    assert first == {"event": "citation", "data": {"n": 1}}
    assert second == {"event": "citation", "data": {"n": 2}}
    assert q.empty()
