"""Regression tests for anthropic_adapter.py _safe_content — the single
API chokepoint that guarantees Anthropic-valid content on every message.

Critical invariant: typed blocks (text / tool_use / tool_result) pass through
UNCHANGED so the tool round-trip is not corrupted.  Every other branch coerces
to a valid shape.  No real Anthropic network calls — fake client only.
"""
import pytest

from robin.anthropic_adapter import AnthropicLLM, _safe_content


# ---------------------------------------------------------------------------
# _safe_content — branch-by-branch
# ---------------------------------------------------------------------------

class TestSafeContentStr:
    def test_non_empty_string_returned_verbatim(self):
        assert _safe_content("hello") == "hello"

    def test_empty_string_replaced_with_single_space(self):
        result = _safe_content("")
        assert result == " "

    def test_whitespace_only_string_returned_as_is(self):
        # A whitespace string is non-empty → returned verbatim (not replaced).
        result = _safe_content("   ")
        assert result == "   "


class TestSafeContentTypedBlocksPassthrough:
    """Typed blocks must arrive at the API byte-for-byte unchanged."""

    def test_text_block_passes_through_unchanged(self):
        block = {"type": "text", "text": "cancel my gym"}
        result = _safe_content([block])
        assert result == [{"type": "text", "text": "cancel my gym"}]

    def test_tool_use_block_passes_through_unchanged(self):
        # CRITICAL: tool round-trip must not be corrupted.
        block = {
            "type": "tool_use",
            "id": "tu_abc123",
            "name": "research_cancellation_law",
            "input": {"jurisdiction": "US-CA"},
        }
        result = _safe_content([block])
        assert result == [block]

    def test_tool_result_block_passes_through_unchanged(self):
        block = {
            "type": "tool_result",
            "tool_use_id": "tu_abc123",
            "content": "law text here",
        }
        result = _safe_content([block])
        assert result == [block]

    def test_multiple_typed_blocks_all_pass_through(self):
        blocks = [
            {"type": "text", "text": "part one"},
            {"type": "tool_use", "id": "x1", "name": "foo", "input": {}},
        ]
        assert _safe_content(blocks) == blocks

    def test_typed_block_type_value_must_be_str_to_pass_through(self):
        # type=42 (non-str) → typeless path → coerced to text block.
        block = {"type": 42, "text": "surprise"}
        result = _safe_content([block])
        assert isinstance(result, list)
        assert result[0]["type"] == "text"


class TestSafeContentTypelessDicts:
    def test_typeless_dict_with_text_key_coerced(self):
        block = {"text": "some text"}
        result = _safe_content([block])
        assert result == [{"type": "text", "text": "some text"}]

    def test_typeless_dict_with_content_key_coerced(self):
        block = {"content": "content value"}
        result = _safe_content([block])
        assert result == [{"type": "text", "text": "content value"}]

    def test_typeless_dict_text_takes_priority_over_content(self):
        # text key checked first; content is fallback.
        block = {"text": "primary", "content": "secondary"}
        result = _safe_content([block])
        assert result[0]["text"] == "primary"

    def test_typeless_dict_with_neither_key_coerced_to_str_of_block(self):
        block = {"random_key": "some value"}
        result = _safe_content([block])
        assert result[0]["type"] == "text"
        assert isinstance(result[0]["text"], str)

    def test_typeless_dict_none_text_falls_back_to_content(self):
        # text key exists but is None → fall to content key.
        block = {"text": None, "content": "fallback"}
        result = _safe_content([block])
        assert result[0]["text"] == "fallback"


class TestSafeContentBareStringsInList:
    def test_bare_string_in_list_coerced_to_text_block(self):
        result = _safe_content(["hello"])
        assert result == [{"type": "text", "text": "hello"}]

    def test_multiple_bare_strings_each_coerced(self):
        result = _safe_content(["one", "two"])
        assert result == [
            {"type": "text", "text": "one"},
            {"type": "text", "text": "two"},
        ]


