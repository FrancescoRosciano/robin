"""Event bus for typed sponsor events (citation, memory, mail_draft, ...).

Duck-typed to the W0 event_bus contract:
    subscribe() -> asyncio.Queue   (items: {"event": str, "data": dict})
    unsubscribe(q: asyncio.Queue) -> None
    async publish_event(event: str, data: dict) -> None

Mirrors TurnBroadcaster mechanics:
    - bounded per-subscriber queue (maxsize=64 default)
    - put_nowait; drop on full, never block, never raise
    - unsubscribe is idempotent

Replay buffer (deliberate W4 design, not in TurnBroadcaster)
-----------------------------------------------------------
W0's stage.py event_bus drain calls ``event_bus.subscribe()`` *inside*
the SSE generator loop — a fresh subscription is created on every
iteration (after a turn or the 15s heartbeat) and discarded again. A
pure post-subscribe fan-out (TurnBroadcaster semantics) would therefore
lose every event published *before* that per-iteration subscription
exists, so a citation/mail event emitted before the projector's first
heartbeat would never reach the page.

To make the W0 stub correct without editing stage.py, EventBus keeps a
small bounded ring of the most recent events and pre-loads each new
subscriber queue with that ring at ``subscribe()`` time. Events are
still fanned out live to existing subscribers on ``publish_event``. The
buffer only *adds* on subscribe (it never removes or reorders), so the
post-subscribe-publish behaviour the unit tests assert is unchanged.
"""
import asyncio
from collections import deque

# Keep the last N events for replay to a freshly-created subscription.
# Bounded so a long-running demo can never grow this without limit.
_REPLAY_MAXLEN = 64


class EventBus:
    def __init__(self, maxsize: int = 64) -> None:
        self._maxsize = maxsize
        self._queues: list[asyncio.Queue] = []
        self._replay: deque[dict] = deque(maxlen=_REPLAY_MAXLEN)

    def subscribe(self) -> asyncio.Queue:
        """Return a new bounded queue, pre-loaded with recent events.

        The pre-load makes W0's per-iteration re-subscribe in stage.py
        deliver events that were published before this subscription
        existed. Pre-load respects the queue bound (drop on full).
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        for item in self._replay:
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                break  # queue smaller than the replay ring — stop pre-loading
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a queue; idempotent."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass  # already removed — idempotent

    async def publish_event(self, event: str, data: dict) -> None:
        """Fan out {"event": event, "data": data} to every subscriber.

        Also records the event in the bounded replay ring so a
        subscription created later still sees it. Drop on a full
        subscriber queue — never block, never raise.
        """
        item = {"event": event, "data": data}
        self._replay.append(item)
        for q in list(self._queues):
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass  # slow consumer — drop, do not block the publisher
