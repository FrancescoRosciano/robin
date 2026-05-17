# Robin Plan 03 — Webhook Server + Tool-Call Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax. TDD against
> injected fakes — **no API keys, no live telephony in this plan**.

**Goal:** A FastAPI webhook server that verifies the AgentPhone HMAC over
raw bytes, runs a Claude tool-call loop (≤6 turns, 3 tools) with NDJSON
interim→final streaming, serves the pre-vetted `/fixture/law.html`, and
fails fast at startup if any secret is missing — all unit/integration
tested with fakes.

**Architecture:** Dependency-injected. The loop takes an `llm` client, a
`browser` client, and an `outbound` module by interface, so every test
uses a fake (`tests/fakes.py`). Real adapters are wired only in
`app.py`'s composition root. Imports Plan 01 (`context_pack`, `prompts`).
Serves Plan 02 `law.html`. Imports Plan 04's two tool callables by the
frozen signature (local stub until Plan 04 lands).

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, `anthropic`,
`browser-use-sdk`, pytest, pytest-asyncio.

**Ownership note:** This plan **appends** runtime deps to the
`pyproject.toml` that Plan 01 created — only after Plan 01 is merged.
Never edit `pyproject.toml` concurrently with Plan 01.

---

## File Structure

- Modify `pyproject.toml` — add runtime + async-test deps.
- Create `src/robin/config.py` — env load + fail-fast secret guard.
- Create `src/robin/signature.py` — `verify_hmac` (constant-time, raw bytes).
- Create `src/robin/ndjson.py` — interim/final line serializer.
- Create `src/robin/tools.py` — Anthropic tool schemas + `research_cancellation_law` impl (Browser Use) + dispatcher.
- Create `src/robin/outbound.py` — **stub** (Plan 04 replaces): `place_negotiation_call`, `deliver_result` with the frozen signatures.
- Create `src/robin/loop.py` — Claude tool-call loop (≤6 turns), interim ack → tools → final.
- Create `src/robin/app.py` — FastAPI: `POST /webhook`, `GET /fixture/law.html`, `GET /healthz`.
- Create `tests/fakes.py` — `FakeLLM`, `FakeBrowser`, `FakeAgentPhoneClient`.
- Create `tests/test_config.py`, `tests/test_signature.py`, `tests/test_ndjson.py`, `tests/test_tools.py`, `tests/test_loop.py`, `tests/test_app.py`.

---

### Task 0: API contract lock (Wave-1 GATE — do not skip)

**This is a hard gate.** It BLOCKS every later task in this plan
(Tasks 1–8, and most critically Tasks 3, 6, 7, 8) until it is complete.
Do not write `signature.py`, `tools.py`, `loop.py`, or `app.py` until
the 5 facts below are confirmed against the **live** AgentPhone source.

**Why:** Plan 03 ships sensible *defaults* — HMAC = SHA-256 over the raw
body with header `X-AgentPhone-Signature` (Task 3); webhook body
`data.transcript` + `recentHistory:[{"direction","content"}]` (Task 8);
SSE events `connected`/`turn`/`ended` (Plan 04 contract). But
`agentphone/agentphone-notes.md` explicitly marks **HMAC signature
verification** and **inbound caller DTMF** as `OPEN — confirm before
relying on it`. Building the live demo on an unverified wire contract is
the single highest-likelihood silent failure: every webhook rejected as
a bad signature, or the transcript parsed from the wrong field — both
look like "Robin is mute on stage".

**Files:**
- Read/confirm only (no `src/`/`tests/` code in this task):
  `agentphone/agentphone-notes.md` and the live sources it cites.

- [ ] **Step 1: Complete the 5-fact API extraction (the Plan 00 GATE)**

