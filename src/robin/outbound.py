"""Outbound leg: dial the simulated receptionist, capture its SSE
transcript in one asyncio task, classify on call-end, deliver the result.

Implements the Coordination Model. Tool signatures are frozen in the 00
doc and replace the Plan 03 stub unchanged.
"""
import asyncio
import logging

from robin.classifier import classify_transcript
from robin.models import Outcome, OutcomeStatus

_log = logging.getLogger(__name__)


class CallRegistry:
    """In-process map call_id -> Outcome (None until the call ends)."""

    def __init__(self) -> None:
        self._outcomes: dict[str, Outcome] = {}

    def set(self, call_id: str, outcome: Outcome) -> None:
        self._outcomes[call_id] = outcome

    def get(self, call_id: str) -> Outcome | None:
        return self._outcomes.get(call_id)


async def capture_and_classify(call_id: str, *, client,
                               registry: CallRegistry) -> Outcome:
    """Consume one SSE transcript until it ends, classify, store."""
    lines: list[str] = []
    try:
        async for turn in client.stream_transcript(call_id):
            lines.append(f"{turn.role}: {turn.content}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - stream is an untrusted boundary
        outcome = Outcome(status=OutcomeStatus.BLOCKED, confirmation=None,
                           detail=f"transcript stream error: {exc!s}"[:200])
        registry.set(call_id, outcome)
        return outcome
    outcome = classify_transcript("\n".join(lines))
    registry.set(call_id, outcome)
    return outcome


def make_place_negotiation_call(*, client, registry: CallRegistry,
                                agent_id: str, from_number_id: str,
                                receptionist_to_number: str,
                                outbound_system_prompt: str):
    """Build the frozen-signature place_negotiation_call tool callable.

    Robin SAYS the public number but DIALS the controlled simulation
    (receptionist_to_number) — never the real company.
    """

    _tasks: set[asyncio.Task] = set()

    def _on_done(task: asyncio.Task) -> None:
        _tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _log.error("capture task failed: %r", task.exception())

    async def place_negotiation_call(phone: str, member_name: str,
                                     citations: list[dict]) -> dict:
        call_id = await client.place_call(
            agent_id=agent_id, to_number=receptionist_to_number,
            initial_greeting=f"Hi, I'm calling on behalf of {member_name}.",
            system_prompt=outbound_system_prompt,
            from_number_id=from_number_id)
        task = asyncio.create_task(
            capture_and_classify(call_id, client=client, registry=registry))
        _tasks.add(task)
        task.add_done_callback(_on_done)
        return {"call_id": call_id}

    return place_negotiation_call


def make_deliver_result(*, client, agent_id: str, from_number_id: str,
                         callback_number: str):
    """Build the frozen-signature deliver_result tool callable.

    channel "callback": place a fresh outbound call to the caller with
    the result. channel "stay_on": no call — the text is spoken on the
    held inbound turn by the loop (stretch path).
    """

    async def deliver_result(channel: str, summary: str,
                             confirmation: str | None) -> dict:
        spoken = summary if not confirmation else (
            f"{summary} Confirmation number {confirmation}.")
        if channel == "callback":
            await client.place_call(
                agent_id=agent_id, to_number=callback_number,
                initial_greeting="Hi, it's Robin with an update.",
                system_prompt=f"Tell the caller, then stop: {spoken}",
                from_number_id=from_number_id)
        elif channel != "stay_on":
            raise ValueError(f"deliver_result: unrecognised channel {channel!r}")
        return {"delivered": True}

    return deliver_result
