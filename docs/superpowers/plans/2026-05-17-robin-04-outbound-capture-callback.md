# Robin Plan 04 — Outbound + Capture + Callback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`)
> syntax. TDD against fakes — **no API keys, no live telephony**. This
> plan **replaces the Plan 03 `outbound.py` stub** keeping the exact
> frozen signatures.

**Goal:** Implement the Coordination Model — `AgentPhoneClient` (real
httpx: place call, SSE transcript stream, recording URL) and
`outbound.py` (`place_negotiation_call` dials the simulated receptionist
and spawns one asyncio task that consumes that call's SSE transcript
until it ends, classifies it with Plan 01, and stores the `Outcome`;
`deliver_result` places the callback or returns the stay-on text).

**Architecture:** Exactly one async primitive (design "Coordination
Model"): *one asyncio task consuming one SSE stream until the call ends,
then classify.* No call bridging, no race. An in-process
`CallRegistry` maps `call_id → Outcome|None`. Imports Plan 01
`classify_transcript`. Interface frozen in the 00 doc.

**Tech Stack:** Python 3.11+, httpx (real client + `MockTransport` in
tests), asyncio, pytest-asyncio. Reuses `tests/fakes.py` from Plan 03.

---

## File Structure

- Create `src/robin/agentphone_client.py` — `AgentPhoneClient`, `TranscriptTurn` (frozen 00 interface).
- Replace `src/robin/outbound.py` — `CallRegistry`, `place_negotiation_call`, `deliver_result` (same signatures as the Plan 03 stub).
- Create `tests/fixtures/transcript_done.sse` — canned SSE stream ending in the DONE transcript.
- Create `tests/fixtures/transcript_blocked.sse` — canned SSE stream with no confirmation.
- Create `tests/test_agentphone_client.py`, `tests/test_outbound.py`.

---

### Task 1: AgentPhone client (place call / SSE stream / recording)

**Files:**
- Create: `src/robin/agentphone_client.py`
- Create: `tests/fixtures/transcript_done.sse`
- Create: `tests/fixtures/transcript_blocked.sse`
- Test: `tests/test_agentphone_client.py`

- [ ] **Step 1: Write the SSE fixtures**

`tests/fixtures/transcript_done.sse` (the event shape from
`agentphone-notes.md`: `connected` → `turn`… → `ended`):

```text
event: connected
data: {"callId":"call_x","direction":"outbound","status":"in_progress"}

event: turn
data: {"role":"user","content":"I need to cancel my membership.","createdAt":"t1"}

event: turn
data: {"role":"agent","content":"You can only cancel in person at your home club.","createdAt":"t2"}

event: turn
data: {"role":"user","content":"I've pulled the law; you have two options. Easy or hard. Your decision.","createdAt":"t3"}

event: turn
data: {"role":"agent","content":"Fine — I'll cancel your subscription and refund your last month. Your confirmation number is 24HF-4471.","createdAt":"t4"}

event: ended
data: {"callId":"call_x","status":"completed","durationSeconds":42}

```

`tests/fixtures/transcript_blocked.sse`:

```text
event: connected
data: {"callId":"call_y","direction":"outbound","status":"in_progress"}

event: turn
data: {"role":"agent","content":"You can only cancel in person. I cannot help further.","createdAt":"t1"}

event: ended
data: {"callId":"call_y","status":"completed","durationSeconds":12}

```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_agentphone_client.py
import httpx
import pytest
from robin.agentphone_client import AgentPhoneClient, TranscriptTurn


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/calls" and request.method == "POST":
        return httpx.Response(200, json={"id": "call_x"})
    if request.url.path == "/v1/calls/call_x/transcript/stream":
        return httpx.Response(
            200, text=open("tests/fixtures/transcript_done.sse").read(),
            headers={"content-type": "text/event-stream"})
    if request.url.path == "/v1/calls/call_x":
        return httpx.Response(200, json={"recordingUrl": "https://r/c.mp3",
                                         "recordingAvailable": True})
    return httpx.Response(404)


def _client() -> AgentPhoneClient:
    c = AgentPhoneClient(api_key="k")
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="https://api.agentphone.ai/v1")
    return c


async def test_place_call_returns_call_id():
    cid = await _client().place_call(
        agent_id="agt", to_number="+15550000002",
        initial_greeting="Hi, this is Robin.", system_prompt="SYS",
        from_number_id="num")
    assert cid == "call_x"


async def test_stream_transcript_yields_turns_until_ended():
    turns = [t async for t in _client().stream_transcript("call_x")]
    assert all(isinstance(t, TranscriptTurn) for t in turns)
    assert turns[-1].content.endswith("24HF-4471.")
    assert turns[0].role in ("user", "agent")


async def test_get_recording_url():
    assert await _client().get_recording_url("call_x") == "https://r/c.mp3"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_agentphone_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.agentphone_client'`.

- [ ] **Step 4: Write `src/robin/agentphone_client.py`**

