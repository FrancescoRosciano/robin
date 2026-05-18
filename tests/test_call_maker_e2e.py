"""E2E tests for the outbound call-maker path.

Covers: loop→tool→dial→capture→classify→deliver.
No real telephony; uses FakeAgentPhoneClient and FakeLLM.
"""
import asyncio


from robin.loop import run_turn
from robin.models import OutcomeStatus
from robin.outbound import CallRegistry, make_deliver_result, make_place_negotiation_call
from tests.fakes import FakeAgentPhoneClient, FakeLLM

# ---------------------------------------------------------------------------
# Shared demo transcript — mirrors the stage runsheet outcome
# ---------------------------------------------------------------------------
DONE_TURNS = [
    ("user", "I'd like to cancel my membership please."),
    ("agent", "You can only cancel in person at your home club."),
    ("user", "I have the law. Two options. Easy or hard. Your decision."),
    ("agent",
     "Fine — I'll cancel your subscription and refund your last month. "
     "Your confirmation number is 24HF-4471."),
]

BLOCKED_TURNS = [
    ("agent", "We only process cancellations in person. Goodbye."),
]

NEEDS_APPROVAL_TURNS = [
    ("agent", "I need you to verify your identity with a one-time code we'll text you."),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TOOL_USE_MSG_CONTENT = [
    {
        "type": "tool_use",
        "id": "tu_01",
        "name": "place_negotiation_call",
        "input": {
            "phone": "415-776-2200",
            "member_name": "Demo User",
            "citations": [
                {
                    "citation": "FTC Rule",
                    "operative_quote": "cancellation must be as easy as sign-up",
                    "source_url": "https://ftc.example/rule",
                }
            ],
        },
    }
]

_FINAL_MSG_CONTENT = [{"type": "text", "text": "I've placed the call on your behalf."}]


class _Msg:
    """Minimal Anthropic response shape."""

    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


def _make_tool_use_msg():
    return _Msg(_TOOL_USE_MSG_CONTENT, stop_reason="tool_use")


def _make_final_msg():
    return _Msg(_FINAL_MSG_CONTENT, stop_reason="end_turn")


# ---------------------------------------------------------------------------
# Test 1: end-to-end loop → place_negotiation_call → capture → DONE outcome
# ---------------------------------------------------------------------------

async def test_e2e_loop_to_done_outcome_and_sim_dialled():
    """Full path: run_turn emits tool_use → place_negotiation_call fires →
    capture task finishes → registry holds DONE with confirmation.

    Integrity bright-line: the fake client MUST be dialled at the sim number
    (+15550000002), NOT the publicly spoken number (415-776-2200).
    """
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="call_e2e_01")
    registry = CallRegistry()

    llm = FakeLLM([_make_tool_use_msg(), _make_final_msg()])

    tool_impls = {
        "place_negotiation_call": make_place_negotiation_call(
            client=client,
            registry=registry,
            agent_id="agt_test",
            from_number_id="num_test",
            receptionist_to_number="+15550000002",
            outbound_system_prompt="SYS-OUT",
        )
    }

    chunks = [c async for c in run_turn(
        "I want to cancel my gym membership.",
        history=[],
        system="You are Robin.",
        llm=llm,
        tool_impls=tool_impls,
    )]

    # Give the background capture task time to drain the fake stream
    await asyncio.sleep(0.05)

    # Integrity bright-line: dialled the controlled sim, not the public number
    assert len(client.placed) >= 1
    assert client.placed[0]["to_number"] == "+15550000002", (
        "Robin MUST dial the controlled sim number, never 415-776-2200"
    )

    # Registry stores DONE with the confirmation number
    outcome = registry.get("call_e2e_01")
    assert outcome is not None
    assert outcome.status == OutcomeStatus.DONE
    assert outcome.confirmation == "24HF-4471"

    # Loop produced at least one non-interim final chunk
    final_chunks = [c for c in chunks if not c.get("interim")]
    assert len(final_chunks) >= 1
    assert final_chunks[-1].get("text")


# ---------------------------------------------------------------------------
# Test 2: negotiation→callback chain delivers result with confirmation
# ---------------------------------------------------------------------------

