"""tests/test_extensions.py — W0 extension seam unit tests.

Each test is self-contained: no live telephony, no real SDKs, no env vars.
All async tests use pytest-asyncio (already in requirements-dev.txt).
"""
import asyncio
import pytest

# These imports will fail until the seam is implemented (that's the RED step).
from robin.extensions import ExtensionHooks, PromptEnricher, ResearchHook, OutcomeHook
from robin.loop import run_turn, _record_session
from robin.app import build_app
from robin.stage import make_stage_router
from tests.fakes import FakeLLM


def _make_msg(texts: list[str], stop_reason: str):
    class _M:
        content = [{"type": "text", "text": t} for t in texts]
    _M.stop_reason = stop_reason
    return _M()


def test_extension_hooks_default_is_all_empty():
    """ExtensionHooks() must be constructible with zero args and all fields empty."""
    hooks = ExtensionHooks()
    assert hooks.prompt_enrichers == ()
    assert hooks.on_research == ()
    assert hooks.on_outcome == ()
    assert hooks.event_bus is None


def test_extension_hooks_is_frozen():
    """ExtensionHooks is a frozen dataclass — mutation must raise."""
    hooks = ExtensionHooks()
    with pytest.raises((AttributeError, TypeError)):
        hooks.event_bus = object()  # type: ignore[misc]


def test_extension_hooks_callable_aliases_exist():
    """PromptEnricher, ResearchHook, OutcomeHook must be importable type aliases."""
    # Just confirm they are callable/type objects; no runtime check needed.
    assert PromptEnricher is not None
    assert ResearchHook is not None
    assert OutcomeHook is not None


async def test_run_turn_with_empty_hooks_output_identical_to_no_hooks():
    """run_turn with ExtensionHooks() must yield the same chunks as today's baseline.

    The baseline is captured inline: one interim ack, then the scripted final text.
    """
    llm = FakeLLM([_make_msg(["Hi, I'm Robin."], "end_turn")])
    hooks = ExtensionHooks()

    out_with_hooks = [c async for c in run_turn(
        "hello", [], system="SYS", llm=llm,
        tool_impls={}, call_id=None, hooks=hooks)]

    llm2 = FakeLLM([_make_msg(["Hi, I'm Robin."], "end_turn")])
    out_no_hooks = [c async for c in run_turn(
        "hello", [], system="SYS", llm=llm2,
        tool_impls={}, call_id=None)]

    assert out_with_hooks == out_no_hooks


async def test_prompt_enrichers_append_in_registration_order():
    """Two enrichers: first returns 'AAA', second returns 'BBB'.
    effective_system must end with '\\n\\nAAA\\n\\nBBB' in that order."""
    captured_systems: list[str] = []

    class _CaptureLLM:
        async def create(self, *, system, messages, tools):
            captured_systems.append(system)
            return _make_msg(["done"], "end_turn")

    async def enricher_a(call_id):
        return "AAA"

    async def enricher_b(call_id):
        return "BBB"

    hooks = ExtensionHooks(prompt_enrichers=(enricher_a, enricher_b))
    _ = [c async for c in run_turn(
        "hi", [], system="BASE", llm=_CaptureLLM(),
        tool_impls={}, call_id="c1", hooks=hooks)]

    assert len(captured_systems) == 1
    sys = captured_systems[0]
    assert sys.endswith("\n\nAAA\n\nBBB"), f"Unexpected system: {sys!r}"
    assert sys.startswith("BASE")


async def test_prompt_enricher_returning_empty_string_is_skipped():
    """An enricher returning '' must not add blank lines to the system prompt."""
    captured_systems: list[str] = []

    class _CaptureLLM:
        async def create(self, *, system, messages, tools):
            captured_systems.append(system)
            return _make_msg(["done"], "end_turn")

    async def enricher_empty(call_id):
        return ""

    async def enricher_real(call_id):
        return "REAL"

    hooks = ExtensionHooks(prompt_enrichers=(enricher_empty, enricher_real))
    _ = [c async for c in run_turn(
        "hi", [], system="BASE", llm=_CaptureLLM(),
        tool_impls={}, call_id="c1", hooks=hooks)]

    sys = captured_systems[0]
    assert "REAL" in sys
    assert "\n\n\n" not in sys   # no double-blank from empty return


async def test_raising_enricher_is_swallowed_and_turn_completes():
    """An enricher that raises must not crash the turn; the next enricher still runs."""
    called = []

    async def bad_enricher(call_id):
        raise ValueError("enricher kaboom")

    async def good_enricher(call_id):
        called.append("good")
        return "GOOD"

    class _LLM:
        async def create(self, *, system, messages, tools):
            return _make_msg(["done"], "end_turn")

    hooks = ExtensionHooks(prompt_enrichers=(bad_enricher, good_enricher))
    out = [c async for c in run_turn(
        "hi", [], system="BASE", llm=_LLM(),
        tool_impls={}, call_id="c1", hooks=hooks)]

    # Turn must still deliver a final chunk
    assert any("interim" not in c for c in out)
    # The good enricher still ran
    assert called == ["good"]


async def test_on_research_hook_fires_with_exact_payload():
    """on_research must be called with (call_id, out_dict) when research returns OK."""
    received: list[tuple] = []

    async def research_hook(call_id, payload):
        received.append((call_id, payload))

    # Simulate what _record_session sees
    out = {"status": "OK", "citations": [{"citation": "FTC §425", "operative_quote": "easy cancel"}]}
    hooks = ExtensionHooks(on_research=(research_hook,))

    await _record_session("call_42", "research_cancellation_law", {}, out, hooks)

    assert len(received) == 1
    cid, payload = received[0]
    assert cid == "call_42"
    # payload is the full out dict
    assert payload is out
    assert payload["status"] == "OK"


async def test_on_research_hook_does_not_fire_when_status_not_ok():
    """on_research must NOT fire if research returns status != 'OK'."""
    received: list = []

    async def research_hook(call_id, payload):
        received.append(payload)

    out = {"status": "ERR", "citations": []}
    hooks = ExtensionHooks(on_research=(research_hook,))

    await _record_session("call_42", "research_cancellation_law", {}, out, hooks)

    assert received == []


async def test_on_research_hook_does_not_fire_for_other_tools():
    """on_research must not fire for place_negotiation_call or deliver_result."""
    received: list = []

    async def research_hook(call_id, payload):
        received.append(payload)

    hooks = ExtensionHooks(on_research=(research_hook,))

    await _record_session("c1", "place_negotiation_call", {}, {"call_id": "x"}, hooks)
    await _record_session("c1", "deliver_result", {"summary": "done"}, {"delivered": True}, hooks)

    assert received == []
