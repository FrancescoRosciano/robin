"""Adapt the Anthropic SDK to the loop's llm.create(system, messages,
tools) seam. Content blocks are normalized to plain dicts so loop.py
stays SDK-agnostic (and fakeable)."""
import anthropic

_MAX_TOKENS = 1024


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


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = [_normalize(b) for b in content]
        self.stop_reason = stop_reason


class AnthropicLLM:
    def __init__(self, *, client=None, api_key: str | None = None,
                 model: str = "claude-sonnet-4-6") -> None:
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._model = model

    async def create(self, *, system: str, messages: list, tools: list):
        resp = self._client.messages.create(
            model=self._model, max_tokens=_MAX_TOKENS, system=system,
            messages=messages, tools=tools)
        return _Msg(resp.content, getattr(resp, "stop_reason", "end_turn"))
