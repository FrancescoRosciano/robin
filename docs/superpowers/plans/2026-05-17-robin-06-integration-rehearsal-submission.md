# Robin Plan 06 — Integration, Rehearsal & Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans. **Operational + live + human-in-loop** —
> not TDD. Execute inline with checkpoints. Several steps are
> **human-only** (live phone calls; `git push`; the Google form — the
> agent is denied push by project settings). The agent prepares; the
> human performs the gated steps.

**Goal:** Wire the real adapters into one composed app, prove the full
pipeline end-to-end once, **capture the mandatory recorded backup**,
rehearse the live Stage Runsheet ×3 against a clock, freeze, and submit
(public repo + Google form) before **8:00 PM**.

**Architecture:** A composition root `src/robin/main.py` builds the real
`AgentPhoneClient`, a real Anthropic LLM adapter, a real Browser Use
client, the Plan 04 tool factories, and the Plan 01 prompts/pack — and
hands them to Plan 03's `build_app`. Everything below is exercised live.

**Tech Stack:** the assembled Robin app; cloudflared tunnel; a phone; a
screen recorder.

**Depends on:** Plans 01–04 merged, Plan 05 run (agents/number/webhook
live, `.env` populated).

---

## File Structure

- Create `src/robin/anthropic_adapter.py` — wraps the Anthropic SDK to the `llm.create(system, messages, tools)` seam Plan 03 expects.
- Create `src/robin/main.py` — composition root; exposes `app` for `uvicorn robin.main:app`.
- Create `tests/test_anthropic_adapter.py` — adapter shape test (no network).
- Create `docs/RUNSHEET.md` — the on-stage card (timed) + the "AI simulation" disclosure line.
- Modify `README.md` — accurate run steps + the integrity statement.

---

### Task 1: Anthropic adapter (the deferred integration seam)

**Files:**
- Create: `src/robin/anthropic_adapter.py`
- Test: `tests/test_anthropic_adapter.py`

- [ ] **Step 1: Write the failing test (shape only — no network)**

```python
# tests/test_anthropic_adapter.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_anthropic_adapter.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.anthropic_adapter'`.

- [ ] **Step 3: Write `src/robin/anthropic_adapter.py`**

```python
"""Adapt the Anthropic SDK to the loop's llm.create(system, messages,
tools) seam. Content blocks are normalized to plain dicts so loop.py
stays SDK-agnostic (and fakeable)."""
import anthropic

_MAX_TOKENS = 1024


def _normalize(block) -> dict:
    if isinstance(block, dict):
        return block
    t = getattr(block, "type", None)
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name,
                "input": block.input}
    return {"type": t or "unknown"}


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = [_normalize(b) for b in content]
        self.stop_reason = stop_reason


class AnthropicLLM:
    def __init__(self, *, client=None, api_key: str | None = None,
                 model: str = "claude-sonnet-4-6") -> None:
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._model = model

    async def create(self, *, system: str, messages: list, tools: list):
        resp = self._client.messages.create(
            model=self._model, max_tokens=_MAX_TOKENS, system=system,
            messages=messages, tools=tools)
        return _Msg(resp.content, getattr(resp, "stop_reason", "end_turn"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_anthropic_adapter.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/anthropic_adapter.py tests/test_anthropic_adapter.py
git commit -m "feat: Anthropic SDK adapter (loop seam, normalized blocks)"
```

---

### Task 2: Composition root

**Files:**
- Create: `src/robin/main.py`

- [ ] **Step 1: Write `src/robin/main.py`**

