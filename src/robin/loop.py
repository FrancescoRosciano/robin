"""Claude tool-call loop. interim ack -> (<=6 tool turns) -> final text.

If the injected ``llm`` exposes ``.stream`` (an async generator of
``(kind, payload)`` events: ``("text", chunk)`` deltas then a single
``("final", msg)``), the model's answer is spoken sentence-by-sentence
as it streams — TTS starts on sentence 1 instead of after the whole
completion. An ``llm`` with only ``.create`` keeps the exact legacy
behaviour, so every pre-existing fake/test is unaffected by construction.
"""
import re
import time
from typing import AsyncGenerator, Callable

from robin import obs, session
from robin.tools import TOOL_SCHEMAS

MAX_TOOL_TURNS = 6
# A complete sentence: up to a terminal . ! ? that sits on a whitespace
# or end-of-buffer boundary (so "415.776" / "U.S." mid-stream don't split).
_SENTENCE_RE = re.compile(r".*?[.!?](?=\s|$)", re.S)
# Keep the pre-stream ack tiny (~1s). With Haiku + sentence streaming the
# real first sentence lands in well under a second, so a long canned
# filler ADDS perceived latency instead of masking it (reference server
# uses an equally short ack). The streamed answer is the immediacy.
_INTERIM_ACK = "One moment."
_KEEPALIVE = "Still working on that — almost there."
_FORCED_FINAL = "Give me one moment — I'm still working on this."


def _content_text(content) -> str:
    parts = [b["text"] for b in content
             if isinstance(b, dict) and b.get("type") == "text"]
    return " ".join(p.strip() for p in parts if p).strip()


