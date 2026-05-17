"""Claude tool-call loop. interim ack -> (<=6 tool turns) -> final text."""
from typing import AsyncGenerator, Callable

from robin.tools import TOOL_SCHEMAS

MAX_TOOL_TURNS = 6
_INTERIM_ACK = "Let me handle that for you."
_KEEPALIVE = "Still working on that — almost there."
_FORCED_FINAL = "Give me one moment — I'm still working on this."


def _content_text(content) -> str:
    parts = [b["text"] for b in content
             if isinstance(b, dict) and b.get("type") == "text"]
    return " ".join(p.strip() for p in parts if p).strip()


def _tool_uses(content) -> list:
    return [b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"]


async def run_turn(transcript: str, history: list, *, system: str, llm,
                   tool_impls: dict[str, Callable]) -> AsyncGenerator[dict, None]:
    """Yield NDJSON-ready dicts: one interim ack, then the final text."""
    yield {"text": _INTERIM_ACK, "interim": True}

    messages = []
    for h in history:
        role = "user" if h.get("direction") == "inbound" else "assistant"
        content = h.get("content", "")
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": transcript})

    for _ in range(MAX_TOOL_TURNS):
        msg = await llm.create(system=system, messages=messages,
                               tools=TOOL_SCHEMAS)
        tool_uses = _tool_uses(msg.content)
        if not tool_uses or getattr(msg, "stop_reason", "") != "tool_use":
            yield {"text": _content_text(msg.content) or _FORCED_FINAL}
            return
        messages.append({"role": "assistant", "content": msg.content})
        yield {"text": _KEEPALIVE, "interim": True}
        results = []
        for tu in tool_uses:
            impl = tool_impls.get(tu["name"])
            out = (await impl(**tu["input"])) if impl else {
                "error": f"unknown tool {tu['name']}"}
            results.append({"type": "tool_result", "tool_use_id": tu["id"],
                            "content": str(out)})
        messages.append({"role": "user", "content": results})

    yield {"text": _FORCED_FINAL}
