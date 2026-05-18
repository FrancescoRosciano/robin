"""Streaming-completion path of run_turn.

The loop prefers an ``llm.stream`` (async generator of ``(kind, payload)``
events) so model text is spoken sentence-by-sentence as it arrives —
killing the dead air of waiting for a full completion. When the llm has
no ``.stream`` the loop must behave EXACTLY as before (every existing
fake injects only ``.create``), so the legacy path is pinned here too.
"""
import pytest

from robin import loop


class _Final:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class ScriptedStreamLLM:
    """Exposes ``.stream``; each call yields the next scripted
    (text_chunks, final_message) pair."""

    def __init__(self, scripts):
        self._scripts = scripts
        self._i = 0

    async def stream(self, *, system, messages, tools):
        chunks, final = self._scripts[self._i]
        self._i += 1
        for c in chunks:
            yield ("text", c)
        yield ("final", final)


class CreateOnlyLLM:
    """No ``.stream`` — must hit the unchanged legacy path."""

    def __init__(self, final):
        self._final = final

    async def create(self, *, system, messages, tools):
        return self._final


async def _collect(gen):
    return [c async for c in gen]


@pytest.mark.asyncio
async def test_stream_emits_completed_sentences_interim_last_as_final():
    text = "Hello there. How can I help you today?"
    llm = ScriptedStreamLLM([(["Hello there. ", "How can I help you",
                               " today?"],
                              _Final([{"type": "text", "text": text}]))])
    out = await _collect(loop.run_turn("hi", [], system="S", llm=llm,
                                       tool_impls={}))

    assert out[0] == {"text": loop._INTERIM_ACK, "interim": True}
    interim_texts = [c["text"] for c in out if c.get("interim")]
    assert "Hello there." in interim_texts
    # exactly one closing (non-interim) line, and it is last
    finals = [c for c in out if "interim" not in c]
    assert len(finals) == 1 and out[-1] == finals[0]
    assert finals[0] == {"text": "How can I help you today?"}


@pytest.mark.asyncio
async def test_single_sentence_has_no_spurious_interim():
    llm = ScriptedStreamLLM([(["Just one sentence."],
                              _Final([{"type": "text",
                                       "text": "Just one sentence."}]))])
    out = await _collect(loop.run_turn("hi", [], system="S", llm=llm,
                                       tool_impls={}))
    # only the ack is interim; the lone sentence is the final close
    assert out == [{"text": loop._INTERIM_ACK, "interim": True},
                   {"text": "Just one sentence."}]


@pytest.mark.asyncio
async def test_stream_tool_use_runs_tool_then_streams_answer():
    calls = {}

    async def research(**kw):
        calls.update(kw)
        return {"status": "OK",
                "citations": [{"citation": "CA 1812", "operative_quote": "q"}]}

    tool_final = _Final([{"type": "tool_use", "id": "t1",
                          "name": "research_cancellation_law",
                          "input": {"jurisdiction": "California"}}],
                        stop_reason="tool_use")
    answer_final = _Final([{"type": "text",
                            "text": "Found it. You can cancel."}])
    llm = ScriptedStreamLLM([([], tool_final),
                             (["Found it. ", "You can cancel."],
                              answer_final)])

    out = await _collect(loop.run_turn(
        "cancel my gym", [], system="S", llm=llm,
        tool_impls={"research_cancellation_law": research}, call_id="c1"))

    assert calls == {"jurisdiction": "California"}
    # tool turn with no pre-tool text → keepalive interim still emitted
    assert {"text": loop._KEEPALIVE, "interim": True} in out
    assert out[-1] == {"text": "You can cancel."}
    from robin import session
    done, _ = session.research_status("c1")
    assert done is True


@pytest.mark.asyncio
async def test_stream_no_text_falls_back_to_forced_final():
    llm = ScriptedStreamLLM([([], _Final([]))])
    out = await _collect(loop.run_turn("hi", [], system="S", llm=llm,
                                       tool_impls={}))
    assert out[-1] == {"text": loop._FORCED_FINAL}


class FlakyStreamLLM:
    """`.stream` raises mid-flight; `.create` still works — the loop must
    degrade to one completion and never let the exception 500 the call."""

    def __init__(self, final):
        self._final = final

    async def stream(self, *, system, messages, tools):
        yield ("text", "partial ")
        raise RuntimeError("upstream stream dropped")

    async def create(self, *, system, messages, tools):
        return self._final


@pytest.mark.asyncio
async def test_stream_failure_falls_back_to_create():
    llm = FlakyStreamLLM(_Final([{"type": "text",
                                  "text": "Recovered answer."}]))
    out = await _collect(loop.run_turn("hi", [], system="S", llm=llm,
                                       tool_impls={}))
    assert out[-1] == {"text": "Recovered answer."}
    assert all("error" not in str(c).lower() for c in out)


@pytest.mark.asyncio
async def test_create_only_llm_keeps_legacy_behaviour_unchanged():
    llm = CreateOnlyLLM(_Final([{"type": "text", "text": "Legacy answer."}]))
    out = await _collect(loop.run_turn("hi", [], system="S", llm=llm,
                                       tool_impls={}))
    assert out == [{"text": loop._INTERIM_ACK, "interim": True},
                   {"text": "Legacy answer."}]
