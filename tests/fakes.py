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


# --- W1: FakeSupermemoryClient ---

class _FakeSearchResult:
    def __init__(self, content: str, similarity: float = 0.9):
        self.content = content
        self.memory = content
        self.similarity = similarity


class _FakeSearchResponse:
    def __init__(self, items: list[str]):
        self.results = [_FakeSearchResult(t) for t in items]


class _FakeSearchNamespace:
    def __init__(self, items: list[str], raise_exc: Exception | None = None):
        self._items = items
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def documents(self, *, q, container_tag, limit=5,
                        chunk_threshold=0.3, rerank=False,
                        rewrite_query=False):
        self.calls.append({"q": q, "container_tag": container_tag})
        if self._raise:
            raise self._raise
        return _FakeSearchResponse(self._items)


class FakeSupermemoryClient:
    """Scriptable fake for AsyncSupermemory.

    Usage:
        client = FakeSupermemoryClient(items=["- Cancelled 24 Hour Gym"])
        # or: client = FakeSupermemoryClient(items=[], raise_exc=TimeoutError())
    """

    def __init__(self, items: list[str] = (), *,
                 raise_exc: Exception | None = None,
                 add_raise: Exception | None = None):
        self.search = _FakeSearchNamespace(list(items), raise_exc)
        self._add_raise = add_raise
        self.added: list[dict] = []

    async def add(self, *, content: str, container_tag: str,
                  metadata: dict | None = None):
        if self._add_raise:
            raise self._add_raise
        self.added.append({"content": content, "container_tag": container_tag,
                           "metadata": metadata})
        return {"status": "queued"}
