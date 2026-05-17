"""In-process async pub/sub fan-out for transcript turns.

The Plan 04 SSE capture task is the ONLY AgentPhone SSE reader.
It calls broadcast.publish(turn) after each turn; every subscriber
(e.g. the projector SSE endpoint) gets its own bounded asyncio.Queue.
Turns are dropped (not raised) on a full queue so a slow projector
client never blocks the capture task.
"""
import asyncio

from robin.agentphone_client import TranscriptTurn


class TurnBroadcaster:
    def __init__(self, maxsize: int = 64) -> None:
        self._maxsize = maxsize
        self._queues: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """Return a new bounded queue that will receive future turns."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a queue; it will receive no further turns."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass  # already removed — idempotent

    async def publish(self, turn: TranscriptTurn) -> None:
        """Fan out turn to every subscriber queue. Non-blocking: drop on full."""
        for q in list(self._queues):
            try:
                q.put_nowait(turn)
            except asyncio.QueueFull:
                pass  # slow consumer — drop, do not block capture task
