# Robin — Demo-Tonight Plan Set & Execution Sequence

> **This is the orchestration map.** It freezes the cross-plan interface
> contracts (so plans run in parallel without colliding) and states the
> wave order + per-plan execution strategy. Read this first, then the
> individual plan files in `docs/superpowers/plans/`.

**Goal:** Be ready to perform the canonical Stage Runsheet live tonight
(call Robin → discovery → Browser Use legal research → outbound call to a
simulated 24 Hour Fitness receptionist → escalating negotiation →
two-option ultimatum → capitulation + last-month refund + `24HF-4471` →
report back), with a clean recorded backup and a public repo, submitted
by **8:00 PM**.

**Source of truth:** `CLAUDE.md` "Approved demo", `SPEC.md`, the design
doc `~/.gstack/projects/robin/francescorosciano-unknown-design-20260517-112530.md`,
`DAY_PLAN.md`, `agentphone/agentphone-notes.md`, `browseruse/browseruse-notes.md`.

---

## The plan set

| # | Plan | Produces | Key-gated? | Strategy | Worker model |
|---|------|----------|-----------|----------|--------------|
| 01 | Pure Logic Core | `models.py`, `context_pack.py`, `prompts.py`, `classifier.py` + tests (≥80%) | No | **subagent-driven-development** | sonnet |
| 02 | Content & Fixtures | locked `law.html`, receptionist prompt, Robin inbound + outbound prompt templates | No | **executing-plans** (legal verify is human-judgment) | opus for legal verify task, else sonnet |
| 03 | Webhook Server + Tool Loop | FastAPI app, HMAC, NDJSON, Claude ≤6-turn loop, 3 tool schemas, `/fixture/law.html` route, Browser Use research tool | No (fakes) | **subagent-driven-development** | sonnet |
| 04 | Outbound + Capture + Callback | `agentphone_client.py`, `outbound.py` (asyncio SSE consumer → classify → callback), recording URL | No (fakes) | **subagent-driven-development** | sonnet |
| 05 | Provisioning & Tunnel | `scripts/setup_agentphone.py`, 2nd (receptionist) agent, cloudflared tunnel | **Yes** (AGENTPHONE_API_KEY) — *code* is key-free, *run* is gated | **executing-plans** (live, operator judgment) | sonnet |
| 06 | Integration, Rehearsal, Submission | wired `.env`, smoke, manual win gate, recorded backup, ×3 rehearsal, public repo + Google form | **Yes** (both keys + tunnel) | **executing-plans** (live, human-in-loop) | sonnet |

Why two strategies:
- **subagent-driven-development** — well-specified, TDD-able, decomposable
  code with frozen interfaces and crisp tests. Fresh subagent per task,
  two-stage review between tasks, fast iteration. → 01, 03, 04.
- **executing-plans** — inline batch execution with checkpoints where the
  operator must watch and exercise judgment: high-stakes legal
  verification (02), live key-gated provisioning with pre-decided
  fallbacks (05), and the operational closeout / live rehearsal /
  human-only git push + submission (06).

---

## Execution sequence (parallel-first)

```
GATE (start NOW, runs alongside everything — does NOT block Wave 1/2 code):
  G1  Obtain AGENTPHONE_API_KEY      (human — agentphone.ai / Discord https://tinyurl.com/ycagentphone)
  G2  Obtain BROWSER_USE_API_KEY     (human — cloud.browser-use.com → API keys)
  G3  Bring up cloudflared HTTPS tunnel; note PUBLIC_BASE_URL (do NOT restart it later — ~12s cooldown)
  DAY_PLAN rule: if keys not in hand by early afternoon, Waves 1–2 still
  complete against fakes; keys only gate Plan 05 *run* + Plan 06 integration.

WAVE 1  — fully parallel, zero keys, zero cross-plan deps:
  ├─ Plan 01  Pure Logic Core            (subagent-driven)
  ├─ Plan 02  Content & Fixtures         (executing-plans; Task 1 legal-verify FIRST, user sign-off gate)
  └─ Plan 05  *script authoring only*    (write setup_agentphone.py against documented API; run deferred to Wave 3)

  Wave 1 exit criteria:
    • Plan 01 INTERFACES frozen & merged (models.py committed) — unblocks Wave 2
    • Plan 02 legal citations LOCKED + user-signed-off; law.html + 3 prompt files committed

WAVE 2  — parallel, starts the moment Plan 01 interfaces are committed
          and Plan 02 prompt templates exist (still no keys needed):
  ├─ Plan 03  Webhook Server + Tool Loop (subagent-driven; imports Plan 01, serves Plan 02 law.html, loads Plan 02 prompts)
  └─ Plan 04  Outbound + Capture + Callback (subagent-driven; imports Plan 01 classifier; both 03 & 04 code against the FROZEN AgentPhone client + tool contracts below)

  03 and 04 do NOT block each other: the AgentPhone client interface and
  the 3-tool contract are frozen below. 03 owns the loop + research tool +
  thin import of 04's two tool callables; 04 owns the client + outbound +
  callback. They integrate when both land.

WAVE 3  — sequential, needs keys + Wave 1/2 code:
  1. Plan 05 RUN  (executing-plans, live): provision Robin agent + number +
     webhook to PUBLIC_BASE_URL; provision 2nd receptionist agent w/ Plan 02
     prompt; print IDs → .env. Fixture fallback if 2nd agent stalls (see 05).
  2. Plan 06      (executing-plans, live, human-in-loop): wire .env →
     startup-secret guard green → smoke (Robin speaks) → **manual
     receptionist win gate** → first end-to-end happy path → **capture
     recorded backup immediately** → rehearse runsheet ×3 vs clock →
     6 PM feature freeze → README/secrets scan → human makes repo public,
     pushes, submits Google form before 8 PM.
```