```python
"""Thin AgentPhone REST/SSE client. Interface frozen in the 00 doc."""
import json
from dataclasses import dataclass
from typing import AsyncIterator

import httpx


@dataclass(frozen=True)
class TranscriptTurn:
    role: str
    content: str
    created_at: str


class AgentPhoneClient:
    def __init__(self, api_key: str,
                 base_url: str = "https://api.agentphone.ai/v1") -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(30.0, read=None))

    async def place_call(self, *, agent_id: str, to_number: str,
                         initial_greeting: str, system_prompt: str,
                         from_number_id: str) -> str:
        r = await self._http.post("/calls", json={
            "agentId": agent_id, "toNumber": to_number,
            "initialGreeting": initial_greeting,
            "systemPrompt": system_prompt, "fromNumberId": from_number_id})
        r.raise_for_status()
        body = r.json()
        return body.get("id") or body.get("callId")

    async def stream_transcript(self, call_id: str
                                ) -> AsyncIterator[TranscriptTurn]:
        async with self._http.stream(
                "GET", f"/calls/{call_id}/transcript/stream") as resp:
            resp.raise_for_status()
            event = ""
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    if event == "turn" and data:
                        d = json.loads(data)
                        yield TranscriptTurn(
                            role=d.get("role", ""),
                            content=d.get("content", ""),
                            created_at=d.get("createdAt", ""))
                    elif event == "ended":
                        return

    async def get_recording_url(self, call_id: str) -> str | None:
        r = await self._http.get(f"/calls/{call_id}")
        r.raise_for_status()
        return r.json().get("recordingUrl")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_agentphone_client.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/robin/agentphone_client.py tests/test_agentphone_client.py tests/fixtures/transcript_done.sse tests/fixtures/transcript_blocked.sse
git commit -m "feat: AgentPhone client (place call, SSE stream, recording)"
```

---

### Task 2: Call registry + capture task

**Files:**
- Replace: `src/robin/outbound.py`
- Test: `tests/test_outbound.py` (Step 1–6)

- [ ] **Step 1: Write the failing test (capture → classify → store)**

```python
# tests/test_outbound.py
import asyncio
import pytest
from robin.models import OutcomeStatus
from robin.outbound import CallRegistry, capture_and_classify
from tests.fakes import FakeAgentPhoneClient

DONE_TURNS = [
    ("user", "I need to cancel."),
    ("agent", "Cancel in person only."),
    ("user", "Two options: easy or hard. Your decision."),
    ("agent", "Fine — I'll cancel your subscription and refund your last "
              "month. Your confirmation number is 24HF-4471."),
]
BLOCKED_TURNS = [("agent", "Cancel in person only. I cannot help further.")]


async def test_capture_stores_done_outcome():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c1")
    await capture_and_classify("c1", client=client, registry=reg)
    o = reg.get("c1")
    assert o.status == OutcomeStatus.DONE
    assert o.confirmation == "24HF-4471"


async def test_capture_stores_blocked_outcome():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(BLOCKED_TURNS, call_id="c2")
    await capture_and_classify("c2", client=client, registry=reg)
    assert reg.get("c2").status == OutcomeStatus.BLOCKED


def test_registry_get_unknown_is_none():
    assert CallRegistry().get("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_outbound.py -q`
Expected: FAIL — `ImportError: cannot import name 'CallRegistry'` (stub
from Plan 03 has no such symbol).

- [ ] **Step 3: Write `src/robin/outbound.py` (registry + capture; keep frozen tool signatures)**

```python
"""Outbound leg: dial the simulated receptionist, capture its SSE
transcript in one asyncio task, classify on call-end, deliver the result.

Implements the Coordination Model. Tool signatures are frozen in the 00
doc and replace the Plan 03 stub unchanged.
"""
import asyncio

from robin.classifier import classify_transcript
from robin.models import Outcome


class CallRegistry:
    """In-process map call_id -> Outcome (None until the call ends)."""

    def __init__(self) -> None:
        self._outcomes: dict[str, Outcome] = {}

    def set(self, call_id: str, outcome: Outcome) -> None:
        self._outcomes[call_id] = outcome

    def get(self, call_id: str) -> Outcome | None:
        return self._outcomes.get(call_id)


async def capture_and_classify(call_id: str, *, client,
                               registry: CallRegistry) -> Outcome:
    """Consume one SSE transcript until it ends, classify, store."""
    lines: list[str] = []
    async for turn in client.stream_transcript(call_id):
        lines.append(f"{turn.role}: {turn.content}")
    outcome = classify_transcript("\n".join(lines))
    registry.set(call_id, outcome)
    return outcome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_outbound.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/outbound.py tests/test_outbound.py
git commit -m "feat: call registry + SSE capture-and-classify task"
```

---

### Task 3: `place_negotiation_call` (frozen tool signature)