```python
"""Composition root. Builds real adapters from validated settings and
exposes `app` for uvicorn. Fails fast if any secret is missing."""
from browser_use_sdk.v3 import AsyncBrowserUse

from robin.agentphone_client import AgentPhoneClient
from robin.anthropic_adapter import AnthropicLLM
from robin.app import build_app
from robin.config import load_settings
from robin.context_pack import load_context_pack
from robin.outbound import (CallRegistry, make_deliver_result,
                            make_place_negotiation_call)
from robin.prompts import (render_inbound_system_prompt,
                           render_outbound_system_prompt)

CONTEXT_PACK_PATH = "context_pack.json"   # gitignored; real PII lives here
LAW_HTML_PATH = "src/robin/fixtures/law.html"

_settings = load_settings()                       # fail-fast on missing env
_pack = load_context_pack(CONTEXT_PACK_PATH)      # fail-fast on placeholders

_ap = AgentPhoneClient(api_key=_settings.agentphone_api_key)
_llm = AnthropicLLM(api_key=_settings.anthropic_api_key,
                    model="claude-sonnet-4-6")
_browser = AsyncBrowserUse()                      # reads BROWSER_USE_API_KEY
_registry = CallRegistry()


async def _research(jurisdiction: str) -> dict:
    from robin.tools import research_cancellation_law
    return await research_cancellation_law(
        jurisdiction, browser=_browser,
        law_url=f"{_settings.public_base_url}/fixture/law.html",
        law_html_path="src/robin/fixtures/law.html")


_outbound_prompt = render_outbound_system_prompt(
    _pack, citations=[])  # citations interpolated per-call by the model text;
# the law block is also carried in the tool result the model already saw.

_tool_impls = {
    "research_cancellation_law": _research,
    "place_negotiation_call": make_place_negotiation_call(
        client=_ap, registry=_registry, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        receptionist_to_number=_settings.receptionist_to_number,
        outbound_system_prompt=render_outbound_system_prompt(_pack, [])),
    "deliver_result": make_deliver_result(
        client=_ap, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        callback_number=_pack.callback_number),
}

app = build_app(
    secret=_settings.agentphone_webhook_secret.encode(),
    law_html_path=LAW_HTML_PATH, llm=_llm, tool_impls=_tool_impls,
    system_prompt=render_inbound_system_prompt(_pack))
```

> Note: `render_outbound_system_prompt(_pack, [])` will raise
> `PromptRenderError` because `{{citations}}` is unfilled. **Fix in
> Step 2** — the outbound prompt's citations must be bound at call time.
>
> Note (cross-ref Plan 03): the `_research` wrapper passes
> `law_html_path="src/robin/fixtures/law.html"` so the research tool has a
> **deterministic local fallback** if Browser Use fails/hangs on stage.
> Plan 03's updated signature is
> `research_cancellation_law(jurisdiction, *, browser, law_url,
> law_html_path=None)` — `law_html_path` is the local committed fixture
> the tool falls back to when the live Browser Use path errors. **The
> mandatory recorded backup (Task 7) must still be captured on the REAL
> Browser Use path — the local fallback is a live-stage safety net only.**

- [ ] **Step 2: Bind citations at call time (correct the seam)**

Change `make_place_negotiation_call` usage so the outbound system prompt
is rendered with the citations the model passes in. Delete the
`_outbound_prompt = ...` line and the eager
`_tool_impls["place_negotiation_call"]` entry, and replace them with a
per-call wrapper that binds citations at call time:

```python
# delete the `_outbound_prompt = render_outbound_system_prompt(_pack, [])`
# line and the `"place_negotiation_call": make_place_negotiation_call(...)`
# entry in _tool_impls, then add:
from robin.models import Citation


async def _place(phone: str, member_name: str, citations: list[dict]) -> dict:
    cites = [Citation(c["citation"], c["operative_quote"],
                       c.get("source_url", "")) for c in citations]
    impl = make_place_negotiation_call(
        client=_ap, registry=_registry, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        receptionist_to_number=_settings.receptionist_to_number,
        outbound_system_prompt=render_outbound_system_prompt(_pack, cites))
    return await impl(phone=phone, member_name=member_name,
                      citations=citations)


_tool_impls["place_negotiation_call"] = _place
```

Re-import check:

Run: `cd /Users/francescorosciano/docs/robin && set -a && . ./.env && set +a && python3 -c "import robin.main; print('composed OK')"`
Expected: `composed OK` (proves the startup guard + pack guard + prompt
render all pass with the real `.env`).

