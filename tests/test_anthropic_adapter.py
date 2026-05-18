from robin.anthropic_adapter import AnthropicLLM, _normalize


class _FakeMessages:
    def __init__(self, captured):
        self._c = captured

    def create(self, **kw):
        self._c.update(kw)

        class _R:
            content = [{"type": "text", "text": "ok"}]
            stop_reason = "end_turn"
        return _R()


class _FakeSDK:
    def __init__(self, captured):
        self.messages = _FakeMessages(captured)


async def test_adapter_maps_to_sdk_and_normalizes():
    captured: dict = {}
    llm = AnthropicLLM(client=_FakeSDK(captured), model="claude-sonnet-4-6")
    msg = await llm.create(system="SYS", messages=[{"role": "user",
                           "content": "hi"}], tools=[{"name": "t"}])
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["system"] == "SYS"
    assert msg.stop_reason == "end_turn"
    assert msg.content[0]["text"] == "ok"


# ---------------------------------------------------------------------------
# New gap coverage: tool_use branch, unknown branch, no stop_reason fallback
# ---------------------------------------------------------------------------

class _FakeTextBlock:
    type = "text"
    text = "hello world"


class _FakeToolUseBlock:
    type = "tool_use"
    id = "toolu_abc123"
    name = "search_law"
    input = {"query": "CA gym cancellation law"}


class _FakeUnknownBlock:
    type = "image_url"  # not text or tool_use


class _FakeNoTypeBlock:
    """Block whose type attribute is missing entirely (returns 'unknown')."""
    # no .type attribute


def test_normalize_dict_passthrough():
    """A plain dict must pass through _normalize unchanged."""
    d = {"type": "text", "text": "verbatim"}
    assert _normalize(d) is d


def test_normalize_text_sdk_block():
    result = _normalize(_FakeTextBlock())
    assert result == {"type": "text", "text": "hello world"}


def test_normalize_tool_use_sdk_block():
    result = _normalize(_FakeToolUseBlock())
    assert result == {
        "type": "tool_use",
        "id": "toolu_abc123",
        "name": "search_law",
        "input": {"query": "CA gym cancellation law"},
    }


def test_normalize_unknown_block_type():
    result = _normalize(_FakeUnknownBlock())
    assert result == {"type": "image_url"}


def test_normalize_no_type_attr_returns_unknown():
    result = _normalize(_FakeNoTypeBlock())
    assert result == {"type": "unknown"}


class _FakeMessagesMultiBlock:
    def __init__(self, captured):
        self._c = captured

    def create(self, **kw):
        self._c.update(kw)

        class _R:
            content = [_FakeTextBlock(), _FakeToolUseBlock(), _FakeUnknownBlock()]
            stop_reason = "tool_use"
        return _R()


class _FakeMessagesNoStopReason:
    def __init__(self, captured):
        self._c = captured

    def create(self, **kw):
        self._c.update(kw)

        class _R:
            content = [{"type": "text", "text": "done"}]
            # deliberately no stop_reason attribute
        return _R()


class _FakeSDKMulti:
    def __init__(self, captured):
        self.messages = _FakeMessagesMultiBlock(captured)


class _FakeSDKNoStop:
    def __init__(self, captured):
        self.messages = _FakeMessagesNoStopReason(captured)


async def test_adapter_normalizes_mixed_content_blocks():
    """text + tool_use + unknown blocks all normalized; stop_reason preserved."""
    captured: dict = {}
    llm = AnthropicLLM(client=_FakeSDKMulti(captured), model="claude-sonnet-4-6")
    msg = await llm.create(system="SYS", messages=[], tools=[])

    assert msg.stop_reason == "tool_use"
    assert len(msg.content) == 3

    text_block, tool_block, unknown_block = msg.content
    assert text_block == {"type": "text", "text": "hello world"}
    assert tool_block == {
        "type": "tool_use",
        "id": "toolu_abc123",
        "name": "search_law",
        "input": {"query": "CA gym cancellation law"},
    }
    assert unknown_block == {"type": "image_url"}


async def test_adapter_defaults_stop_reason_to_end_turn_when_missing():
    """A response with no stop_reason attribute must default to 'end_turn'."""
    captured: dict = {}
    llm = AnthropicLLM(client=_FakeSDKNoStop(captured), model="claude-sonnet-4-6")
    msg = await llm.create(system="SYS", messages=[], tools=[])

    assert msg.stop_reason == "end_turn"
    assert msg.content == [{"type": "text", "text": "done"}]