**One-line scheduling answer:** 01 ‖ 02 ‖ 05-authoring run in parallel
now; 03 ‖ 04 in parallel as soon as 01's `models.py` is committed and
02's prompt files exist; 05-run then 06 strictly sequential at the end
once the two keys + tunnel are in hand. The only true serialization is
Wave 3 (it needs live telephony + the human for push/submit).

---

## FROZEN INTERFACE CONTRACTS (the seam that makes Waves parallel — do not deviate)

Plan 01 **owns and must commit first**: `pyproject.toml` (initial),
`src/robin/__init__.py`, and `src/robin/models.py`. Plan 03 *appends* its
deps to `pyproject.toml` only after Plan 01 is merged (no concurrent edit
of `pyproject.toml`).

### `src/robin/models.py` (Plan 01 — imported by 03, 04)

```python
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ContextPack:
    caller_name: str
    callback_number: str          # E.164, synthetic +1555... in tests/demo
    target_name: str              # "24 Hour Fitness"
    target_display_number: str    # "415-776-2200" — what Robin SAYS
    receptionist_to_number: str   # E.164 Robin actually DIALS (the simulation)
    jurisdiction: str             # "US-CA"
    win_goal: str
    fallback_goal: str


@dataclass(frozen=True)
class Citation:
    citation: str                 # e.g. "FTC Negative Option Rule, 16 CFR Part 425"
    operative_quote: str          # one verbatim operative sentence
    source_url: str


class OutcomeStatus(str, Enum):
    DONE = "DONE"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Outcome:
    status: OutcomeStatus
    confirmation: str | None      # "24HF-4471" when DONE, else None
    detail: str                   # human summary / why blocked
```

### `src/robin/context_pack.py` (Plan 01)

```python
def load_context_pack(path: str) -> ContextPack: ...
class ContextPackError(ValueError): ...
```
Guard (fail fast at load): missing file/JSON error/missing key →
`ContextPackError`; any string value containing `{{` or `}}` → error
(`unfilled placeholder in <field>`); empty string → error;
`callback_number` and `receptionist_to_number` not matching
`^\+[1-9]\d{7,14}$` → error.

### `src/robin/prompts.py` (Plan 01; templates supplied by Plan 02)

```python
def render(template: str, pack: ContextPack,
           citations: list[Citation] | None = None) -> str: ...
def render_inbound_system_prompt(pack: ContextPack) -> str: ...      # reads INBOUND_TEMPLATE_PATH
def render_outbound_system_prompt(pack: ContextPack,
                                  citations: list[Citation]) -> str: ...  # reads OUTBOUND_TEMPLATE_PATH
class PromptRenderError(ValueError): ...
```
`render` substitutes `{{caller_name}}`, `{{callback_number}}`,
`{{target_name}}`, `{{target_display_number}}`, `{{jurisdiction}}`,
`{{win_goal}}`, `{{fallback_goal}}`, and `{{citations}}` (a formatted
block built from `citations`). After substitution, any residual
`{{...}}` → `PromptRenderError`. Template path constants:
`INBOUND_TEMPLATE_PATH = "src/robin/fixtures/prompts/inbound_discovery.txt"`,
`OUTBOUND_TEMPLATE_PATH = "src/robin/fixtures/prompts/outbound_negotiation.txt"`.

### `src/robin/classifier.py` (Plan 01 — consumed by Plan 04)

```python
def classify_transcript(transcript: str) -> Outcome: ...
```
- `DONE` iff `re.search(r"\b24HF-\d{4}\b", transcript)` **and**
  `"refund" in transcript.lower()` — `confirmation` = the matched
  `24HF-####`.
- else `NEEDS_APPROVAL` iff any of (case-insensitive): `one-time code`,
  `verification code`, `\botp\b`, `security question`,
  `verify your identity`, `text you a code` — `detail` = matched phrase.
- else `BLOCKED` — `detail` = last non-empty line, truncated 200 chars.
- DONE is checked first (success overrides an earlier OTP mention).

