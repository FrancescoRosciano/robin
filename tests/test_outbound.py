import asyncio

from robin.models import OutcomeStatus
from robin.outbound import CallRegistry, capture_and_classify, make_place_negotiation_call
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