def _tool_uses(content) -> list:
    return [b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"]


def _drain_sentences(buf: str) -> tuple[list[str], str]:
    """Split completed sentences off the front of a streaming buffer.

    Returns ``(complete_sentences, remainder)``. The remainder is text
    after the last sentence terminator (an incomplete sentence still
    being streamed) and is carried forward to the next delta.
    """
    out: list[str] = []
    pos = 0
    for m in _SENTENCE_RE.finditer(buf):
        seg = m.group(0).strip()
        if seg:
            out.append(seg)
        pos = m.end()
    return out, buf[pos:]


def _history_text(content) -> str:
    """AgentPhone recentHistory `content` is not contractually a string —
    it can be a list/dict of blocks whose shape we do not control. Flatten
    to plain text: a string message content is always Anthropic-valid and
    cannot trigger a `messages.N.content.M.type` 400 from typeless blocks.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                parts.append(str(b.get("text") or b.get("content") or ""))
        return " ".join(p for p in (s.strip() for s in parts) if p)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return str(content or "")


def _history_role(h: dict) -> str:
    """Best-effort speaker mapping — AgentPhone may key it as `direction`
    or `role`/`speaker`. Unknown → 'user' (treat unattributed history as
    caller speech; never wrongly attribute it to Robin)."""
    d = str(h.get("direction") or "").lower()
    if d in ("inbound", "in", "incoming"):
        return "user"
    if d in ("outbound", "out", "outgoing"):
        return "assistant"
    r = str(h.get("role") or h.get("speaker") or h.get("from") or "").lower()
    if r in ("assistant", "agent", "robin", "bot"):
        return "assistant"
    return "user"


def _record_session(call_id: str | None, name: str, tool_input: dict,
                    out: object) -> None:
    """Persist tool outcomes into the per-call session so the NEXT webhook
    turn remembers them (AgentPhone's recentHistory carries no tool state).
    Deliberate, documented coupling to the three stable tool names — this
    is what stops Robin re-researching every turn and lets it progress to
    the dial. Best-effort: never raise into the call turn."""
    if not isinstance(out, dict):
        return
    try:
        if name == "research_cancellation_law" and out.get("status") == "OK":
            cites = out.get("citations") or []
            facts = "; ".join(
                f"{c.get('citation', '')}: {c.get('operative_quote', '')}"
                for c in cites if isinstance(c, dict))
            session.record_research(call_id, facts)
        elif name == "place_negotiation_call" and out.get("call_id"):
            session.mark_approved(call_id)
            session.mark_dial_placed(call_id, str(out.get("call_id")))
        elif name == "deliver_result" and out.get("delivered"):
            session.record_outcome(
                call_id, str(tool_input.get("summary", "delivered")))
    except Exception as exc:  # noqa: BLE001 - memory is best-effort, never fatal
        obs.log_event("session_record_error", call_id=call_id, name=name,
                       err=f"{type(exc).__name__}: {exc}")


async def run_turn(transcript: str, history: list, *, system: str, llm,
                   tool_impls: dict[str, Callable],
                   call_id: str | None = None
                   ) -> AsyncGenerator[dict, None]:
    """Yield NDJSON-ready dicts: one interim ack, then the final text."""
    yield {"text": _INTERIM_ACK, "interim": True}

    messages = []
    for h in history:
        if not isinstance(h, dict):
            continue
        text = _history_text(h.get("content", ""))
        if text:
            messages.append({"role": _history_role(h), "content": text})
    messages.append({"role": "user", "content": transcript})

    mem = session.summary_for_prompt(call_id)
    effective_system = f"{system}\n\n{mem}" if mem else system
    obs.log_event("turn_start", call_id=call_id,
                   history=len(messages) - 1, mem=bool(mem))

    stream_fn = getattr(llm, "stream", None)

    for _ in range(MAX_TOOL_TURNS):
        if stream_fn is None:
            msg = await llm.create(system=effective_system,
                                   messages=messages, tools=TOOL_SCHEMAS)
            tool_uses = _tool_uses(msg.content)
            if not tool_uses or getattr(msg, "stop_reason", "") != "tool_use":
                yield {"text": _content_text(msg.content) or _FORCED_FINAL}
                return
            messages.append({"role": "assistant", "content": msg.content})
            yield {"text": _KEEPALIVE, "interim": True}
        else:
            buf = ""
            pending: str | None = None
            spoke = False
            msg = None
            try:
                async for kind, payload in stream_fn(
                        system=effective_system, messages=messages,
                        tools=TOOL_SCHEMAS):
                    if kind == "text":
                        buf += str(payload)
                        sents, buf = _drain_sentences(buf)
                        for s in sents:
                            if pending is not None:
                                yield {"text": pending, "interim": True}
                                spoke = True
                            pending = s
                    elif kind == "final":
                        msg = payload
            except Exception as exc:  # noqa: BLE001 - a streaming hiccup must never 500 a live call; degrade to one completion
                obs.log_event("stream_error", call_id=call_id,
                               err=f"{type(exc).__name__}: {exc}")
                msg = None
            if msg is None:
                msg = await llm.create(system=effective_system,
                                       messages=messages, tools=TOOL_SCHEMAS)
                pending, buf = None, ""  # use the completion's own content
            tool_uses = _tool_uses(msg.content)
            if not tool_uses or getattr(msg, "stop_reason", "") != "tool_use":
                tail = " ".join(
                    x for x in (pending, buf.strip()) if x).strip()
                yield {"text": tail or _content_text(msg.content)
                       or _FORCED_FINAL}
                return
            if pending is not None:
                yield {"text": pending, "interim": True}
                spoke = True
            if buf.strip():
                yield {"text": buf.strip(), "interim": True}
                spoke = True
            if not spoke:
                yield {"text": _KEEPALIVE, "interim": True}
            messages.append({"role": "assistant", "content": msg.content})

        results = []
        for tu in tool_uses:
            name = tu.get("name", "")
            tool_input = tu.get("input", {}) or {}
            impl = tool_impls.get(name)
            if impl is None:
                obs.log_event("tool_unknown", call_id=call_id, name=name)
                out = {"error": f"unknown tool {name}"}
            else:
                obs.log_event("tool_start", call_id=call_id, name=name)
                t0 = time.monotonic()
                try:
                    out = await impl(**tool_input)
                    obs.log_event("tool_ok", call_id=call_id, name=name,
                                  ms=int((time.monotonic() - t0) * 1000),
                                  result=str(out))
                except Exception as exc:  # noqa: BLE001 - tools are an untrusted, fragile boundary; a tool failure must not kill the call turn, but it MUST be loud
                    obs.log_event("tool_error", call_id=call_id, name=name,
                                  ms=int((time.monotonic() - t0) * 1000),
                                  err=f"{type(exc).__name__}: {exc}")
                    out = {"error": f"tool {name} failed: {exc!s}"[:200]}
            _record_session(call_id, name, tool_input, out)
            results.append({"type": "tool_result", "tool_use_id": tu["id"],
                            "content": str(out)})
        messages.append({"role": "user", "content": results})

    yield {"text": _FORCED_FINAL}
