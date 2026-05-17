from robin.loop import run_turn
from tests.fakes import FakeLLM


def _text(blocks):
    return [{"type": "text", "text": t} for t in blocks]


def _tool_use(tid, name, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


async def test_final_only_response_streams_interim_then_final():
    llm = FakeLLM([_Msg(_text(["Hi, this is Robin."]), "end_turn")])
    out = [chunk async for chunk in run_turn(
        "hello", [], system="SYS", llm=llm, tool_impls={})]
    assert out[0]["interim"] is True
    assert out[-1]["text"] == "Hi, this is Robin."
    assert "interim" not in out[-1]


async def test_tool_call_then_final():
    calls = []

    async def fake_research(**kw):
        calls.append(kw)
        return {"citations": [{"citation": "X"}], "status": "OK"}

    llm = FakeLLM([
        _Msg([_tool_use("t1", "research_cancellation_law",
                        {"jurisdiction": "US-CA"})], "tool_use"),
        _Msg(_text(["I pulled the law."]), "end_turn"),
    ])
    out = [c async for c in run_turn(
        "cancel my gym", [], system="SYS", llm=llm,
        tool_impls={"research_cancellation_law": fake_research})]
    assert calls and calls[0]["jurisdiction"] == "US-CA"
    assert out[-1]["text"] == "I pulled the law."


async def test_loop_caps_at_six_tool_turns():
    async def loop_tool(**kw):
        return {"status": "OK"}

    scripted = [_Msg([_tool_use(f"t{i}", "research_cancellation_law",
                                {"jurisdiction": "US-CA"})], "tool_use")
                for i in range(8)]
    llm = FakeLLM(scripted)
    out = [c async for c in run_turn(
        "x", [], system="SYS", llm=llm,
        tool_impls={"research_cancellation_law": loop_tool})]
    assert out[-1].get("interim") is not True
    assert len(llm.calls) == 6


async def test_history_is_included_in_messages():
    captured = {}

    class _LLM:
        async def create(self, *, system, messages, tools):
            captured["messages"] = messages

            class _M:
                content = [{"type": "text", "text": "24 Hour Gym, got it."}]
                stop_reason = "end_turn"
            return _M()

    hist = [{"direction": "inbound", "content": "cancel my gym"},
            {"direction": "outbound", "content": "Which gym?"}]
    _ = [c async for c in run_turn("24 Hour Gym", hist, system="S",
                                   llm=_LLM(), tool_impls={})]
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert captured["messages"][-1]["content"] == "24 Hour Gym"


async def test_keepalive_interim_emitted_before_tool_batch():
    async def slow_tool(**kw):
        return {"status": "OK"}

    llm = FakeLLM([
        _Msg([_tool_use("t1", "research_cancellation_law",
                        {"jurisdiction": "US-CA"})], "tool_use"),
        _Msg(_text(["Done."]), "end_turn"),
    ])
    out = [c async for c in run_turn(
        "cancel my gym", [], system="SYS", llm=llm,
        tool_impls={"research_cancellation_law": slow_tool})]
    interims = [c for c in out if c.get("interim") is True]
    assert len(interims) >= 2
    assert out[-1].get("interim") is not True
    assert out[-1]["text"] == "Done."