This is the SAME extraction tracked in the GATE block of
`docs/superpowers/plans/2026-05-17-robin-00-execution-sequence.md`.
Verify each fact against the live AgentPhone docs / Discord
(`https://tinyurl.com/ycagentphone`) and the Moss `moss_agentphone.py`
reference — NOT against this plan's defaults:

  1. **HMAC scheme** — exact algorithm (SHA-256?), exact request header
     name (`X-AgentPhone-Signature`?), any value prefix (`sha256=`?),
     and exactly which bytes are signed (raw body only? body +
     timestamp?). Sources: Moss `moss_agentphone.py` signature-verify
     code + `https://docs.agentphone.ai/welcome/llms-full.txt`.
  2. **Inbound webhook body shape** — confirm spoken text is at
     `data.transcript` and history is
     `recentHistory:[{"direction":"inbound|outbound","content":"..."}]`
     (exact field names and `direction` literal values).
  3. **Inbound caller DTMF** — whether a caller's own `1`/`2` keypress
     reaches the webhook at all, and under what field. If not: the
     voice-keyword fallback ("say one / say two", Plan 02 wording)
     stands — no code change, just record the confirmed decision.
  4. **SSE transcript event names** — confirm `connected` → `turn`
     (`role`:"user"|"agent", `content`, `createdAt`) → `ended`
     (consumed by Plan 04; locked here so 03/04 cannot drift).
  5. **Outbound + recording shapes** — `POST /v1/calls`
     (`agentId`/`toNumber`/`initialGreeting`/`systemPrompt`/`fromNumberId`)
     and `GET /v1/calls/{id}` → `recordingUrl` (locked for Plan 04).

- [ ] **Step 2: Record findings + the SINGLE change-points**

Resolve the `OPEN` section of `agentphone/agentphone-notes.md` with the
confirmed facts and a source link for each. This task is a **gate +
pointer, not a reimplementation** — if reality differs from the
defaults, the change is surgical and localized to exactly one place:

  - **HMAC scheme differs** → change *only* `src/robin/signature.py`
    (the algorithm constant + the header-prefix strip in `verify_hmac`).
    No other file touches the signing math.
  - **Webhook body shape differs** → change *only* the two parse lines
    in `src/robin/app.py` (`transcript = ...`, `history = ...`) and the
    matching field mapping in the AgentPhone client (Plan 04). The loop
    contract `run_turn(transcript, history, ...)` is unaffected.
  - **Inbound DTMF unsupported** → no code change; the voice-keyword
    flow already stands. Just record the decision.

- [ ] **Step 3: Gate check — confirm before proceeding**

Do NOT start Task 1 (and therefore Tasks 3/6/7/8) until all 5 facts are
recorded in `agentphone/agentphone-notes.md` with a source link each,
and the notes state explicitly whether each default held or changed.
Only then is the gate released and Tasks 1–8 may proceed.

(No commit for this task — it edits `agentphone/agentphone-notes.md`,
which is outside Plan 03's `src/`/`tests/` ownership surface. Record the
findings there, release the gate, and continue.)

---

### Task 1: Add runtime dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Replace the `dependencies = []` line**

In `pyproject.toml`, set:

```toml
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "httpx>=0.27",
  "anthropic>=0.39",
  "browser-use-sdk>=0.1",
]
```

- [ ] **Step 2: Add async test deps under a new section after `[tool.ruff]`**

```toml
[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "pytest-asyncio>=0.23", "ruff"]

[tool.pytest.ini_options.asyncio_mode]
```

Then ensure `[tool.pytest.ini_options]` has `asyncio_mode = "auto"` —
final `[tool.pytest.ini_options]` block:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-q --cov=robin --cov-report=term-missing"
```

(Remove the stray `[tool.pytest.ini_options.asyncio_mode]` line if it was
added — the canonical form is the single block above.)

- [ ] **Step 3: Install and verify**

Run: `cd /Users/francescorosciano/docs/robin && python3 -m pip install -q -e ".[dev]" && python3 -m pytest -q`
Expected: existing Plan 01 tests still pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add FastAPI/anthropic/browser-use runtime deps"
```

---

### Task 2: Fail-fast secret/config guard

