"""Adapt the Anthropic SDK to the loop's llm.create(system, messages,
tools) seam. Content blocks are normalized to plain dicts so loop.py
stays SDK-agnostic (and fakeable)."""
import anthropic

# Voice-call latency: a hard token cap keeps spoken replies short (less
# generation time AND less TTS to wait through). The platform author's
# reference server uses 256 for a simpler assistant; 320 gives Robin's
# tool-driven discovery a little headroom without bloating replies.
_MAX_TOKENS = 320


def _normalize(block) -> dict:
    if isinstance(block, dict):
        return block
    t = getattr(block, "type", None)
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name,
                "input": block.input}
    return {"type": t or "unknown"}


def _safe_content(content):
    """Anthropic accepts a string or a list of typed blocks. AgentPhone's
    transcript/history shape is not contractual, so guarantee validity
    here — the single chokepoint before the API. Typed blocks
    (text/tool_use/tool_result) pass through untouched so the tool loop
    round-trips exactly; anything typeless is coerced to a text block."""
    if isinstance(content, str):
        return content if content else " "
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and isinstance(b.get("type"), str):
                out.append(b)
            elif isinstance(b, dict):
                txt = b.get("text")
                if txt is None:
                    txt = b.get("content")
                out.append({"type": "text",
                            "text": str(txt) if txt is not None else str(b)})
            elif isinstance(b, str):
                out.append({"type": "text", "text": b})
            else:
                out.append({"type": "text", "text": str(b)})
        return out or " "
    if content is None:
        return " "
    return str(content)


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = [_normalize(b) for b in content]
        self.stop_reason = stop_reason


class AnthropicLLM:
    def __init__(self, *, client=None, api_key: str | None = None,
                 model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._api_key = api_key
        self._model = model
        self._aclient = None  # lazy AsyncAnthropic, built on first stream()

    @staticmethod
    def _safe_messages(messages: list) -> list:
        return [{
            "role": (m.get("role", "user") if isinstance(m, dict)
                     else "user"),
            "content": _safe_content(
                m.get("content") if isinstance(m, dict) else m),
        } for m in messages]

    async def create(self, *, system: str, messages: list, tools: list):
        resp = self._client.messages.create(
            model=self._model, max_tokens=_MAX_TOKENS, system=system,
            messages=self._safe_messages(messages), tools=tools)
        return _Msg(resp.content, getattr(resp, "stop_reason", "end_turn"))

    async def stream(self, *, system: str, messages: list, tools: list):
        """Yield ``("text", delta)`` as the completion streams, then one
        ``("final", _Msg)``. Lets the loop speak sentences as they arrive
        (TTS starts on sentence 1) instead of waiting for the full
        completion. Uses an async client; ``create`` stays sync so the
        non-streaming fallback and its tests are unaffected."""
        if self._aclient is None:
            self._aclient = anthropic.AsyncAnthropic(api_key=self._api_key)
        async with self._aclient.messages.stream(
                model=self._model, max_tokens=_MAX_TOKENS, system=system,
                messages=self._safe_messages(messages),
                tools=tools) as stream:
            async for text in stream.text_stream:
                if text:
                    yield ("text", text)
            final = await stream.get_final_message()
        yield ("final", _Msg(final.content,
                             getattr(final, "stop_reason", "end_turn")))
