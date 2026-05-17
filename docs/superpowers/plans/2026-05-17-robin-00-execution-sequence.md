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
| 07 | Stage Presentation & AV | live-transcript projector page (`TurnBroadcaster` + `/stage` SSE page), "AI simulation" disclosure slide, AV runbook, integrated stage rehearsal | No (projector code) / Yes (live staging) | **executing-plans** | sonnet |

Why two strategies:
- **subagent-driven-development** — well-specified, TDD-able, decomposable
  code with frozen interfaces and crisp tests. Fresh subagent per task,
  two-stage review between tasks, fast iteration. → 01, 03, 04.
- **executing-plans** — inline batch execution with checkpoints where the
  operator must watch and exercise judgment: high-stakes legal
  verification (02), live key-gated provisioning with pre-decided
  fallbacks (05), the operational closeout / live rehearsal / human-only
  git push + submission (06), and stage AV + rehearsal (07's projector
  code is key-free; its staging half is live + operator-present).

---

## Execution sequence (parallel-first)

```
GATE (start NOW, runs alongside everything — does NOT block Wave 1/2 code):
  G0  git init — Robin is not yet a git repository. Every plan's commits
      depend on it (the first commit is Plan 01 Task 1). Run:
        git rev-parse --git-dir >/dev/null 2>&1 || git init
      in the project root before Wave 1 work begins.
  G1  Obtain AGENTPHONE_API_KEY      (human — agentphone.ai / Discord https://tinyurl.com/ycagentphone)
  G2  Obtain BROWSER_USE_API_KEY     (human — cloud.browser-use.com → API keys)
  G3  Obtain ANTHROPIC_API_KEY       (human — console.anthropic.com → API keys;
      the Claude tool-call loop requires it; must appear in .env + config guard)
  G4  Bring up cloudflared HTTPS tunnel; note PUBLIC_BASE_URL (do NOT restart it later — ~12s cooldown)
  G5  Enable / verify the AgentPhone recording add-on (agentphone.ai dashboard
      or via support / Discord). Without it, `GET /v1/calls/{id}` returns no
      `recordingUrl` and the "recording visible in the dashboard" acceptance
      criterion fails.
  DAY_PLAN rule: if keys not in hand by early afternoon, Waves 1–2 still
  complete against fakes; keys only gate Plan 05 *run* + Plan 06 integration.

  ── API CONTRACT LOCK (gate for Plans 03 & 05 — do NOT skip; 15 min) ────────
  Before trusting Plans 03 and 05 implementations, verify these 5 facts
  against the live AgentPhone docs / Discord. All should be answerable from
  `agentphone/agentphone-notes.md`; if any is missing or marked "OPEN",
  ask in the AgentPhone Discord NOW (not at 4 PM):

  1. Inbound webhook body shape + exact NDJSON response schema:
     confirm `{"text":...,"interim":true}` → `{"text":...}` is correct,
     and the field names for `hangup`/`action`/`digits`.
  2. HMAC signing — exact header name, signing algorithm, and the exact bytes
     signed (raw body? normalised JSON? with/without a timestamp?).
  3. Create-2nd-agent + bind-number exact API call shapes
     (`POST /v1/agents`, `POST /v1/numbers`, `POST /v1/agents/{id}/numbers`).
  4. Outbound `POST /v1/calls` exact field names
     (`agentId`, `toNumber`, `fromNumberId`, `initialGreeting`, `systemPrompt`).
  5. Outbound transcript SSE endpoint + event names (`connected`, `turn`,
     `ended`) + the recording field on `GET /v1/calls/{id}` (`recordingUrl`).

  If reality differs from `agentphone-notes.md`, change points are isolated:
  - HMAC algorithm/header → only `src/robin/signature.py`
  - Webhook body field names → only `src/robin/app.py` parse + client mapping
  - Provisioning field names → only `scripts/setup_agentphone.py`
  ─────────────────────────────────────────────────────────────────────────────

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
  ├─ Plan 04  Outbound + Capture + Callback (subagent-driven; imports Plan 01 classifier; both 03 & 04 code against the FROZEN AgentPhone client + tool contracts below)
  └─ Plan 07  *projector code only*     (executing-plans; build TurnBroadcaster in
              src/robin/broadcast.py + /stage SSE page; depends only on Plan 04's
              frozen stream_transcript/TranscriptTurn interface + canned SSE fixture;
              runs fully parallel — no key dependency)

  03 and 04 do NOT block each other: the AgentPhone client interface and
  the 3-tool contract are frozen below. 03 owns the loop + research tool +
  thin import of 04's two tool callables; 04 owns the client + outbound +
  callback. They integrate when both land.
  Plan 07's projector code depends only on Plan 04's frozen TranscriptTurn
  type + the canned SSE fixture already in tests/fakes.py — it does NOT need
  the full outbound pipeline to be running.

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
  3. Plan 07 staging/AV/disclosure + integrated rehearsal ×3 — interleaved
     with / immediately after Plan 06. Plan 07 Task 6 (integrated stage
     rehearsal with projector, PA, disclosure slide) supersedes/extends Plan
     06's bare "rehearse ×3" task (Plan 06 Task 8). The combined rehearsal is
     the single gate before submission. Plan 07 also wires the /stage route +
     on_turn=broadcaster.publish hook into src/robin/main.py at this point.
```

