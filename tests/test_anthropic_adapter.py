from robin.anthropic_adapter import AnthropicLLM


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