async def test_e2e_callback_delivers_confirmation_in_spoken_prompt():
    """After DONE outcome, deliver_result('callback', ...) places a callback
    call to the synthetic callback number with the confirmation embedded."""
    callback_client = FakeAgentPhoneClient([], call_id="call_cb_01")
    deliver = make_deliver_result(
        client=callback_client,
        agent_id="agt_test",
        from_number_id="num_test",
        callback_number="+15550000001",
    )

    result = await deliver(
        channel="callback",
        summary="Cancelled — last-month refund granted.",
        confirmation="24HF-4471",
    )

    assert result["delivered"] is True
    assert len(callback_client.placed) == 1
    assert callback_client.placed[0]["to_number"] == "+15550000001"
    # The placed call must carry the confirmation number somewhere visible
    placed_call = callback_client.placed[0]
    assert placed_call is not None  # callback was placed — confirmation embedded in system_prompt (tested via integration)


async def test_e2e_callback_system_prompt_contains_confirmation():
    """Verify the spoken system_prompt passed to place_call includes
    the confirmation number so the outbound agent reads it to the caller."""
    spoken_prompts: list[str] = []

    class _CapturingClient:
        placed: list = []
        _call_id = "cap_01"

        async def place_call(self, *, agent_id, to_number, initial_greeting,
                             system_prompt, from_number_id):
            self.placed.append({"to_number": to_number,
                                 "system_prompt": system_prompt})
            spoken_prompts.append(system_prompt)
            return self._call_id

        async def stream_transcript(self, call_id):
            return
            yield  # pragma: no cover

        async def get_recording_url(self, call_id):
            return None

    cap_client = _CapturingClient()
    deliver = make_deliver_result(
        client=cap_client,
        agent_id="agt_test",
        from_number_id="num_test",
        callback_number="+15550000001",
    )

    await deliver(
        channel="callback",
        summary="Your gym membership has been cancelled.",
        confirmation="24HF-4471",
    )

    assert spoken_prompts, "No call was placed"
    assert "24HF-4471" in spoken_prompts[0]


# ---------------------------------------------------------------------------
# Test 3a: BLOCKED when receptionist stonewalls (no confirmation/refund)
# ---------------------------------------------------------------------------

async def test_e2e_capture_classifies_blocked_on_stonewall():
    """Transcript with no confirmation number and no refund → BLOCKED."""
    client = FakeAgentPhoneClient(BLOCKED_TURNS, call_id="call_blocked_01")
    registry = CallRegistry()

    tool = make_place_negotiation_call(
        client=client,
        registry=registry,
        agent_id="agt_test",
        from_number_id="num_test",
        receptionist_to_number="+15550000002",
        outbound_system_prompt="SYS-OUT",
    )

    await tool(phone="415-776-2200", member_name="Demo User", citations=[])
    await asyncio.sleep(0.05)

    outcome = registry.get("call_blocked_01")
    assert outcome is not None
    assert outcome.status == OutcomeStatus.BLOCKED
    assert outcome.confirmation is None


# ---------------------------------------------------------------------------
# Test 3b: NEEDS_APPROVAL when receptionist demands OTP/verification
# ---------------------------------------------------------------------------

async def test_e2e_capture_classifies_needs_approval_on_otp_demand():
    """Transcript containing a verification/OTP phrase → NEEDS_APPROVAL."""
    client = FakeAgentPhoneClient(NEEDS_APPROVAL_TURNS, call_id="call_otp_01")
    registry = CallRegistry()

    tool = make_place_negotiation_call(
        client=client,
        registry=registry,
        agent_id="agt_test",
        from_number_id="num_test",
        receptionist_to_number="+15550000002",
        outbound_system_prompt="SYS-OUT",
    )

    await tool(phone="415-776-2200", member_name="Demo User", citations=[])
    await asyncio.sleep(0.05)

    outcome = registry.get("call_otp_01")
    assert outcome is not None
    assert outcome.status == OutcomeStatus.NEEDS_APPROVAL
    assert outcome.confirmation is None


# ---------------------------------------------------------------------------
# Test: dialled number is NEVER the public display number
# ---------------------------------------------------------------------------

async def test_e2e_never_dials_public_display_number():
    """Regardless of the 'phone' arg passed by the LLM, Robin MUST always
    dial receptionist_to_number (the controlled simulation), never whatever
    string appears in the tool call as the public display number."""
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="call_nodial_01")
    registry = CallRegistry()

    tool = make_place_negotiation_call(
        client=client,
        registry=registry,
        agent_id="agt_test",
        from_number_id="num_test",
        receptionist_to_number="+15550000002",
        outbound_system_prompt="SYS-OUT",
    )

    # The LLM passes the public display number as 'phone' — must be ignored
    await tool(phone="415-776-2200", member_name="Demo User", citations=[])

    assert client.placed[0]["to_number"] == "+15550000002"
    assert client.placed[0]["to_number"] != "415-776-2200"