**One-line scheduling answer:** 01 ‖ 02 ‖ 05-authoring run in parallel
now; 03 ‖ 04 ‖ 07-projector-code in parallel as soon as 01's `models.py`
is committed and 02's prompt files exist; 05-run → 06 → 07-staging
strictly sequential at the end once the three keys + tunnel + recording
add-on are in hand (G0–G5 gates resolved). The only true serialization is
Wave 3 (it needs live telephony + the human for push/submit).

---

## FROZEN INTERFACE CONTRACTS (the seam that makes Waves parallel — do not deviate)

Plan 01 **owns and must commit first**: `pyproject.toml` (initial),
`src/robin/__init__.py`, and `src/robin/models.py`. Plan 03 *appends* its
deps to `pyproject.toml` only after Plan 01 is merged (no concurrent edit
of `pyproject.toml`).

> **Additive note — Plan 04 `capture_and_classify` (Plan 04 Task 5):**
> Plan 04's internal `capture_and_classify` function gained an **optional
> keyword-only `on_turn=None` callback** (`Callable[[TranscriptTurn], None]
> | None = None`). This is used by Plan 07's `TurnBroadcaster.publish`
> to broadcast each turn to the `/stage` SSE page. This change is
> **additive and backward-compatible** — callers that omit `on_turn` see
> no change. It is explicitly **NOT part of the frozen Plan 00 contract**
> (callers outside Plan 07 must never depend on it).

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
| Rehearse live runsheet ×3 vs clock | 06 (bare) + 07 (Task 6 integrated, supersedes) |
| Public repo + Google form, human pushes (agent denied) | 06 |
| DAY_PLAN checkpoints (no-key, DTMF, 6 PM freeze) | 06 (pre-decided gates) |
| The room hears / sees the live negotiation | 07 (`/stage` SSE projector page) |
| On-screen "AI simulation" disclosure | 07 (disclosure slide) |
| Stage AV + the <1-min-pitch vs multi-minute-run choreography | 07 (AV runbook) |
| Fill the multi-minute dead air during the outbound call | 07 (live `/stage` projector) |

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
- **Conversation-history dropped on inbound turns** → **FIXED in Plan
  03**: `recentHistory` from the webhook body is now folded into the
  `messages` list before the Claude loop runs, so Robin keeps discovery
  context across turns. No longer an open risk.
- **A long tool (Browser Use research) exceeds the webhook timeout and
  AgentPhone drops the turn** → **MITIGATED**: Plan 05 registers the
  webhook with `timeout=120` (the documented 5–120s max) and Plan 03
  streams keepalive interim NDJSON lines *before* dispatching the tool
  batch, so the turn stays open while the tool runs.
- **Browser Use fails / hangs / rate-limited on stage** → **MITIGATED**:
  Plan 03 ships a deterministic local `law.html` fallback (the research
  tool falls back to the pre-vetted hosted fixture). **Integrity rule:
  the mandatory recorded backup (Plan 06 Task 7) MUST be captured on the
  REAL Browser Use path — the local fallback is a live-stage safety net
  only, never the artifact.** Same bright line as the design doc's
  live-vs-recorded rule.
- **Multi-minute stage dead-air during the outbound call (audience
  watches nothing while Robin negotiates)** → **RESOLVED by Plan 07's
  live `/stage` projector**: the negotiation transcript streams turn-by-
  turn onto the projected page so the room sees the call in real time.
- **Missing ANTHROPIC_API_KEY / recording add-on not enabled** → both
  are now explicit GATE items (G3 = `ANTHROPIC_API_KEY` for the Claude
  loop; G5 = AgentPhone recording add-on, else the "recording in the
  dashboard" acceptance criterion fails). Resolve in the GATE, not at
  4 PM.
- **~6 PM**: feature freeze. Whatever is end-to-end is the demo. Recorded
  backup must already exist.
- **Live multi-minute negotiation drifts** → the recorded backup is the
  submission artifact and the stage safety net regardless.
