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


# --- W3: FakeMossClient ---
# (dataclass is imported at module top.)

@dataclass
class FakeMossDoc:
    id: str
    text: str
    score: float = 1.0

@dataclass
class FakeMossQueryResult:
    docs: list  # list[FakeMossDoc]
    time_taken_ms: int = 5

class FakeMossClient:
    """Scriptable stand-in for moss.MossClient.

    list_indexes_returns: list of index names to return from list_indexes().
    query_returns:        FakeMossQueryResult to return from query().
    create_raises:        if set, create_index() raises this.
    query_raises:         if set, query() raises this.
    """
    def __init__(
        self,
        list_indexes_returns: list[str] | None = None,
        query_returns: FakeMossQueryResult | None = None,
        create_raises: Exception | None = None,
        query_raises: Exception | None = None,
    ):
        self.list_indexes_returns = list_indexes_returns or []
        self.query_returns = query_returns or FakeMossQueryResult(docs=[])
        self.create_raises = create_raises
        self.query_raises = query_raises
        self.created: list[dict] = []     # records create_index() calls
        self.queried: list[dict] = []     # records query() calls

    async def list_indexes(self) -> list[str]:
        return list(self.list_indexes_returns)

    async def create_index(self, name: str, docs: list) -> None:
        if self.create_raises:
            raise self.create_raises
        self.created.append({"name": name, "docs": docs})

    async def query(self, index_name: str, query_str: str, options=None):
        self.queried.append({"index": index_name, "query": query_str, "options": options})
        if self.query_raises:
            raise self.query_raises
        return self.query_returns
# --- end W3 ---