> **Cross-ref Plan 07 (not a conflict / not a surprise):** at execution
> time Plan 07 additively wires the `/stage` projector route and the
> `on_turn=broadcaster.publish` hook into `src/robin/main.py` (it builds
> a `TurnBroadcaster` in `src/robin/broadcast.py`, mounts `/stage`, and
> passes `on_turn=broadcaster.publish` into the outbound capture). So
> `main.py` legitimately gains those lines when Plan 07's staging half
> runs — this is expected and additive, NOT a collision with this task's
> composition root. `on_turn` is Plan 04's optional kw-only callback
> (Plan 04 Task 5), backward-compatible and outside the Plan 00 frozen
> contract.

- [ ] **Step 3: Commit**

```bash
git add src/robin/main.py
git commit -m "feat: composition root (real adapters, call-time citations)"
```

---

### Task 3: Context pack with real (gitignored) values

**Files:**
- Create: `context_pack.json` (**gitignored — real PII, never commit**)
- Modify: `.gitignore` (ensure `context_pack.json` is listed)

- [ ] **Step 1: Ensure gitignore**

Confirm `.gitignore` contains `context_pack.json` and `.env`.
Run: `grep -E 'context_pack.json|^\.env' .gitignore && echo OK`
Expected: both present, `OK`. If missing, add them, then:
`git add .gitignore && git commit -m "chore: gitignore context pack + env"`.

- [ ] **Step 2: Create `context_pack.json` with the real demo values**

Real callback number = the presenter's phone (E.164). `receptionist_to_number`
= the E.164 from Plan 05 (the simulated agent, or the fallback phone).
`target_display_number` = "415-776-2200" (what Robin SAYS).

Run: `git status --porcelain context_pack.json`
Expected: empty output (file is gitignored — not tracked).

- [ ] **Step 3: Validate the pack guard accepts it**

Run: `python3 -c "from robin.context_pack import load_context_pack as L; L('context_pack.json'); print('pack OK')"`
Expected: `pack OK` (no `ContextPackError`).

---

### Task 4: Smoke — Robin speaks one line

- [ ] **Step 1: Start the composed server (tunnel already up from Plan 05)**

Run: `cd /Users/francescorosciano/docs/robin && set -a && . ./.env && set +a && uvicorn robin.main:app --port 8000`
Expected: uvicorn starts with no `ConfigError`/`ContextPackError`.

- [ ] **Step 2: Health + law fixture over the public URL**

Run: `curl -s $PUBLIC_BASE_URL/healthz && curl -s $PUBLIC_BASE_URL/fixture/law.html | head -c 80`
Expected: `{"ok":true}` then the start of the law HTML (3 citations
present).

- [ ] **Step 3: Live inbound smoke call**

Call Robin's provisioned number from a phone. Say "hello".
Expected: Robin speaks (interim ack then a real reply). If silent, check
the uvicorn log + that the webhook URL registered in Plan 05 matches the
current tunnel host.

- [ ] **Step 4: Checkpoint**

Robin answers and speaks on a real call → proceed. (DAY_PLAN: this is
build-order step 1 "agent speaks one line".)

---

### Task 5: MANUAL receptionist win gate (design-doc Assignment — gate before trusting Robin)

> Design doc: *"If you can't win that argument by hand at noon, Robin
> can't at 7:45 PM."* Do this **by a human**, before trusting the
> pipeline.

- [ ] **Step 1: Call the receptionist number by hand and win it**

Dial `RECEPTIONIST_TO_NUMBER`. Walk the four escalation blocks; deliver
the two-option ultimatum verbatim from
`src/robin/fixtures/prompts/outbound_negotiation.txt`.
Expected: the receptionist says, verbatim, *"Fine — I'll cancel your
subscription and refund your last month. Your confirmation number is
24HF-4471."*

- [ ] **Step 2: Gate**

- Receptionist capitulates correctly → proceed to Task 6.
- It does not → fix `src/robin/fixtures/prompts/receptionist.txt`
  (Plan 02) or invoke the Plan 05 fixture fallback. Do **not** proceed
  until a human can win it by hand.

---

### Task 6: First full end-to-end pipeline run

- [ ] **Step 1: Run the canonical path live**