**Files:**
- Modify: `src/robin/outbound.py`
- Test: `tests/test_outbound.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_outbound.py
from robin.outbound import make_place_negotiation_call


async def test_place_negotiation_call_dials_and_spawns_capture():
    reg = CallRegistry()
    client = FakeAgentPhoneClient(DONE_TURNS, call_id="c9")
    tool = make_place_negotiation_call(
        client=client, registry=reg, agent_id="agt_robin",
        from_number_id="num_robin", receptionist_to_number="+15550000002",
        outbound_system_prompt="SYS-OUT")
    res = await tool(phone="415-776-2200", member_name="Demo User",
                     citations=[{"citation": "X", "operative_quote": "q",
                                 "source_url": "u"}])
    assert res["call_id"] == "c9"
    assert client.placed[0]["to_number"] == "+15550000002"  # dials the sim, not 415-...
    await asyncio.sleep(0.05)  # let the capture task finish the fake stream
    assert reg.get("c9").confirmation == "24HF-4471"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_outbound.py::test_place_negotiation_call_dials_and_spawns_capture -q`
Expected: FAIL — `ImportError: cannot import name 'make_place_negotiation_call'`.

- [ ] **Step 3: Append to `src/robin/outbound.py`**

```python
# append to src/robin/outbound.py
def make_place_negotiation_call(*, client, registry: CallRegistry,
                                agent_id: str, from_number_id: str,
                                receptionist_to_number: str,
                                outbound_system_prompt: str):
    """Build the frozen-signature place_negotiation_call tool callable.

    Robin SAYS the public number but DIALS the controlled simulation
    (receptionist_to_number) — never the real company.
    """

    async def place_negotiation_call(phone: str, member_name: str,
                                     citations: list[dict]) -> dict:
        call_id = await client.place_call(
            agent_id=agent_id, to_number=receptionist_to_number,
            initial_greeting=f"Hi, I'm calling on behalf of {member_name}.",
            system_prompt=outbound_system_prompt,
            from_number_id=from_number_id)
        asyncio.create_task(
            capture_and_classify(call_id, client=client, registry=registry))
        return {"call_id": call_id}

    return place_negotiation_call
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_outbound.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/outbound.py tests/test_outbound.py
git commit -m "feat: place_negotiation_call dials simulation + spawns capture"
```

---

### Task 4: `deliver_result` (callback primary, stay-on stretch)

**Files:**
- Modify: `src/robin/outbound.py`
- Test: `tests/test_outbound.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_outbound.py
from robin.outbound import make_deliver_result


async def test_deliver_result_callback_places_call():
    client = FakeAgentPhoneClient([], call_id="cb1")
    tool = make_deliver_result(
        client=client, agent_id="agt_robin", from_number_id="num_robin",
        callback_number="+15550000001")
    res = await tool(channel="callback",
                     summary="Cancelled, last-month refund.",
                     confirmation="24HF-4471")
    assert res["delivered"] is True
    assert client.placed[0]["to_number"] == "+15550000001"


async def test_deliver_result_stay_on_does_not_place_call():
    client = FakeAgentPhoneClient([], call_id="x")
    tool = make_deliver_result(
        client=client, agent_id="a", from_number_id="n",
        callback_number="+15550000001")
    res = await tool(channel="stay_on", summary="Done.",
                     confirmation="24HF-4471")
    assert res["delivered"] is True
    assert client.placed == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_outbound.py::test_deliver_result_callback_places_call -q`
Expected: FAIL — `ImportError: cannot import name 'make_deliver_result'`.

- [ ] **Step 3: Append to `src/robin/outbound.py`**

```python
# append to src/robin/outbound.py
def make_deliver_result(*, client, agent_id: str, from_number_id: str,
                         callback_number: str):
    """Build the frozen-signature deliver_result tool callable.

    channel "callback": place a fresh outbound call to the caller with
    the result. channel "stay_on": no call — the text is spoken on the
    held inbound turn by the loop (stretch path).
    """

    async def deliver_result(channel: str, summary: str,
                             confirmation: str | None) -> dict:
        spoken = summary if not confirmation else (
            f"{summary} Confirmation number {confirmation}.")
        if channel == "callback":
            await client.place_call(
                agent_id=agent_id, to_number=callback_number,
                initial_greeting="Hi, it's Robin with an update.",
                system_prompt=f"Tell the caller, then stop: {spoken}",
                from_number_id=from_number_id)
        return {"delivered": True}

    return deliver_result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_outbound.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Full suite + lint**

Run: `python3 -m pytest -q && python3 -m ruff check src tests`
Expected: all pass; coverage ≥ 80%; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/robin/outbound.py tests/test_outbound.py
git commit -m "feat: deliver_result (callback primary, stay-on stretch)"
```

---

## Self-Review

- **Spec coverage:** AgentPhone client place/stream/recording
  (agentphone-notes); Coordination Model — one asyncio task per SSE
  stream, classify on end (design "Coordination Model"); dials the
  simulation not the real number (design premise 3); callback primary,
  stay-on stretch (SPEC press-2 first); recording URL surfaced for the
  dashboard receipt. Covered.
- **Placeholder scan:** every step has full code/fixtures; no TBD.
- **Type consistency:** `place_negotiation_call`/`deliver_result` keep
  the exact frozen signatures from the 00 doc and the Plan 03 stub
  (`make_*` factories produce callables with those signatures —
  Plan 06's composition wires the factories and registers the resulting
  callables into `tool_impls`). `AgentPhoneClient` + `TranscriptTurn`
  match Plan 03's `FakeAgentPhoneClient`. `classify_transcript` and
  `Outcome` imported from Plan 01 unchanged.