**Files:**
- Create: `src/robin/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from robin import config

REQUIRED = [
    "ANTHROPIC_API_KEY", "AGENTPHONE_API_KEY", "AGENTPHONE_WEBHOOK_SECRET",
    "BROWSER_USE_API_KEY", "ROBIN_AGENT_ID", "FROM_NUMBER_ID",
    "RECEPTIONIST_TO_NUMBER", "PUBLIC_BASE_URL",
]


def _set_all(monkeypatch):
    for k in REQUIRED:
        monkeypatch.setenv(k, "x" if k != "RECEPTIONIST_TO_NUMBER" else "+15550000002")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")


def test_load_returns_settings_when_all_present(monkeypatch):
    _set_all(monkeypatch)
    s = config.load_settings()
    assert s.public_base_url == "https://example.test"
    assert s.receptionist_to_number == "+15550000002"


def test_missing_var_raises_naming_it(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("BROWSER_USE_API_KEY")
    with pytest.raises(config.ConfigError, match="BROWSER_USE_API_KEY"):
        config.load_settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.config'`.

- [ ] **Step 3: Write `src/robin/config.py`**

```python
"""Fail-fast configuration. Validate every required secret at startup."""
import os
from dataclasses import dataclass

_REQUIRED = (
    "ANTHROPIC_API_KEY", "AGENTPHONE_API_KEY", "AGENTPHONE_WEBHOOK_SECRET",
    "BROWSER_USE_API_KEY", "ROBIN_AGENT_ID", "FROM_NUMBER_ID",
    "RECEPTIONIST_TO_NUMBER", "PUBLIC_BASE_URL",
)


class ConfigError(RuntimeError):
    """Raised at startup when a required environment variable is missing."""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    agentphone_api_key: str
    agentphone_webhook_secret: str
    browser_use_api_key: str
    robin_agent_id: str
    from_number_id: str
    receptionist_to_number: str
    public_base_url: str


def load_settings() -> Settings:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            "missing required environment variable(s): " + ", ".join(missing)
        )
    g = os.environ.__getitem__
    return Settings(
        anthropic_api_key=g("ANTHROPIC_API_KEY"),
        agentphone_api_key=g("AGENTPHONE_API_KEY"),
        agentphone_webhook_secret=g("AGENTPHONE_WEBHOOK_SECRET"),
        browser_use_api_key=g("BROWSER_USE_API_KEY"),
        robin_agent_id=g("ROBIN_AGENT_ID"),
        from_number_id=g("FROM_NUMBER_ID"),
        receptionist_to_number=g("RECEPTIONIST_TO_NUMBER"),
        public_base_url=g("PUBLIC_BASE_URL").rstrip("/"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/config.py tests/test_config.py
git commit -m "feat: fail-fast startup secret guard"
```

---

### Task 3: HMAC signature verification

**Files:**
- Create: `src/robin/signature.py`
- Test: `tests/test_signature.py`

> Algorithm/header default to SHA-256 over the raw body (Moss approach).
> If `agentphone/agentphone-notes.md` later confirms a different scheme,
> only `_ALGO`/prefix handling changes — keep this the single chokepoint.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signature.py
import hashlib
import hmac
import pytest
from robin.signature import verify_hmac, SignatureError

