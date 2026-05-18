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
