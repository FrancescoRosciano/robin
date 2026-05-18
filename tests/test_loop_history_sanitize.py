"""Regression tests for loop.py history-sanitization hot-path.

Pins _history_text, _history_role, and the run_turn message-build contract
introduced in the Plan 04 hardening pass.  No network, no telephony, no PII.
"""
import pytest

from robin.loop import _history_role, _history_text, run_turn
from tests.fakes import FakeLLM


# ---------------------------------------------------------------------------
# Helpers (mirrors test_loop.py style)
# ---------------------------------------------------------------------------

def _text_blocks(*texts):
    return [{"type": "text", "text": t} for t in texts]


class _Msg:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# _history_text — branch coverage
# ---------------------------------------------------------------------------

class TestHistoryText:
    def test_plain_string_returned_verbatim(self):
        assert _history_text("hello caller") == "hello caller"

    def test_empty_string_returned_as_empty(self):
        assert _history_text("") == ""

    def test_list_of_strings_joined(self):
        result = _history_text(["cancel", "my gym"])
        assert result == "cancel my gym"

    def test_list_of_text_dicts_joined(self):
        blocks = [{"type": "text", "text": "cancel"}, {"type": "text", "text": "now"}]
        assert _history_text(blocks) == "cancel now"

    def test_list_of_content_key_dicts_joined(self):
        blocks = [{"content": "cancel"}, {"content": "now"}]
        assert _history_text(blocks) == "cancel now"

    def test_list_mixed_text_and_content_keys(self):
        blocks = [{"text": "first"}, {"content": "second"}]
        result = _history_text(blocks)
        assert "first" in result
        assert "second" in result

    def test_list_with_bare_strings_and_dicts_mixed(self):
        blocks = ["bare string", {"text": "dict part"}]
        result = _history_text(blocks)
        assert "bare string" in result
        assert "dict part" in result

    def test_list_entry_with_neither_text_nor_content_contributes_empty(self):
        # A typeless block with no useful key must not crash; contributes nothing.
        blocks = [{"type": "tool_use", "id": "x"}, {"text": "real part"}]
        result = _history_text(blocks)
        assert "real part" in result

    def test_empty_list_returns_empty_string(self):
        assert _history_text([]) == ""

    def test_dict_with_text_key(self):
        assert _history_text({"text": "single dict"}) == "single dict"

    def test_dict_with_content_key(self):
        assert _history_text({"content": "from content key"}) == "from content key"

    def test_dict_with_neither_key_returns_empty(self):
        result = _history_text({"type": "tool_use"})
        assert result == ""

    def test_none_returns_empty_string(self):
        assert _history_text(None) == ""

    def test_integer_junk_coerced_to_string(self):
        # Non-str/list/dict falls to str(content or ""); 42 → "42"
        result = _history_text(42)
        assert result == "42"

    def test_false_coerced_to_empty_via_or(self):
        # str(False or "") → "" because False is falsy
        result = _history_text(False)
        assert result == ""

    def test_whitespace_only_entries_stripped_and_skipped(self):
        blocks = [{"text": "  "}, {"text": "real"}]
        result = _history_text(blocks)
        # "  ".strip() == "" → skipped; only "real" survives
        assert result == "real"


# ---------------------------------------------------------------------------
# _history_role — direction + role/speaker/from variants
# ---------------------------------------------------------------------------

class TestHistoryRole:
    # --- direction: inbound variants → "user" ---
    def test_direction_inbound_returns_user(self):
        assert _history_role({"direction": "inbound"}) == "user"

    def test_direction_in_returns_user(self):
        assert _history_role({"direction": "in"}) == "user"

    def test_direction_incoming_returns_user(self):
        assert _history_role({"direction": "incoming"}) == "user"

    # --- direction: outbound variants → "assistant" ---
    def test_direction_outbound_returns_assistant(self):
        assert _history_role({"direction": "outbound"}) == "assistant"

    def test_direction_out_returns_assistant(self):
        assert _history_role({"direction": "out"}) == "assistant"

    def test_direction_outgoing_returns_assistant(self):
        assert _history_role({"direction": "outgoing"}) == "assistant"

    # --- direction case-insensitive ---
    def test_direction_uppercase_inbound(self):
        assert _history_role({"direction": "INBOUND"}) == "user"

    def test_direction_uppercase_outbound(self):
        assert _history_role({"direction": "OUTBOUND"}) == "assistant"

    # --- role key variants ---
    def test_role_assistant_returns_assistant(self):
        assert _history_role({"role": "assistant"}) == "assistant"

    def test_role_agent_returns_assistant(self):
        assert _history_role({"role": "agent"}) == "assistant"

    def test_role_robin_returns_assistant(self):
        assert _history_role({"role": "robin"}) == "assistant"

    def test_role_bot_returns_assistant(self):
        assert _history_role({"role": "bot"}) == "assistant"

    def test_role_user_falls_through_to_user(self):
        assert _history_role({"role": "user"}) == "user"

    # --- speaker key ---
    def test_speaker_robin_returns_assistant(self):
        assert _history_role({"speaker": "robin"}) == "assistant"

    def test_speaker_caller_returns_user(self):
        assert _history_role({"speaker": "caller"}) == "user"

    # --- from key ---
    def test_from_bot_returns_assistant(self):
        assert _history_role({"from": "bot"}) == "assistant"

    def test_from_user_returns_user(self):
        assert _history_role({"from": "user"}) == "user"

    # --- unknown / missing → safe default "user" ---
    def test_unknown_direction_falls_back_to_user(self):
        assert _history_role({"direction": "sideways"}) == "user"

    def test_no_keys_returns_user(self):
        assert _history_role({}) == "user"

    def test_unrecognized_role_value_returns_user(self):
        assert _history_role({"role": "receptionist"}) == "user"


