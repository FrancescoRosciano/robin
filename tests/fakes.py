# tests/fakes.py
import asyncio
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


# --- W2: FakeAgentMailClient ---

class _FakeInbox:
    def __init__(self, inbox_id: str, email: str):
        self.inbox_id = inbox_id
        self.email = email


class _FakeMessage:
    def __init__(self, message_id: str, thread_id: str):
        self.message_id = message_id
        self.thread_id = thread_id


class _FakeMessages:
    def __init__(self, sent: list):
        self._sent = sent  # shared reference to FakeAgentMailClient.sent

    async def send(self, inbox_id: str, *, to: str, subject: str, text: str):
        self._sent.append({"inbox_id": inbox_id, "to": to,
                           "subject": subject, "text": text})
        return _FakeMessage(message_id="msg-fake-01", thread_id="thr-fake-01")


class _FakeInboxes:
    def __init__(self, inbox_id: str, email: str, sent: list,
                 created: list, raise_on_send: Exception | None = None):
        self._inbox_id = inbox_id
        self._email = email
        self._created = created
        self._raise_on_send = raise_on_send
        self.messages = _FakeMessages(sent)

    async def create(self, username: str, display_name: str):
        self._created.append({"username": username, "display_name": display_name})
        return _FakeInbox(self._inbox_id, self._email)


class FakeAgentMailClient:
    """Mimics agentmail.AsyncAgentMail for unit tests.

    Attributes:
        sent:    list of dicts from inboxes.messages.send calls
        created: list of dicts from inboxes.create calls
    """

    def __init__(
        self,
        inbox_id: str = "inbox-test-01",
        inbox_email: str = "robin-confirms@agentmail.to",
        raise_on_send: Exception | None = None,
    ):
        self.sent: list[dict] = []
        self.created: list[dict] = []
        self.inboxes = _FakeInboxes(
            inbox_id=inbox_id,
            email=inbox_email,
            sent=self.sent,
            created=self.created,
            raise_on_send=raise_on_send,
        )


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


# >>> W4 FakeEventBus <<<
class FakeEventBus:
    """Drop-in for EventBus in tests. Stores published events for assertion."""

    def __init__(self) -> None:
        self.published: list[dict] = []
        self._queues: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    async def publish_event(self, event: str, data: dict) -> None:
        item = {"event": event, "data": data}
        self.published.append(item)
        for q in list(self._queues):
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass
# <<< end W4 FakeEventBus <<<