class TestSafeContentMixedList:
    def test_mixed_typed_and_typeless_preserves_typed_coerces_rest(self):
        typed = {"type": "text", "text": "valid"}
        typeless = {"random": "junk"}
        bare = "bare"
        result = _safe_content([typed, typeless, bare])
        assert result[0] == typed
        assert result[1]["type"] == "text"
        assert result[2] == {"type": "text", "text": "bare"}

    def test_every_output_block_has_type_key(self):
        blocks = [
            {"type": "text", "text": "ok"},
            {"content": "no type"},
            "string",
            {"type": "tool_use", "id": "x", "name": "f", "input": {}},
        ]
        result = _safe_content(blocks)
        for block in result:
            assert "type" in block, f"block missing 'type': {block}"


class TestSafeContentNone:
    def test_none_returns_single_space(self):
        assert _safe_content(None) == " "


class TestSafeContentScalars:
    def test_integer_coerced_to_str(self):
        assert _safe_content(42) == "42"

    def test_float_coerced_to_str(self):
        assert _safe_content(3.14) == "3.14"

    def test_bool_true_coerced_to_str(self):
        assert _safe_content(True) == "True"

    def test_empty_list_replaced_with_single_space(self):
        # `out or " "` fires when list is empty.
        result = _safe_content([])
        assert result == " "


# ---------------------------------------------------------------------------
# AnthropicLLM.create() — verify _safe_content applied; no block lacks type
# ---------------------------------------------------------------------------

class _FakeMessage:
    """Fake Anthropic message response."""
    def __init__(self, content):
        self.content = content
        self.stop_reason = "end_turn"


class _FakeMessagesAPI:
    """Captures the `messages=` kwarg passed to client.messages.create()."""

    def __init__(self, content=None):
        self.captured: list[dict] | None = None
        self._content = content or [
            type("B", (), {"type": "text", "text": "ok"})()
        ]

    def create(self, *, model, max_tokens, system, messages, tools):
        self.captured = messages
        return _FakeMessage(self._content)


class _FakeClient:
    def __init__(self, content=None):
        self.messages = _FakeMessagesAPI(content)


@pytest.mark.asyncio
async def test_create_maps_content_through_safe_content_no_block_without_type():
    """Messages fed to the real API must never contain a block without 'type'."""
    fake_client = _FakeClient()
    llm = AnthropicLLM(client=fake_client)

    messages = [
        # typeless dict — must be coerced
        {"role": "user", "content": {"random": "junk"}},
        # valid typed list — must pass through
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        # bare string — must stay as string (not coerced to list)
        {"role": "user", "content": "plain string"},
    ]
    await llm.create(system="SYS", messages=messages, tools=[])

    sent = fake_client.messages.captured
    assert sent is not None

    for msg in sent:
        content = msg["content"]
        if isinstance(content, list):
            for block in content:
                assert "type" in block, f"block missing 'type': {block}"


@pytest.mark.asyncio
async def test_create_typed_tool_blocks_reach_api_unchanged():
    """Tool round-trip: typed blocks must not be corrupted through create()."""
    tool_use_block = {
        "type": "tool_use",
        "id": "tu_xyz",
        "name": "research_cancellation_law",
        "input": {"jurisdiction": "US-CA"},
    }
    fake_client = _FakeClient()
    llm = AnthropicLLM(client=fake_client)

    messages = [{"role": "assistant", "content": [tool_use_block]}]
    await llm.create(system="SYS", messages=messages, tools=[])

    sent = fake_client.messages.captured
    assert sent[0]["content"] == [tool_use_block]


@pytest.mark.asyncio
async def test_create_empty_string_content_replaced_with_space():
    """Empty string content must become ' ' before hitting the API."""
    fake_client = _FakeClient()
    llm = AnthropicLLM(client=fake_client)

    messages = [{"role": "user", "content": ""}]
    await llm.create(system="SYS", messages=messages, tools=[])

    sent = fake_client.messages.captured
    assert sent[0]["content"] == " "


@pytest.mark.asyncio
async def test_create_role_preserved_from_message_dict():
    """Role from the message dict must pass through to the API unchanged."""
    fake_client = _FakeClient()
    llm = AnthropicLLM(client=fake_client)

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    await llm.create(system="SYS", messages=messages, tools=[])

    sent = fake_client.messages.captured
    assert sent[0]["role"] == "user"
    assert sent[1]["role"] == "assistant"
