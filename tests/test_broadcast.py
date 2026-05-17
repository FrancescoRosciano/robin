import asyncio

import pytest

from robin.agentphone_client import TranscriptTurn
from robin.broadcast import TurnBroadcaster

TURN_A = TranscriptTurn(role="agent", content="Hello.", created_at="t1")
TURN_B = TranscriptTurn(role="user", content="Cancel please.", created_at="t2")


async def test_two_subscribers_both_receive_published_turn():
    b = TurnBroadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()
    await b.publish(TURN_A)
    assert q1.get_nowait() == TURN_A
    assert q2.get_nowait() == TURN_A


async def test_unsubscribed_queue_does_not_receive():
    b = TurnBroadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()
    b.unsubscribe(q2)
    await b.publish(TURN_B)
    assert q1.get_nowait() == TURN_B
    with pytest.raises(asyncio.QueueEmpty):
        q2.get_nowait()


async def test_full_queue_drops_turn_without_raising():
    b = TurnBroadcaster(maxsize=1)
    q = b.subscribe()
    await b.publish(TURN_A)   # fills the slot
    await b.publish(TURN_B)   # should drop silently, not raise
    assert q.get_nowait() == TURN_A  # first turn still there
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()           # second turn was dropped