Call Robin: "I want to cancel my gym membership." Answer "24 Hour
Fitness". Approve the call. Say "two" (callback path first — it is the
primary per SPEC).
Expected sequence (watch uvicorn log): interim ack → `research_cancellation_law`
returns OK with the X/Y/Z citations → `place_negotiation_call` returns a
`call_id` → the SSE capture task accumulates the negotiation → classifier
yields `DONE` + `24HF-4471` → `deliver_result` callback rings the
presenter with "cancelled, last-month refund, confirmation 24HF-4471".

- [ ] **Step 2: Confirm the recording exists (dashboard receipt)**

Run: `python3 -c "import asyncio,os; from robin.agentphone_client import AgentPhoneClient as A; c=A(os.environ['AGENTPHONE_API_KEY']); print(asyncio.run(c.get_recording_url('<the outbound call_id from the log>')))"`
Expected: a non-empty `recordingUrl` (the AgentPhone dashboard shows the
call + recording — this is the "dashboard" deliverable; no custom UI).

- [ ] **Step 3: Agent-identity / prompt-routing assertion**

From the captured outbound transcript (the SSE `turn` accumulation logged
in Step 1), verify **both** agents ran their provisioned persona — this
catches a mis-provisioned 2nd agent or a wrong systemPrompt landing on
the wrong leg:

- The **receptionist** agent ran ITS provisioned escalation script: all
  four escalation blocks appear in the receptionist's turns (in person /
  50% off / certified letter / stalling), matching
  `src/robin/fixtures/prompts/receptionist.txt` (Plan 02).
- **Robin's outbound systemPrompt is in effect**: Robin cites the X/Y/Z
  law and delivers the verbatim two-option ultimatum, matching
  `src/robin/fixtures/prompts/outbound_negotiation.txt` (Plan 02).

If the receptionist capitulates without the four blocks, or Robin never
cites the law / never delivers the ultimatum, the 2nd agent or a
systemPrompt is mis-routed — fix Plan 05 provisioning (which prompt is
bound to which agent) before trusting the pipeline. Do not proceed.

- [ ] **Step 4: Gate**

Full happy path worked once end-to-end **and** both personas verified in
the transcript → **immediately** go to Task 7 (capture the backup before
touching anything else).

---

### Task 7: Capture the MANDATORY recorded backup (do this the moment Task 6 passes)

> DAY_PLAN + design doc: the recorded backup is the Google-form video AND
> the stage safety net. Never go on stage without it already recorded.

> **Browser Use integrity decision (do not relitigate):** the mandatory
> recorded backup MUST be captured on the **REAL Browser Use path** — the
> live research tool actually hitting the web. The Plan 03 local
> `law.html` fixture fallback is a **live-stage safety net only**; a
> backup recorded on the fallback path is NOT a valid submission artifact.
> Same integrity reasoning as the design doc's live-vs-recorded bright
> line: scripting/safety nets are fine and disclosed, but the recorded
> proof must show the genuine pipeline running. Before recording, confirm
> the uvicorn log shows `research_cancellation_law` returned via Browser
> Use (not the local-fixture fallback branch).

- [ ] **Step 1: Screen-record one clean, unattended, end-to-end run**

Start a screen+audio recorder. Repeat the Task 6 path start-to-finish
with no operator intervention. Capture: the inbound call, the uvicorn log
showing the real tool calls, the negotiation audio, the callback, and the
AgentPhone dashboard showing the call + recording.

- [ ] **Step 2: Save the artifact**

Save as `docs/demo-backup-recording.<ext>` **outside git** if large
(>25MB) — note its location in `docs/RUNSHEET.md`. If small, it may be
linked from the README (not committed binary). This file is the
submission video.

- [ ] **Step 3: Gate (hard)**

A clean recording exists and plays back fully → only now continue.
**If 6 PM arrives without this recording, stop feature work and get this
recording with whatever currently works** (DAY_PLAN freeze rule).

---

### Task 8: Stage runsheet card + rehearse ×3