SECRET = b"shh"
BODY = b'{"event":"agent.message"}'
GOOD = hmac.new(SECRET, BODY, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    assert verify_hmac(BODY, GOOD, SECRET) is True


def test_valid_signature_with_prefix_passes():
    assert verify_hmac(BODY, "sha256=" + GOOD, SECRET) is True


def test_tampered_body_fails():
    with pytest.raises(SignatureError):
        verify_hmac(BODY + b"x", GOOD, SECRET)


def test_missing_signature_fails():
    with pytest.raises(SignatureError):
        verify_hmac(BODY, "", SECRET)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_signature.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.signature'`.

- [ ] **Step 3: Write `src/robin/signature.py`**

```python
"""Constant-time HMAC verification over the raw request bytes."""
import hashlib
import hmac


class SignatureError(Exception):
    """Raised when the webhook signature is absent or does not match."""


def verify_hmac(raw_body: bytes, signature_header: str, secret: bytes) -> bool:
    if not signature_header:
        raise SignatureError("missing signature header")
    provided = signature_header.split("=", 1)[1] if signature_header.startswith(
        "sha256="
    ) else signature_header
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise SignatureError("signature mismatch")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_signature.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/signature.py tests/test_signature.py
git commit -m "feat: constant-time HMAC webhook verification"
```

---

### Task 4: NDJSON serializer

**Files:**
- Create: `src/robin/ndjson.py`
- Test: `tests/test_ndjson.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ndjson.py
import json
from robin.ndjson import interim, final


def test_interim_line():
    line = interim("Let me check that.")
    assert line.endswith("\n")
    assert json.loads(line) == {"text": "Let me check that.", "interim": True}


def test_final_line_plain():
    assert json.loads(final("Done."))["text"] == "Done."
    assert "interim" not in json.loads(final("Done."))


def test_final_with_hangup():
    obj = json.loads(final("Bye.", hangup=True))
    assert obj == {"text": "Bye.", "hangup": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ndjson.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.ndjson'`.

- [ ] **Step 3: Write `src/robin/ndjson.py`**

```python
"""AgentPhone NDJSON line helpers (interim keeps the turn open)."""
import json


def interim(text: str) -> str:
    return json.dumps({"text": text, "interim": True}) + "\n"


def final(text: str, *, hangup: bool = False) -> str:
    obj: dict = {"text": text}
    if hangup:
        obj["hangup"] = True
    return json.dumps(obj) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ndjson.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/ndjson.py tests/test_ndjson.py
git commit -m "feat: NDJSON interim/final serializer"
```

---

### Task 5: Outbound stub (frozen signatures — Plan 04 replaces)

**Files:**
- Create: `src/robin/outbound.py`

- [ ] **Step 1: Write the stub with the EXACT frozen signatures**

```python
"""Outbound tool callables. STUB — Plan 04 replaces with the real impl.

Signatures are frozen in
docs/superpowers/plans/2026-05-17-robin-00-execution-sequence.md and must
not change; Plan 03 depends only on these shapes.
"""


async def place_negotiation_call(
    phone: str, member_name: str, citations: list[dict]
) -> dict:
    raise NotImplementedError("Plan 04 provides place_negotiation_call")


async def deliver_result(
    channel: str, summary: str, confirmation: str | None
) -> dict:
    raise NotImplementedError("Plan 04 provides deliver_result")
```

- [ ] **Step 2: Commit**

```bash
git add src/robin/outbound.py
git commit -m "chore: outbound tool stub with frozen signatures"
```

---

### Task 6: Tool schemas + Browser Use research impl + dispatcher

**Files:**
- Create: `src/robin/tools.py`
- Create: `tests/fakes.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the fakes**

```python
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
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_tools.py
import pytest
from robin.tools import TOOL_SCHEMAS, research_cancellation_law
from tests.fakes import FakeBrowser

LAW_OUTPUT = (
    'citation: FTC Negative Option Rule | quote: Cancellation must be at '
    'least as simple as enrollment. | source: https://h/law.html\n'
    'citation: Cal. Civ. Code 1812.x | quote: The buyer may cancel. | '
    'source: https://h/law.html'
)


def test_tool_schemas_are_the_three_named_tools():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {
        "research_cancellation_law", "place_negotiation_call", "deliver_result"
    }


async def test_research_parses_browser_output_ok():
    fb = FakeBrowser(LAW_OUTPUT)
    res = await research_cancellation_law(
        "US-CA", browser=fb, law_url="https://h/law.html"
    )
    assert res["status"] == "OK"
    assert res["citations"][0]["citation"].startswith("FTC")
    assert "law.html" in fb.calls[0]


async def test_research_timeout_returns_failed_not_raise():
    fb = FakeBrowser("", raise_exc=TimeoutError("slow"))
    res = await research_cancellation_law(
        "US-CA", browser=fb, law_url="https://h/law.html"
    )
    assert res["status"] == "FAILED"
    assert res["citations"] == []


async def test_research_falls_back_to_local_fixture(tmp_path):
    law = tmp_path / "law.html"
    law.write_text('<h2 class="citation">FTC X</h2>'
                   '<p class="operative-quote">Be simple.</p>'
                   '<p class="source">http://h</p>')
    fb = FakeBrowser("", raise_exc=RuntimeError("BU down"))
    res = await research_cancellation_law(
        "US-CA", browser=fb, law_url="http://h/law.html",
        law_html_path=str(law))
    assert res["status"] == "OK"
    assert res["citations"][0]["citation"] == "FTC X"
    assert res.get("source") == "local-fixture-fallback"
```

> **INTEGRITY note (read before implementing the fallback).** The
> mandatory recorded backup run (Plan 06, Task 7) MUST be captured on the
> **real Browser Use path** — the local fixture is a *live-stage safety
> net only*, never the path that produces the submission video. This is
> the same live-vs-recorded integrity bright line as the design doc:
> the pipeline genuinely runs for the recording; the fallback exists
> solely so a flaky network on stage cannot leave Robin with zero
> citations mid-negotiation. The fallback parses the **identical
> pre-vetted text** from the self-hosted `src/robin/fixtures/law.html`,
> so the cited statutes are unchanged whichever path serves them.
> Cross-reference (do NOT implement here): the composition root in
> `src/robin/main.py` (Plan 06) must pass
> `law_html_path="src/robin/fixtures/law.html"` when wiring the real
> `research_cancellation_law`.

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tools.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.tools'`.

- [ ] **Step 4: Write `src/robin/tools.py`**

```python
"""Anthropic tool schemas + the Browser Use research tool + dispatcher."""
import asyncio
import os
import re

RESEARCH_TIMEOUT_S = 60

TOOL_SCHEMAS = [
    {
        "name": "research_cancellation_law",
        "description": "Fetch the pre-vetted cancellation-law page and "
                       "extract the governing citations for a jurisdiction.",
        "input_schema": {
            "type": "object",
            "properties": {"jurisdiction": {"type": "string"}},
            "required": ["jurisdiction"],
        },
    },
    {
        "name": "place_negotiation_call",
        "description": "Call the gym to cancel, using the cited laws.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "member_name": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["phone", "member_name", "citations"],
        },
    },
    {
        "name": "deliver_result",
        "description": "Deliver the outcome to the caller (callback or stay-on).",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": ["callback", "stay_on"]},
                "summary": {"type": "string"},
                "confirmation": {"type": ["string", "null"]},
            },
            "required": ["channel", "summary"],
        },
    },
]


def _parse_law(output: str) -> list[dict]:
    cites: list[dict] = []
    for line in output.splitlines():
        if "citation:" not in line:
            continue
        parts = {}
        for seg in line.split("|"):
            if ":" in seg:
                k, _, v = seg.partition(":")
                parts[k.strip().lower()] = v.strip()
        if parts.get("citation") and parts.get("quote"):
            cites.append({
                "citation": parts["citation"],
                "operative_quote": parts["quote"],
                "source_url": parts.get("source", ""),
            })
    return cites


def _parse_law_html(html: str) -> list[dict]:
    cites = re.findall(r'class="citation"[^>]*>(.*?)<', html, re.S)
    quotes = re.findall(r'class="operative-quote"[^>]*>(.*?)<', html, re.S)
    srcs = re.findall(r'class="source"[^>]*>(.*?)<', html, re.S)
    out = []
    for i, c in enumerate(cites):
        out.append({"citation": c.strip(),
                    "operative_quote": quotes[i].strip() if i < len(quotes) else "",
                    "source_url": srcs[i].strip() if i < len(srcs) else ""})
    return out


async def research_cancellation_law(jurisdiction: str, *, browser,
                                    law_url: str,
                                    law_html_path: str | None = None) -> dict:
    task = (
        f"Go to {law_url}. It lists cancellation-law citations for "
        f"jurisdiction {jurisdiction}. For each citation block return one "
        f"line: 'citation: <h2 text> | quote: <operative sentence> | "
        f"source: <source url>'. Return only those lines."
    )
    try:
        result = await asyncio.wait_for(browser.run(task),
                                        timeout=RESEARCH_TIMEOUT_S)
    except (asyncio.TimeoutError, TimeoutError, Exception) as exc:  # noqa: BLE001
        # Browser Use failed/timed out. Deterministic safety net: parse the
        # SELF-HOSTED, pre-vetted fixture (identical statute text → integrity
        # preserved). Live-stage net only — never the recorded-backup path.
        if law_html_path and os.path.exists(law_html_path):
            with open(law_html_path, encoding="utf-8") as fh:
                cites = _parse_law_html(fh.read())
            if cites:
                return {"citations": cites, "status": "OK",
                        "source": "local-fixture-fallback"}
        return {"citations": [], "status": "FAILED", "error": str(exc)[:200]}
    cites = _parse_law(getattr(result, "output", "") or "")
    return {"citations": cites, "status": "OK" if cites else "FAILED"}
```

> The new fixture-fallback branch is only reachable on a Browser Use
> exception/timeout. The OK path is unchanged: a successful real run
> still returns `status:"OK"` with **no** `source` key, so the recorded
> backup is unambiguously distinguishable from a fallback run.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_tools.py -q`
Expected: PASS (4 passed) — including
`test_research_falls_back_to_local_fixture`.

- [ ] **Step 6: Commit**

```bash
git add src/robin/tools.py tests/fakes.py tests/test_tools.py
git commit -m "feat: tool schemas + Browser Use research (timeout-safe + local fallback)"
```

---

### Task 7: Claude tool-call loop (≤6 turns)

**Files:**
- Create: `src/robin/loop.py`
- Test: `tests/test_loop.py`

> **Two demo-critical behaviors live in this loop:**
> 1. **Conversation memory.** `run_turn` must build `messages` from
>    AgentPhone's `recentHistory` (`inbound`→user, `outbound`→assistant)
>    *before* the current transcript, or the multi-turn discovery
>    dialogue (literally half the Stage Runsheet) has no memory.
> 2. **Keepalive vs webhook timeout.** AgentPhone keeps the turn open as
>    long as interim NDJSON lines keep flowing; the default turn timeout
>    is 30s but the Browser Use research tool can take ~60s. The loop
>    therefore emits a keepalive interim immediately before each
>    tool-execution batch (in addition to the initial ack). Plan 05 also
>    raises the registered webhook `timeout` to 120s (the per-webhook
>    `timeout` field, 5–120s — see `agentphone/agentphone-notes.md`);
>    that is a Plan 05 provisioning change, cross-referenced here, **not
>    implemented in this plan**.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop.py
from robin.loop import run_turn
from robin.models import ContextPack
from tests.fakes import FakeLLM

PACK = ContextPack(
    caller_name="Demo User", callback_number="+15550000001",
    target_name="24 Hour Fitness", target_display_number="415-776-2200",
    receptionist_to_number="+15550000002", jurisdiction="US-CA",
    win_goal="cancel + refund", fallback_goal="cancel",
)


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
    # 6 tool turns max, then a forced final chunk
    assert out[-1].get("interim") is not True
    assert len(llm.calls) <= 6


async def test_history_is_included_in_messages():
    captured = {}

    class _LLM:
        async def create(self, *, system, messages, tools):
            captured["messages"] = messages

            class _M:
                content = [{"type": "text", "text": "24 Hour Fitness, got it."}]
                stop_reason = "end_turn"
            return _M()

    hist = [{"direction": "inbound", "content": "cancel my gym"},
            {"direction": "outbound", "content": "Which gym?"}]
    out = [c async for c in run_turn("24 Hour Fitness", hist, system="S",
                                     llm=_LLM(), tool_impls={})]
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert captured["messages"][-1]["content"] == "24 Hour Fitness"


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
    # initial ack + the pre-tool keepalive = at least TWO interims
    # before the final non-interim chunk.
    assert len(interims) >= 2
    assert out[-1].get("interim") is not True
    assert out[-1]["text"] == "Done."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_loop.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.loop'`.

- [ ] **Step 3: Write `src/robin/loop.py`**

```python
"""Claude tool-call loop. interim ack -> (<=6 tool turns) -> final text."""
from typing import AsyncIterator, Callable

from robin.tools import TOOL_SCHEMAS

MAX_TOOL_TURNS = 6
_INTERIM_ACK = "Let me handle that for you."
_KEEPALIVE = "Still working on that — almost there."
_FORCED_FINAL = "Give me one moment — I'm still working on this."


def _content_text(content) -> str:
    parts = [b["text"] for b in content
             if isinstance(b, dict) and b.get("type") == "text"]
    return " ".join(p.strip() for p in parts if p).strip()


def _tool_uses(content):
    return [b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"]


async def run_turn(transcript: str, history: list, *, system: str, llm,
                   tool_impls: dict[str, Callable]) -> AsyncIterator[dict]:
    """Yield NDJSON-ready dicts: one interim ack, then the final text."""
    yield {"text": _INTERIM_ACK, "interim": True}

    # Build prior-turn memory from AgentPhone's recentHistory so multi-turn
    # discovery ("which gym?" -> "24 Hour Fitness" -> "call it?" -> "yes")
    # actually remembers. inbound = caller (user); outbound = Robin (asst).
    messages = []
    for h in history:
        role = "user" if h.get("direction") == "inbound" else "assistant"
        content = h.get("content", "")
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": transcript})

    for _ in range(MAX_TOOL_TURNS):
        msg = await llm.create(system=system, messages=messages,
                               tools=TOOL_SCHEMAS)
        tool_uses = _tool_uses(msg.content)
        if not tool_uses or getattr(msg, "stop_reason", "") != "tool_use":
            yield {"text": _content_text(msg.content) or _FORCED_FINAL}
            return
        messages.append({"role": "assistant", "content": msg.content})
        # Keepalive: a tool (Browser Use research) may take up to ~60s.
        # Emitting an interim line right before the tool batch keeps the
        # AgentPhone webhook turn open (interim NDJSON resets the timer);
        # without it the default 30s turn times out with silence on stage.
        yield {"text": _KEEPALIVE, "interim": True}
        results = []
        for tu in tool_uses:
            impl = tool_impls.get(tu["name"])
            out = (await impl(**tu["input"])) if impl else {
                "error": f"unknown tool {tu['name']}"}
            results.append({"type": "tool_result", "tool_use_id": tu["id"],
                            "content": str(out)})
        messages.append({"role": "user", "content": results})

    yield {"text": _FORCED_FINAL}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_loop.py -q`
Expected: PASS (5 passed) — including
`test_history_is_included_in_messages` and
`test_keepalive_interim_emitted_before_tool_batch`.

- [ ] **Step 5: Commit**

```bash
git add src/robin/loop.py tests/test_loop.py
git commit -m "feat: Claude tool-call loop (history memory + keepalive, 6-cap)"
```

---

### Task 8: FastAPI app (webhook + law fixture + health)

**Files:**
- Create: `src/robin/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app.py
import hashlib
import hmac
import json
import httpx
import pytest
from robin.app import build_app


def _signed(body: bytes, secret: bytes) -> str:
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


@pytest.fixture
def app(monkeypatch, tmp_path):
    law = tmp_path / "law.html"
    law.write_text("<html><body><h2 class='citation'>X</h2></body></html>")

    class _Msg:
        content = [{"type": "text", "text": "Hi, this is Robin."}]
        stop_reason = "end_turn"

    class _LLM:
        async def create(self, **kw):
            return _Msg()

    return build_app(secret=b"shh", law_html_path=str(law), llm=_LLM(),
                     tool_impls={})


async def test_healthz(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://t") as c:
        r = await c.get("/healthz")
    assert r.status_code == 200


async def test_law_fixture_served(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://t") as c:
        r = await c.get("/fixture/law.html")
    assert r.status_code == 200
    assert "citation" in r.text


async def test_webhook_rejects_bad_signature(app):
    transport = httpx.ASGITransport(app=app)
    body = json.dumps({"event": "agent.message", "channel": "voice",
                        "data": {"transcript": "hi"}}).encode()
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://t") as c:
        r = await c.post("/webhook", content=body,
                         headers={"X-AgentPhone-Signature": "bad"})
    assert r.status_code == 401


async def test_webhook_streams_ndjson_on_valid_signature(app):
    transport = httpx.ASGITransport(app=app)
    body = json.dumps({"event": "agent.message", "channel": "voice",
                        "data": {"transcript": "hi"}}).encode()
    sig = _signed(body, b"shh")
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://t") as c:
        r = await c.post("/webhook", content=body,
                         headers={"X-AgentPhone-Signature": sig})
    assert r.status_code == 200
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines[0]["interim"] is True
    assert lines[-1]["text"] == "Hi, this is Robin."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_app.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.app'`.

- [ ] **Step 3: Write `src/robin/app.py`**

```python
"""FastAPI composition root: webhook + law fixture + health."""
import json

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from robin.loop import run_turn
from robin.signature import SignatureError, verify_hmac


def build_app(*, secret: bytes, law_html_path: str, llm,
              tool_impls: dict, system_prompt: str = "You are Robin.") -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/fixture/law.html")
    async def law():
        return FileResponse(law_html_path, media_type="text/html")

    @app.post("/webhook")
    async def webhook(request: Request,
                      x_agentphone_signature: str = Header("")):
        raw = await request.body()
        try:
            verify_hmac(raw, x_agentphone_signature, secret)
        except SignatureError:
            return JSONResponse({"detail": "invalid signature"},
                                status_code=401)
        payload = json.loads(raw)
        transcript = payload.get("data", {}).get("transcript", "")
        history = payload.get("recentHistory", [])

        async def stream():
            async for chunk in run_turn(transcript, history,
                                        system=system_prompt, llm=llm,
                                        tool_impls=tool_impls):
                yield json.dumps(chunk) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_app.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite + lint**

Run: `python3 -m pytest -q && python3 -m ruff check src tests`
Expected: all pass; coverage ≥ 80%; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/robin/app.py tests/test_app.py
git commit -m "feat: FastAPI webhook (HMAC->loop->NDJSON) + law fixture"
```

---

## Self-Review

- **Spec coverage:** Task 0 **API-contract gate** locks the 5 wire facts
  (HMAC scheme/header, webhook body shape, inbound DTMF, SSE events,
  outbound/recording) against the live AgentPhone source before any
  later task — it hard-blocks Tasks 1–8 and resolves the `OPEN` items in
  `agentphone/agentphone-notes.md`. HMAC over raw bytes before parse
  (security rule + SPEC); NDJSON interim→final (agentphone-notes);
  Claude loop ≤6 tools (design "Tool Schemas"); 3 tool schemas;
  `/fixture/law.html` served (design); fail-fast secret guard. **Loop
  memory:** `run_turn` now builds `messages` from `recentHistory`
  (`inbound`→user / `outbound`→assistant) before the transcript, so
  multi-turn discovery (half the Stage Runsheet) remembers — covered by
  `test_history_is_included_in_messages`. **Keepalive:** a keepalive
  interim is emitted before each tool-execution batch (initial ack +
  pre-tool keepalive ⇒ ≥2 interims) so the ~60s Browser Use research
  cannot time out the 30s webhook turn; Plan 05 raises the webhook
  `timeout` to 120s (cross-ref, not implemented here) — covered by
  `test_keepalive_interim_emitted_before_tool_batch`. **BU resilience:**
  `research_cancellation_law` falls back to the self-hosted pre-vetted
  `law.html` on any Browser Use error (identical statute text →
  integrity preserved; recorded backup must use the real path) —
  covered by `test_research_falls_back_to_local_fixture`. Covered.
- **Placeholder scan:** every step has full code; the only stub is
  `outbound.py`, intentionally and explicitly handed to Plan 04 with the
  frozen signature. Task 0 is a gate/pointer (no `src/` code) by design.
- **Type consistency:** `run_turn(transcript, history, *, system, llm,
  tool_impls)` matches `app.build_app`'s call site; the keepalive/history
  changes add no new params. `research_cancellation_law(jurisdiction:
  str, *, browser, law_url: str, law_html_path: str | None = None)` —
  the added `law_html_path` is keyword-only and defaulted, so existing
  callers (and the frozen 00 tool contract
  `research_cancellation_law(jurisdiction) -> dict`) are unaffected; the
  Plan 06 composition root passes
  `law_html_path="src/robin/fixtures/law.html"` (cross-ref). Tool names
  in `TOOL_SCHEMAS` match the dispatcher and the 00 contract;
  `FakeAgentPhoneClient` mirrors Plan 04's `AgentPhoneClient` +
  `TranscriptTurn`. `models.py`, `AgentPhoneClient`, `TranscriptTurn`,
  and the three tool names are unchanged. The real Anthropic adapter is
  wired in Plan 06 — `llm.create(system, messages, tools)` is the seam.
