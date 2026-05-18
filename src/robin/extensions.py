"""Extension seam — inert injected hooks. Empty == today's behavior.

Hook-author contract
--------------------
A hook MUST return quickly (<~200 ms wall time) and MUST NOT raise. If a
hook needs to do long work (network I/O, email send, SDK persist) it MUST
schedule that work via ``asyncio.create_task(...)`` inside the hook body and
return immediately. Robin awaits the hook in the hot call-turn path; a slow
or crashing hook degrades every caller's experience.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

# Signature: (call_id: str | None) -> str
# Return "" to contribute nothing; non-empty text is appended to the system prompt.
PromptEnricher = Callable[[str | None], Awaitable[str]]

# Signature: (call_id: str | None, payload: dict) -> None
# Must not raise. Long work → asyncio.create_task inside the hook.
ResearchHook = Callable[[str | None, dict], Awaitable[None]]
OutcomeHook  = Callable[[str | None, dict], Awaitable[None]]


@dataclass(frozen=True)
class ExtensionHooks:
    """Injected callback bundles. All fields default to empty/None == no-op."""

    prompt_enrichers: tuple[PromptEnricher, ...] = ()
    """Awaited once per turn, before the first LLM call. Returns extra system
    prompt text appended after the session-memory block, in registration order."""

    on_research: tuple[ResearchHook, ...] = ()
    """Fired after research_cancellation_law returns status=="OK".
    Payload = the full ``out`` dict from the tool."""

    on_outcome: tuple[OutcomeHook, ...] = ()
    """Fired after deliver_result returns delivered==True.
    Payload = {"summary": str, "confirmation": str|None, "channel": str|None,
               "out": dict}."""

    event_bus: object | None = None
    """Opaque handle supplied by W4. None == inert. W0 passes it through
    make_stage_router; stage.py drains its subscribe()/unsubscribe(q) queue."""