> **Cross-ref Plan 07 (do not run this bare):** the "rehearse ×3" below
> must be performed WITH Plan 07's full stage setup — the `/stage`
> projector page live on the screen, the "AI simulation" disclosure
> slide, the PA system, and an audible callback. **Plan 07 Task 6
> (integrated stage rehearsal) supersedes/extends this task**; the
> combined rehearsal (this + Plan 07) is the single gate before
> submission. Treat the steps here as the content checklist; Plan 07
> owns the AV/staging wrapper around it.

**Files:**
- Create: `docs/RUNSHEET.md`

- [ ] **Step 1: Write `docs/RUNSHEET.md`**

Copy the 7-step Stage Runsheet from the design doc verbatim, plus a
timed column and this on-screen disclosure line: **"The receptionist is
an AI simulation. The real 24 Hour Fitness is never called."** Include
the pre-decided checkpoints (no-key, DTMF=voice, 6 PM freeze) as a
"if it breaks" footer.

- [ ] **Step 2: Rehearse the live runsheet 3× against a clock**

Run the full live path 3 times, timing each. Confirm: discovery wording,
the "found 415-776-2200" line, the disclosure slide is visible, the
negotiation lands the ultimatum, the callback delivers `24HF-4471`.
Note the median duration in `docs/RUNSHEET.md` so the stage slot is known.

- [ ] **Step 3: Commit**

```bash
git add docs/RUNSHEET.md
git commit -m "docs: stage runsheet (timed) + AI-simulation disclosure"
```

---

### Task 9: Submission prep (agent prepares; human pushes — agent is denied push)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update `README.md`**

Ensure: one-line pitch ("phone your agent; it does the call you hate"),
exact run steps (`pip install -e ".[dev]"`, `.env` from `.env.example`,
tunnel, `python3 scripts/setup_agentphone.py`, `uvicorn robin.main:app`),
the integrity statement (live + recorded backup; receptionist = disclosed
AI simulation; real company never called), and a link/pointer to the
recorded backup.

- [ ] **Step 2: Secrets / PII sweep of the whole history**

Run: `git log -p | grep -nEi 'AGENTPHONE_API_KEY=|BROWSER_USE_API_KEY=|ANTHROPIC_API_KEY=|sk-[A-Za-z0-9]|\+1(?!555)[0-9]{10}' | head`
Expected: **no output**. Also: `git ls-files | grep -E '\.env$|context_pack.json|demo-backup-recording'`
Expected: **no output** (none tracked). If anything appears, STOP and
remediate before any push.

- [ ] **Step 3: Sync `.env.example` to the full required-var set (public-repo runnable)**

Before the repo goes public, ensure `.env.example` lists **every**
variable the startup guard requires — a stale example causes a
startup-guard failure for anyone cloning the public repo. It must contain
(placeholder values only — **no real secrets**):

```
ANTHROPIC_API_KEY=
AGENTPHONE_API_KEY=
AGENTPHONE_WEBHOOK_SECRET=
BROWSER_USE_API_KEY=
ROBIN_AGENT_ID=
FROM_NUMBER_ID=
RECEPTIONIST_TO_NUMBER=
PUBLIC_BASE_URL=
RECEPTIONIST_AGENT_ID=
RECEPTIONIST_NUMBER_ID=
```

Verify every name in the config guard appears in `.env.example`:

Run: `python3 -c "from robin.config import _REQUIRED; missing=[v for v in _REQUIRED if v not in open('.env.example').read()]; print('MISSING:', missing) if missing else print('env.example OK')"`
Expected: `env.example OK` (every `config._REQUIRED` name is present).

Then: `git add .env.example && git commit -m "chore: sync .env.example to full required-var set"`.

- [ ] **Step 4: Final green check**

Run: `python3 -m pytest -q && python3 -m ruff check src tests`
Expected: all tests pass, coverage ≥ 80%, ruff clean.

- [ ] **Step 5: Hand off to the human (these steps the agent must NOT do)**

Print this checklist for the user to perform via `!`:

