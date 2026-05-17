from robin.models import OutcomeStatus
from robin.outbound import CallRegistry, capture_and_classify
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
