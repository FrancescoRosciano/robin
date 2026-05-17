"""Outbound leg: dial the simulated receptionist, capture its SSE
transcript in one asyncio task, classify on call-end, deliver the result.

Implements the Coordination Model. Tool signatures are frozen in the 00
doc and replace the Plan 03 stub unchanged.
"""
import asyncio

from robin.classifier import classify_transcript
from robin.models import Outcome, OutcomeStatus


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
