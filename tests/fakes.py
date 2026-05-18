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
