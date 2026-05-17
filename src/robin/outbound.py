"""Outbound leg: dial the simulated receptionist, capture its SSE
transcript in one asyncio task, classify on call-end, deliver the result.

Implements the Coordination Model. Tool signatures are frozen in the 00
doc and replace the Plan 03 stub unchanged.
"""
import asyncio  # noqa: F401 — used by later tasks appended to this module

from robin.classifier import classify_transcript
from robin.models import Outcome


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
    async for turn in client.stream_transcript(call_id):
        lines.append(f"{turn.role}: {turn.content}")
    outcome = classify_transcript("\n".join(lines))
    registry.set(call_id, outcome)
    return outcome
