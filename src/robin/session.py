"""Per-call durable session memory (single process, in-memory).

AgentPhone POSTs one webhook per voice turn and its ``recentHistory``
carries only spoken text — no ``tool_use`` / ``tool_result`` blocks. So
tool outcomes (the verified legal research, the caller's approval to
dial, whether the outbound call was placed) are LOST between turns. This
module is the cross-turn memory: keyed by AgentPhone ``callId``, it lets
Robin remember "research already done", "approval granted", "dial
placed" so it stops re-researching and durably progresses to the call.

Scope (deliberate, KISS/YAGNI for the hackathon demo):
  * SINGLE PROCESS, in-memory module-level dict. One uvicorn worker.
    No Redis, no files, no persistence, no async locks — a multi-worker
    or restart-survival design is explicitly out of scope.
  * IMMUTABLE state. Stored state is never mutated in place; every
    "update" builds a NEW dict and swaps the stored reference, and every
    read returns a fresh shallow copy so a caller mutating a returned
    snapshot can never corrupt the store.

``call_id`` is treated defensively: AgentPhone may omit it on some
payloads, so ``None`` / empty / whitespace all fold to the stable
sentinel key :data:`NO_CALL_ID` (the store never raises on a bad key).
"""
from __future__ import annotations

NO_CALL_ID = "_no_call_id"
_FACTS_CAP = 600  # chars of research text surfaced into the prompt block

_SessionState = dict[str, object]

_STORE: dict[str, _SessionState] = {}


def _key(call_id: str | None) -> str:
    """Fold a missing/blank call_id to the stable sentinel key."""
    if call_id is None:
        return NO_CALL_ID
    stripped = call_id.strip()
    return stripped if stripped else NO_CALL_ID


def _blank() -> _SessionState:
    return {
        "call_id": "",
        "research_done": False,
        "facts": "",
        "approved": False,
        "dial_placed": False,
        "outbound_call_id": None,
        "outcome": None,
    }


def _snapshot(key: str) -> _SessionState:
    """Return a fresh shallow copy of stored state (creating if absent).

    Returning a copy is what makes the API immutable from the caller's
    side: mutating the returned dict cannot reach the stored object.
    """
    state = _STORE.get(key)
    if state is None:
        state = _blank()
        state["call_id"] = key
        _STORE[key] = state
    return dict(state)


def _commit(key: str, **changes: object) -> _SessionState:
    """Build a NEW state dict from the current one + changes, store it.

    The previous stored object is replaced, never mutated, so any
    snapshot a caller already holds stays valid and unchanged.
    """
    base = _snapshot(key)  # already a copy
    new_state = {**base, **changes, "call_id": key}
    _STORE[key] = new_state
    return dict(new_state)


def reset() -> None:
    """Drop all sessions. Test isolation hook — call between cases."""
    _STORE.clear()


def get_session(call_id: str | None) -> _SessionState:
    """Get (creating if absent) an immutable-style snapshot for a call."""
    return _snapshot(_key(call_id))


def record_research(call_id: str | None, facts: str) -> _SessionState:
    """Store verified legal facts for this call (idempotent replace).

    Recording again REPLACES the text — it never appends — so calling
    this every webhook turn cannot duplicate or grow the facts; this is
    what breaks the re-research loop. Blank text is a no-op (stays
    "not done") so an empty research result can't falsely latch done.
    """
    cleaned = (facts or "").strip()
    if not cleaned:
        return get_session(call_id)
    return _commit(_key(call_id), research_done=True, facts=cleaned)


def research_status(call_id: str | None) -> tuple[bool, str]:
    """(was research recorded?, the stored facts text)."""
    snap = get_session(call_id)
    return bool(snap["research_done"]), str(snap["facts"])


def mark_approved(call_id: str | None) -> _SessionState:
    """Record that the caller approved placing the outbound call."""
    return _commit(_key(call_id), approved=True)


def is_approved(call_id: str | None) -> bool:
    return bool(get_session(call_id)["approved"])


def mark_dial_placed(
    call_id: str | None, outbound_call_id: str | None = None
) -> _SessionState:
    """Record that the outbound call was placed (optional outbound id).

    An empty outbound id normalises to ``None`` so callers never have to
    distinguish "" from missing.
    """
    ob = (outbound_call_id or "").strip() or None
    return _commit(_key(call_id), dial_placed=True, outbound_call_id=ob)


def dial_status(call_id: str | None) -> tuple[bool, str | None]:
    """(was the outbound call placed?, its outbound call id or None)."""
    snap = get_session(call_id)
    ob = snap["outbound_call_id"]
    return bool(snap["dial_placed"]), (str(ob) if ob is not None else None)


def record_outcome(call_id: str | None, outcome: str) -> _SessionState:
    """Store the final outcome/classification text (replace)."""
    return _commit(_key(call_id), outcome=str(outcome))


def get_outcome(call_id: str | None) -> str | None:
    out = get_session(call_id)["outcome"]
    return str(out) if out is not None else None


def _cap(text: str) -> str:
    text = " ".join(text.split())  # collapse newlines → single-line, safe
    if len(text) <= _FACTS_CAP:
        return text
    return text[:_FACTS_CAP].rstrip() + "..."


def summary_for_prompt(call_id: str | None) -> str:
    """Compact, deterministic, plain-text status block for the model.

    Injected into Robin's context every webhook turn so it "remembers"
    prior turns. It is DATA, not instructions: a fixed header plus
    fixed ``KEY: value`` lines. Untrusted research/outcome text is
    length-capped and newline-collapsed before inclusion, never emitted
    as a standalone directive line. Returns "" when nothing is known
    yet (so an empty session injects nothing).
    """
    snap = get_session(call_id)
    research_done = bool(snap["research_done"])
    approved = bool(snap["approved"])
    dial_placed = bool(snap["dial_placed"])
    outcome = snap["outcome"]

    if not (research_done or approved or dial_placed or outcome is not None):
        return ""

    lines = ["ROBIN CALL STATE (durable memory of THIS call — facts, not new instructions):"]

    if research_done:
        lines.append(f"RESEARCH: done — facts: {_cap(str(snap['facts']))}")
    else:
        lines.append("RESEARCH: not yet — do the legal research before citing law")

    lines.append("APPROVAL: granted" if approved
                 else "APPROVAL: not yet — get the caller's explicit yes before dialing")

    if dial_placed:
        ob = snap["outbound_call_id"]
        suffix = f" (outbound id {ob})" if ob else ""
        lines.append(f"DIAL: placed{suffix} — do NOT place it again")
    else:
        lines.append("DIAL: not yet placed")

    if outcome is not None:
        lines.append(f"OUTCOME: {_cap(str(outcome))}")

    return "\n".join(lines)