```
# HUMAN-ONLY (agent is denied git push + external repo ops by settings):
1. Create the public GitHub repo (fresh, today).
2. git remote add origin <url> && git push -u origin main
3. Verify the repo is PUBLIC and the README + recording link render.
4. Submit the Google form: video (docs/demo-backup-recording) + repo URL.
5. Do this BEFORE 8:00 PM.
```

- [ ] **Step 6: Final commit (content only — no secrets)**

```bash
git add README.md
git commit -m "docs: README run steps + integrity statement for submission"
```

---

## Pre-decided checkpoints (embedded — do not relitigate live)

- **No API key by early afternoon:** Waves 1–2 already done against
  fakes; the moment keys land, Plan 05 run → this plan. Escalate keys on
  Discord/on-site in parallel.
- **Inbound DTMF unsupported:** already shipped voice keyword
  ("say one / say two"). No call-bridging.
- **2nd agent stalls:** Plan 05 fixture fallback (teammate phone / TTS).
- **6:00 PM:** feature freeze. Whatever is end-to-end is the demo. If the
  recorded backup (Task 7) does not yet exist, stop everything and
  capture it now with whatever works.
- **Live run drifts on stage:** the recorded backup is the submission and
  the safety net regardless — it must already exist before stage.

---

## Self-Review

- **Spec coverage:** real-adapter composition (the Plan 03 deferred
  seam); startup + pack fail-fast; smoke (DAY_PLAN step 1); manual win
  gate (design "Assignment"); full E2E (SPEC "Acceptance"); recording =
  dashboard receipt (no custom UI — Approach A cut); mandatory recorded
  backup (DAY_PLAN/design); rehearse ×3 + disclosure (DAY_PLAN
  "Submission"); human-only push + Google form (design "Distribution");
  all DAY_PLAN checkpoints embedded. Covered.
- **Placeholder scan:** Task 2 explicitly flags the `{{citations}}`
  render trap and fixes it with full code (call-time citation binding) —
  no unresolved placeholder ships.
- **Browser Use fallback wired (Task 2):** the `_research` wrapper passes
  `law_html_path="src/robin/fixtures/law.html"` into Plan 03's
  `research_cancellation_law(jurisdiction, *, browser, law_url,
  law_html_path=None)` — deterministic local fallback for live-stage
  safety. The integrity rule is stated at the call site and at Task 7:
  the recorded backup MUST be on the REAL Browser Use path; the fallback
  is a stage safety net only, never the artifact.
- **Agent-identity / prompt-routing assertion (Task 6 Step 3):** the
  captured outbound transcript is checked so the receptionist ran its
  four provisioned escalation blocks AND Robin's outbound systemPrompt
  is in effect (law cited + verbatim ultimatum) — catches a
  mis-provisioned 2nd agent or a wrong systemPrompt before trusting the
  pipeline.
- **`.env.example` synced (Task 9 Step 3):** the public repo is runnable
  — every `config._REQUIRED` var (incl. `ANTHROPIC_API_KEY`,
  `RECEPTIONIST_AGENT_ID`, `RECEPTIONIST_NUMBER_ID`) appears in
  `.env.example` with placeholder-only values; a programmatic check
  enforces no stale-example startup-guard failure. No secrets in the
  example.
- **Plan 07 cross-refs (no collisions):** Task 8's "rehearse ×3" is
  explicitly run WITH Plan 07's full stage setup (projector, disclosure
  slide, PA, audible callback) — Plan 07 Task 6 supersedes/extends it.
  Task 2 notes that Plan 07 additively wires the `/stage` route +
  `on_turn=broadcaster.publish` into `main.py` at execution time
  (`on_turn` = Plan 04's optional kw-only callback, backward-compatible,
  outside the Plan 00 frozen contract) — expected, not a surprise.
- **Type consistency:** `AnthropicLLM.create(system, messages, tools)`
  matches `loop.run_turn`'s `llm`; `_tool_impls` keys match
  `TOOL_SCHEMAS` names; `make_place_negotiation_call` /
  `make_deliver_result` signatures match Plan 04; `load_settings()` vars
  match Plan 05's printed env names; `research_cancellation_law`'s new
  `law_html_path=None` kwarg matches Plan 03's updated signature.
  Consistent end-to-end.
