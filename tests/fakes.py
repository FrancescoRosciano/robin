# tests/fakes.py
from dataclasses import dataclass


@dataclass
class _BUResult:
    output: str


class FakeBrowser:
    """Mimics browser_use_sdk AsyncBrowserUse.run."""

    def __init__(self, output: str, raise_exc: Exception | None = None):
        self._output = output
        self._raise = raise_exc
        self.calls: list[str] = []

    async def run(self, task: str):
        self.calls.append(task)
        if self._raise:
            raise self._raise
        return _BUResult(self._output)


class FakeLLM:
    """Returns scripted Anthropic-shaped responses, one per create() call."""

    def __init__(self, scripted: list):
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    async def create(self, *, system, messages, tools):
        self.calls.append({"system": system, "messages": messages})
        return self._scripted.pop(0)


class FakeAgentPhoneClient:
    """Same interface as src/robin/agentphone_client.py (Plan 04)."""

    def __init__(self, turns: list[tuple[str, str]], call_id: str = "call_test"):
        self._turns = turns
        self._call_id = call_id
        self.placed: list[dict] = []

    async def place_call(self, *, agent_id, to_number, initial_greeting,
                         system_prompt, from_number_id):
        self.placed.append({"to_number": to_number, "agent_id": agent_id})
        return self._call_id

    async def stream_transcript(self, call_id):
        from robin.agentphone_client import TranscriptTurn
        for role, content in self._turns:
            yield TranscriptTurn(role=role, content=content, created_at="t")

    async def get_recording_url(self, call_id):
        return f"https://rec.example/{call_id}.mp3"