# ---------------------------------------------------------------------------
# run_turn message-build — non-dict history skipping + transcript appended last
# ---------------------------------------------------------------------------

class TestRunTurnMessageBuild:
    @pytest.mark.asyncio
    async def test_non_dict_history_entries_are_skipped(self):
        """Strings, ints, None in history must be silently dropped."""
        captured = {}

        class _CaptureLLM:
            async def create(self, *, system, messages, tools):
                captured["messages"] = messages
                return _Msg(_text_blocks("ok"))

        history = [
            "bare string",          # not a dict → skip
            42,                     # int → skip
            None,                   # None → skip
            {"direction": "inbound", "content": "real entry"},  # dict → keep
        ]
        _ = [c async for c in run_turn(
            "transcript text", history,
            system="SYS", llm=_CaptureLLM(), tool_impls={})]

        msgs = captured["messages"]
        # Only the dict entry + the transcript itself should appear
        assert len(msgs) == 2
        assert msgs[0]["content"] == "real entry"
        assert msgs[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_transcript_always_appended_as_final_user_message(self):
        """The live transcript must always be the last message, role=user."""
        captured = {}

        class _CaptureLLM:
            async def create(self, *, system, messages, tools):
                captured["messages"] = messages
                return _Msg(_text_blocks("done"))

        history = [
            {"direction": "inbound", "content": "first"},
            {"direction": "outbound", "content": "second"},
        ]
        _ = [c async for c in run_turn(
            "LIVE TRANSCRIPT", history,
            system="SYS", llm=_CaptureLLM(), tool_impls={})]

        msgs = captured["messages"]
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "LIVE TRANSCRIPT"

    @pytest.mark.asyncio
    async def test_empty_content_history_entries_are_excluded(self):
        """History entries whose content flattens to '' must not be appended."""
        captured = {}

        class _CaptureLLM:
            async def create(self, *, system, messages, tools):
                captured["messages"] = messages
                return _Msg(_text_blocks("ok"))

        history = [
            {"direction": "inbound", "content": ""},    # empty string → falsy → skip
            {"direction": "inbound", "content": None},  # None → "" → falsy → skip
            {"direction": "outbound", "content": "real"},
        ]
        _ = [c async for c in run_turn(
            "transcript", history,
            system="S", llm=_CaptureLLM(), tool_impls={})]

        msgs = captured["messages"]
        contents = [m["content"] for m in msgs]
        assert "" not in contents
        assert "real" in contents

    @pytest.mark.asyncio
    async def test_all_non_dict_history_yields_only_transcript(self):
        """When every history entry is non-dict, messages = [transcript only]."""
        captured = {}

        class _CaptureLLM:
            async def create(self, *, system, messages, tools):
                captured["messages"] = messages
                return _Msg(_text_blocks("ok"))

        history = ["string", 99, None, False]
        _ = [c async for c in run_turn(
            "only me", history,
            system="S", llm=_CaptureLLM(), tool_impls={})]

        assert len(captured["messages"]) == 1
        assert captured["messages"][0]["content"] == "only me"

    @pytest.mark.asyncio
    async def test_fake_llm_pattern_from_existing_tests_works_here(self):
        """Confirm FakeLLM from fakes.py integrates correctly with run_turn."""
        llm = FakeLLM([_Msg(_text_blocks("Robin here."))])
        out = [c async for c in run_turn(
            "hello", [], system="SYS", llm=llm, tool_impls={})]
        assert out[0]["interim"] is True
        assert out[-1]["text"] == "Robin here."
