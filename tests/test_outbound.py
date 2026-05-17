import asyncio

import pytest

from robin.models import OutcomeStatus
from robin.outbound import CallRegistry, capture_and_classify, make_deliver_result, make_place_negotiation_call
from tests.fakes import FakeAgentPhoneClient

DONE_TURNS = [
    ("user", "I need to cancel."),
    ("agent", "Cancel in person only."),
    ("user", "Two options: easy or hard. Your decision."),
    ("agent", "Fine — I'll cancel your subscription and refund your last "
              "month. Your confirmation number is 24HF-4471."),
]
BLOCKED_TURNS = [("agent", "Cancel in person only. I cannot help further.")]


async def test_capture_stores_done_outcome():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c1")
    await capture_and_classify("c1", client=client, registry=reg)
    o = reg.get("c1")
    assert o.status == OutcomeStatus.DONE
    assert o.confirmation == "24HF-4471"


async def test_capture_stores_blocked_outcome():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(BLOCKED_TURNS, call_id="c2")
    await capture_and_classify("c2", client=client, registry=reg)
    assert reg.get("c2").status == OutcomeStatus.BLOCKED


def test_registry_get_unknown_is_none():
    assert CallRegistry().get("nope") is None


class _BoomClient:
    placed: list = []

    async def stream_transcript(self, call_id):
        if False:
            yield  # make this an async generator
        raise RuntimeError("stream dropped")


async def test_capture_stores_blocked_on_stream_error():
    reg = CallRegistry()
    await capture_and_classify("cerr", client=_BoomClient(), registry=reg)
    o = reg.get("cerr")
    assert o.status == OutcomeStatus.BLOCKED
    assert "stream error" in o.detail


async def test_place_negotiation_call_dials_and_spawns_capture():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c9")
    tool = make_place_negotiation_call(
        client=client, registry=reg, agent_id="agt_robin",
        from_number_id="num_robin", receptionist_to_number="+15550000002",
        outbound_system_prompt="SYS-OUT")
    res = await tool(phone="415-776-2200", member_name="Demo User",
                     citations=[{"citation": "X", "operative_quote": "q",
                                 "source_url": "u"}])
    assert res["call_id"] == "c9"
    assert client.placed[0]["to_number"] == "+15550000002"  # dials the sim, not 415-...
    await asyncio.sleep(0.05)  # let the capture task finish the fake stream
    assert reg.get("c9").confirmation == "24HF-4471"


async def test_deliver_result_callback_places_call():
    client = FakeAgentPhoneClient([], call_id="cb1")
    tool = make_deliver_result(
        client=client, agent_id="agt_robin", from_number_id="num_robin",
        callback_number="+15550000001")
    res = await tool(channel="callback",
                     summary="Cancelled, last-month refund.",
                     confirmation="24HF-4471")
    assert res["delivered"] is True
    assert client.placed[0]["to_number"] == "+15550000001"


async def test_deliver_result_stay_on_does_not_place_call():
    client = FakeAgentPhoneClient([], call_id="x")
    tool = make_deliver_result(
        client=client, agent_id="a", from_number_id="n",
        callback_number="+15550000001")
    res = await tool(channel="stay_on", summary="Done.",
                     confirmation="24HF-4471")
    assert res["delivered"] is True
    assert client.placed == []


async def test_deliver_result_unknown_channel_raises():
    client = FakeAgentPhoneClient([], call_id="x")
    tool = make_deliver_result(
        client=client, agent_id="a", from_number_id="n",
        callback_number="+15550000001")
    with pytest.raises(ValueError):
        await tool(channel="bogus", summary="Done.", confirmation=None)
    assert client.placed == []


# ---------------------------------------------------------------------------
# Task 5: on_turn optional projector callback
# ---------------------------------------------------------------------------

async def test_on_turn_callback_receives_each_turn():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c_obs")
    collected: list = []

    async def collector(turn):
        collected.append(turn)

    await capture_and_classify("c_obs", client=client, registry=reg,
                               on_turn=collector)
    assert len(collected) == len(DONE_TURNS)
    assert collected[0].content == "I need to cancel."


async def test_on_turn_none_is_backward_compatible():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c_compat")
    await capture_and_classify("c_compat", client=client, registry=reg)
    assert reg.get("c_compat").status == OutcomeStatus.DONE


async def test_place_negotiation_call_forwards_on_turn():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c_fwd")
    collected: list = []

    async def collector(turn):
        collected.append(turn)

    tool = make_place_negotiation_call(
        client=client, registry=reg, agent_id="agt_robin",
        from_number_id="num_robin", receptionist_to_number="+15550000002",
        outbound_system_prompt="SYS-OUT", on_turn=collector)
    await tool(phone="415-776-2200", member_name="Demo User",
               citations=[{"citation": "X", "operative_quote": "q",
                           "source_url": "u"}])
    await asyncio.sleep(0.05)
    assert len(collected) == len(DONE_TURNS)


async def test_on_turn_error_stores_blocked_not_hang():
    """A raising on_turn must not leave the registry None — it degrades
    to a stored BLOCKED outcome (demo-safety invariant)."""
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c_obs_err")

    async def boom(turn):
        raise RuntimeError("projector exploded")

    await capture_and_classify("c_obs_err", client=client, registry=reg,
                               on_turn=boom)
    o = reg.get("c_obs_err")
    assert o is not None
    assert o.status == OutcomeStatus.BLOCKED