### `src/robin/agentphone_client.py` (Plan 04 owns; Plan 03 imports the type only)

```python
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass(frozen=True)
class TranscriptTurn:
    role: str        # "user" | "agent"
    content: str
    created_at: str


class AgentPhoneClient:
    def __init__(self, api_key: str,
                 base_url: str = "https://api.agentphone.ai/v1") -> None: ...
    async def place_call(self, *, agent_id: str, to_number: str,
                         initial_greeting: str, system_prompt: str,
                         from_number_id: str) -> str: ...                 # -> call_id
    async def stream_transcript(self, call_id: str
                                ) -> AsyncIterator[TranscriptTurn]: ...    # SSE 'turn' until 'ended'
    async def get_recording_url(self, call_id: str) -> str | None: ...     # GET /v1/calls/{id}.recordingUrl
```
`tests/fakes.py::FakeAgentPhoneClient` implements the same interface from
a canned SSE fixture — this is what makes Plans 03/04 key-independent.

### Claude tool contract (Plan 03 registers schemas; impls split 03/04)

- `research_cancellation_law(jurisdiction: str) -> dict`
  → `{"citations":[{"citation","operative_quote","source_url"}],
  "status":"OK"|"FAILED"}`. **Impl: Plan 03** (Browser Use →
  `PUBLIC_BASE_URL + "/fixture/law.html"`, 60s timeout, on timeout
  `status:"FAILED"`, never hang the loop).
- `place_negotiation_call(phone: str, member_name: str,
  citations: list[dict]) -> {"call_id": str}`. **Impl: Plan 04**
  (`src/robin/outbound.py::place_negotiation_call`).
- `deliver_result(channel: str, summary: str,
  confirmation: str | None) -> {"delivered": bool}`. **Impl: Plan 04**
  (`src/robin/outbound.py::deliver_result`).

Plan 03's loop imports `place_negotiation_call`, `deliver_result` from
`src/robin/outbound.py`. During Wave 2, if 03 lands before 04, 03 keeps a
local `outbound.py` stub raising `NotImplementedError` with **exactly
these signatures**; Plan 04 replaces the stub. No signature drift.

---

## Spec → plan coverage map (self-review)

| Runsheet / SPEC requirement | Plan |
|---|---|
| Inbound discovery dialogue (brainstorm→plan→confirm) | 02 (prompt) + 03 (loop/NDJSON) |
| "say one / say two" voice keyword (DTMF cut) | 02 (prompt wording) + 03 (inbound flow) |
| Browser Use pulls X/Y/Z cancellation laws | 02 (law.html + citations) + 03 (research tool) |
| Outbound call to simulated receptionist | 04 (place_negotiation_call) + 05 (the agent) |
| Simulated 24HF receptionist agent | 02 (system prompt) + 05 (provision) |
| Escalating negotiation / Robin playbook (Voss ×2 + ultimatum) | 02 (outbound prompt) |
| Outcome classifier (DONE/NEEDS_APPROVAL/BLOCKED, greps 24HF-#### + refund) | 01 |
| Result delivery — callback (press-2) primary; stay-on (press-1) stretch | 04 (deliver_result) |
| Recording visible in AgentPhone dashboard | 04 (get_recording_url) + 06 (show it) |
| Webhook HMAC verify over raw bytes, constant-time | 03 |
| Secrets only in `.env`, validated at startup | 03 (config guard) |
| Context pack guard rejects unfilled placeholders | 01 |
| Manual receptionist "win it by hand" gate | 06 (gate before trusting Robin) |
| Recorded backup run (Google-form video + safety net) | 06 |
| Rehearse live runsheet ×3 vs clock | 06 |
| Public repo + Google form, human pushes (agent denied) | 06 |
| DAY_PLAN checkpoints (no-key, DTMF, 6 PM freeze) | 06 (pre-decided gates) |

No requirement is unmapped.

---

## Risk register (pre-decided — do not relitigate live)

- **Wrong/misquoted law on stage = fatal.** Plan 02 Task 1 verifies all
  three against primary sources + a hard user-sign-off gate before
  `law.html` is locked. No live legal-site fetch on stage.
- **No API key by early afternoon** → keep building Waves 1–2 against
  fakes; escalate on Discord/on-site in parallel (G1).
- **Inbound DTMF unsupported** → already decided: ship voice keyword
  ("say one / say two"). Do not chase call-bridging.
- **2nd AgentPhone agent provisioning stalls > 30 min (≈12:30 PM
  checkpoint)** → Plan 05 fallback: a teammate phone / 6-line TTS plays
  the receptionist at `RECEPTIONIST_TO_NUMBER`. Same demo story.
- **~6 PM**: feature freeze. Whatever is end-to-end is the demo. Recorded
  backup must already exist.
- **Live multi-minute negotiation drifts** → the recorded backup is the
  submission artifact and the stage safety net regardless.
