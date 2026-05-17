# Robin Plan 07 — Stage Presentation & AV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. This is an operational + live + human-in-loop plan (one small web artifact + staging/AV/rehearsal), not TDD. Execute inline with checkpoints; several steps are human-only (on-stage).

**Goal:** Surface the live Robin-vs-receptionist negotiation to the room — projector shows a scrolling transcript, disclosure banner is always visible, the multi-minute "dead air" problem is eliminated, PA carries both sides audibly, and the choreography decision between a full-live run and a hybrid live+recorded contingency is pre-decided and written down before the presenter walks on stage.

**Architecture:** An in-process `TurnBroadcaster` (async pub/sub, bounded queue) is the single fan-out point. The Plan 04 SSE capture task (the only AgentPhone SSE reader) re-publishes each `TranscriptTurn` to the broadcaster via an optional `on_turn` callback. A `GET /stage/stream` SSE endpoint subscribes to the broadcaster and pushes turns to the projector browser tab. A `GET /stage` route serves a self-contained HTML page with a live auto-scrolling transcript and a persistent AI-simulation disclosure banner. The broadcaster is the only new piece of infrastructure; the SSE capture path in Plan 04 is unchanged except for a backward-compatible optional `on_turn` keyword argument.

**Tech Stack:** Python 3.11+, asyncio, FastAPI (`StreamingResponse` + `EventSourceResponse` via `sse-starlette` or raw `StreamingResponse`), pytest-asyncio. No new third-party deps beyond what Plan 03 already uses. The projector artifact is plain HTML/CSS/JS (no build step). AV runbook and disclosure slide are plain Markdown/HTML files.

**Depends on:** Plan 04 (frozen `AgentPhoneClient.stream_transcript` / `TranscriptTurn`), Plan 02 disclosure content, Plan 06 live pipeline + `src/robin/main.py` composition root.

---

## File Structure

- Create `src/robin/broadcast.py` — `TurnBroadcaster` (async pub/sub fan-out).
- Create `tests/test_broadcast.py` — unit tests for broadcaster.
- Modify `src/robin/main.py` — instantiate `broadcaster`, pass `on_turn=broadcaster.publish` into the `_place` wrapper.
- Create `src/robin/stage.py` — `GET /stage` HTML route + `GET /stage/stream` SSE route; mounted onto the FastAPI app.
- Modify `src/robin/main.py` (additive) — mount `stage.py` router.
- Create `docs/stage/disclosure-slide.md` — full-screen disclosure + pitch content (real, required integrity artifact).
- Create `docs/stage/av-runbook.md` — AV setup, per-step projector content, PA plan, choreography decision.

---

### Task 1: Live-transcript broadcaster

**Files:**
- Create: `src/robin/broadcast.py`
- Test: `tests/test_broadcast.py`

The broadcaster is the fan-out primitive. `AgentPhoneClient.stream_transcript` may be single-consumer (SSE streams commonly are). The Plan 04 capture task is the **only** direct SSE reader; it re-publishes each turn here. The projector and any future subscriber get their own bounded queue — they never touch the raw SSE stream.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_broadcast.py
import asyncio
import pytest
from robin.broadcast import TurnBroadcaster
from robin.agentphone_client import TranscriptTurn

TURN_A = TranscriptTurn(role="agent", content="Hello.", created_at="t1")
TURN_B = TranscriptTurn(role="user", content="Cancel please.", created_at="t2")


async def test_two_subscribers_both_receive_published_turn():
    b = TurnBroadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()
    await b.publish(TURN_A)
    assert q1.get_nowait() == TURN_A
    assert q2.get_nowait() == TURN_A


async def test_unsubscribed_queue_does_not_receive():
    b = TurnBroadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()
    b.unsubscribe(q2)
    await b.publish(TURN_B)
    assert q1.get_nowait() == TURN_B
    with pytest.raises(asyncio.QueueEmpty):
        q2.get_nowait()


async def test_full_queue_drops_turn_without_raising():
    b = TurnBroadcaster(maxsize=1)
    q = b.subscribe()
    await b.publish(TURN_A)   # fills the slot
    await b.publish(TURN_B)   # should drop silently, not raise
    assert q.get_nowait() == TURN_A  # first turn still there
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()           # second turn was dropped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_broadcast.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.broadcast'`.

- [ ] **Step 3: Write `src/robin/broadcast.py`**

```python
"""In-process async pub/sub fan-out for transcript turns.

The Plan 04 SSE capture task is the ONLY AgentPhone SSE reader.
It calls broadcast.publish(turn) after each turn; every subscriber
(e.g. the projector SSE endpoint) gets its own bounded asyncio.Queue.
Turns are dropped (not raised) on a full queue so a slow projector
client never blocks the capture task.
"""
import asyncio
from robin.agentphone_client import TranscriptTurn


class TurnBroadcaster:
    def __init__(self, maxsize: int = 64) -> None:
        self._maxsize = maxsize
        self._queues: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """Return a new bounded queue that will receive future turns."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a queue; it will receive no further turns."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass  # already removed — idempotent

    async def publish(self, turn: TranscriptTurn) -> None:
        """Fan out turn to every subscriber queue. Non-blocking: drop on full."""
        for q in list(self._queues):
            try:
                q.put_nowait(turn)
            except asyncio.QueueFull:
                pass  # slow consumer — drop, do not block capture task
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_broadcast.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/broadcast.py tests/test_broadcast.py
git commit -m "feat: TurnBroadcaster async pub/sub fan-out for projector"
```

---

### Task 2: Wire the broadcaster into the capture task and the composition root

**Files:**
- Modify: `src/robin/main.py` (additive — Plan 04's `on_turn` hook from Task 5 of that plan must be merged first)

This task depends on Plan 04 Task 5 (the `on_turn` keyword-only callback added to `capture_and_classify` and forwarded by `make_place_negotiation_call`). The changes to `main.py` are purely additive — no existing wiring is removed.

- [ ] **Step 1: Instantiate the broadcaster in `main.py`**

After the `_registry = CallRegistry()` line, add:

```python
from robin.broadcast import TurnBroadcaster
_broadcaster = TurnBroadcaster()
```

- [ ] **Step 2: Forward `on_turn` into the `_place` wrapper**

The `_place` async wrapper in `main.py` calls `make_place_negotiation_call(...)` and then `impl(...)`. Change the `make_place_negotiation_call` call inside `_place` to pass `on_turn=_broadcaster.publish`:

```python
async def _place(phone: str, member_name: str, citations: list[dict]) -> dict:
    cites = [Citation(c["citation"], c["operative_quote"],
                      c.get("source_url", "")) for c in citations]
    impl = make_place_negotiation_call(
        client=_ap, registry=_registry, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        receptionist_to_number=_settings.receptionist_to_number,
        outbound_system_prompt=render_outbound_system_prompt(_pack, cites),
        on_turn=_broadcaster.publish)          # <-- additive; Plan 04 Task 5
    return await impl(phone=phone, member_name=member_name,
                      citations=citations)
```

This is the complete change to `_place`. No other lines in `main.py` change.

- [ ] **Step 3: Verify import chain is clean**

Run: `python3 -c "from robin.broadcast import TurnBroadcaster; print('broadcaster OK')"`
Expected: `broadcaster OK`.

- [ ] **Step 4: Commit**

```bash
git add src/robin/main.py
git commit -m "feat: wire TurnBroadcaster into composition root via on_turn"
```

---

### Task 3: Projector page and stage routes

**Files:**
- Create: `src/robin/stage.py`
- Modify: `src/robin/main.py` (mount the stage router)

The projector tab is open on the display before the demo starts. The disclosure banner is hard-coded in the HTML — it is always visible. Auto-scroll keeps the newest turns visible during the negotiation. No JavaScript framework; self-contained single file.

- [ ] **Step 1: Write `src/robin/stage.py`**

```python
"""Stage projector routes.

GET /stage       — serve the self-contained HTML projector page.
GET /stage/stream — SSE stream of TranscriptTurn events for the page JS.

Mount this router onto the main FastAPI app AFTER the broadcaster is
available. The broadcaster singleton is passed in via the factory so this
module stays testable without importing main.py.
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse


_STAGE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Robin — Live Negotiation</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0a0a; color: #f0f0f0; font-family: 'Segoe UI', system-ui, sans-serif; }

  #banner {
    position: fixed; top: 0; left: 0; right: 0;
    background: #b91c1c; color: #fff;
    text-align: center; font-size: 1.4rem; font-weight: 700;
    padding: 0.6rem 1rem;
    z-index: 100;
    letter-spacing: 0.04em;
  }

  #transcript {
    margin-top: 4rem; padding: 2rem;
    max-width: 900px; margin-left: auto; margin-right: auto;
  }

  .turn {
    margin-bottom: 1.8rem;
    padding: 1rem 1.4rem;
    border-radius: 0.6rem;
    font-size: 1.6rem;
    line-height: 1.5;
    max-width: 85%;
  }
  .turn.agent {
    background: #1e3a5f;
    border-left: 6px solid #3b82f6;
    margin-right: auto;
  }
  .turn.user {
    background: #1a3a1a;
    border-left: 6px solid #22c55e;
    margin-left: auto;
  }
  .turn .label {
    font-size: 0.85rem;
    font-weight: 600;
    opacity: 0.7;
    margin-bottom: 0.4rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
</style>
</head>
<body>
<div id="banner">
  AI SIMULATION &mdash; the receptionist is an AI.&nbsp;
  The real 24 Hour Fitness is never called.
</div>
<div id="transcript"></div>
<script>
  const transcript = document.getElementById('transcript');
  const es = new EventSource('/stage/stream');

  es.addEventListener('turn', function(e) {
    const data = JSON.parse(e.data);
    const div = document.createElement('div');
    div.className = 'turn ' + (data.role === 'agent' ? 'agent' : 'user');
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = data.role === 'agent' ? 'Robin' : 'Receptionist';
    const text = document.createElement('div');
    text.textContent = data.content;
    div.appendChild(label);
    div.appendChild(text);
    transcript.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  });

  es.onerror = function() {
    // reconnect is automatic with EventSource — no action needed
  };
</script>
</body>
</html>
"""


def make_stage_router(broadcaster) -> APIRouter:
    """Build the /stage router bound to the given TurnBroadcaster instance."""
    router = APIRouter()

    @router.get("/stage", response_class=HTMLResponse)
    async def stage_page():
        return HTMLResponse(content=_STAGE_HTML)

    @router.get("/stage/stream")
    async def stage_stream():
        """SSE endpoint: subscribe to the broadcaster, emit turn events."""
        q = broadcaster.subscribe()

        async def event_generator():
            try:
                while True:
                    try:
                        turn = await asyncio.wait_for(q.get(), timeout=15.0)
                        payload = json.dumps(
                            {"role": turn.role, "content": turn.content})
                        yield f"event: turn\ndata: {payload}\n\n"
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"   # keep the connection alive
            except asyncio.CancelledError:
                pass
            finally:
                broadcaster.unsubscribe(q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            })

    return router
```

- [ ] **Step 2: Mount the stage router in `main.py`**

After the `app = build_app(...)` line, add:

```python
from robin.stage import make_stage_router
app.include_router(make_stage_router(_broadcaster))
```

This is the only addition to `main.py` for this task.

- [ ] **Step 3: Manual verification with the canned SSE fixture**

Start the server with the real `.env` and replay the canned `transcript_done.sse` fixture into the broadcaster via a small test script, then verify the projector renders correctly:

```python
# scripts/test_stage_projector.py  (not committed; run interactively)
"""Replay the DONE fixture into the broadcaster so the /stage page can be
verified manually without a live call. Run alongside a running uvicorn server.
"""
import asyncio
import sys
sys.path.insert(0, "src")

from robin.agentphone_client import TranscriptTurn

TURNS = [
    TranscriptTurn("user", "I need to cancel my membership.", "t1"),
    TranscriptTurn("agent", "You can only cancel in person at your home club.", "t2"),
    TranscriptTurn("user", "Two options: easy or hard. Your decision.", "t3"),
    TranscriptTurn("agent",
                   "Fine — I'll cancel your subscription and refund your last "
                   "month. Your confirmation number is 24HF-4471.", "t4"),
]

async def main():
    # Import after uvicorn has started so the singleton exists
    from robin.main import _broadcaster
    for turn in TURNS:
        await _broadcaster.publish(turn)
        await asyncio.sleep(1.0)   # pace the display
    print("done")

asyncio.run(main())
```

Run: Open `http://localhost:8000/stage` in a browser (or the projector tab).
Run: `python3 scripts/test_stage_projector.py`
Expected:
- The red banner "AI SIMULATION — the receptionist is an AI. The real 24 Hour Fitness is never called." is permanently visible at the top.
- Four transcript turns render in sequence with auto-scroll: user turn (green border, label "Receptionist"), agent turns (blue border, label "Robin").
- No console errors in the browser DevTools.

- [ ] **Step 4: Commit**

```bash
git add src/robin/stage.py src/robin/main.py
git commit -m "feat: /stage projector page + /stage/stream SSE endpoint"
```

---

### Task 4: Disclosure slide artifact

**Files:**
- Create: `docs/stage/disclosure-slide.md`

This is a required integrity and brand-safety artifact per the design doc. It provides the full-screen content shown on the projector at the moment Robin dials out (Step 3 of the Stage Runsheet), before the `/stage` live-transcript page takes over. It must exist as a real file with real content — not a TODO.

- [ ] **Step 1: Create `docs/stage/disclosure-slide.md`**

```markdown
# docs/stage/disclosure-slide.md

## Full-Screen Disclosure Slide — shown during outbound dial-out (Runsheet Step 3)

Display this slide on the projector from the moment Robin says
"want me to call and cancel for you?" through the instant the first
transcript turn appears on `/stage`. Switch to the `/stage` live
transcript page when the first turn renders.

---

<!-- ============================================================
     PROJECTOR CONTENT — paste into Keynote/Google Slides or
     display docs/stage/disclosure.html full-screen.
     Font: white on black, centered, maximum size.
     ============================================================ -->

**AI SIMULATION**

The receptionist in this call is an AI agent.
The real 24 Hour Fitness is never called.

---

*"Phone your agent; it does the call you hate."*

**Robin** — AgentPhone × Browser Use — YC Hackathon 2026-05-17

---

<!-- Legal research is real. Cancellation laws cited are pre-verified
     against primary sources (see src/robin/fixtures/law.html).
     Both call sides (Robin's playbook + simulated receptionist) are
     scripted and disclosed. No faked video; no fake repo. -->
```

- [ ] **Step 2: Create `docs/stage/disclosure.html` (display version)**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Robin — Disclosure Slide</title>
<style>
  html, body {
    height: 100%; margin: 0; padding: 0;
    background: #000; color: #fff;
    font-family: 'Segoe UI', system-ui, sans-serif;
    display: flex; align-items: center; justify-content: center;
  }
  .slide {
    text-align: center;
    max-width: 900px;
    padding: 2rem;
  }
  h1 { font-size: 5rem; font-weight: 800; color: #ef4444; margin-bottom: 1rem; }
  p  { font-size: 2rem; line-height: 1.5; margin-bottom: 1.5rem; }
  .pitch { font-size: 1.6rem; font-style: italic; color: #a3a3a3; }
  .product { font-size: 1.3rem; margin-top: 2rem; color: #737373; }
</style>
</head>
<body>
<div class="slide">
  <h1>AI SIMULATION</h1>
  <p>The receptionist in this call is an AI agent.<br>
     The real 24 Hour Fitness is never called.</p>
  <p class="pitch">"Phone your agent; it does the call you hate."</p>
  <p class="product">Robin &mdash; AgentPhone &times; Browser Use &mdash; YC Hackathon 2026-05-17</p>
</div>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add docs/stage/disclosure-slide.md docs/stage/disclosure.html
git commit -m "docs: disclosure slide artifact (integrity + brand-safety)"
```

---

### Task 5: AV runbook and choreography decision

**Files:**
- Create: `docs/stage/av-runbook.md`

This is the pre-decided choreography document. The choreography decision is explicit and written down before the presenter walks on stage so there is no live judgment call under pressure.

- [ ] **Step 1: Create `docs/stage/av-runbook.md`**

```markdown
# docs/stage/av-runbook.md — Robin Stage AV Runbook

> Pre-decided. Do not relitigate live. Read before walking on stage.
> Median rehearsal duration: ___ min ___ sec  ← fill in after Task 6 ×3 rehearsals.

---

## AV Setup (configure before the slot; do not adjust during)

| Item | Setup |
|------|-------|
| Presenter's phone | Audio-out → PA mixer via 3.5mm jack OR speakerphone on a lapel mic stand |
| Robin's spoken side | Flows through AgentPhone → presenter's phone speaker → PA |
| Callback ring + audio | Same phone → PA (callback rings audibly in the room) |
| Projector | Browser tab open at `http://localhost:8000/stage` — full-screen, no chrome, disclosure banner always visible |
| Disclosure slide | `docs/stage/disclosure.html` open in a second tab — switch TO this tab the instant Robin says "want me to call and cancel for you?" |
| Return to transcript | Switch back to `/stage` tab the moment the first turn renders |
| uvicorn server | Running locally, tunnel up; test PA output before the slot |
| Backup video | `docs/demo-backup-recording.<ext>` queued in QuickTime/VLC, ready to play at 2× |

---

## Per-Step Projector Content (7-Step Stage Runsheet)

| Runsheet Step | What the room sees on the projector |
|---|---|
| **1.** Presenter calls Robin live | `/stage` tab open, empty (no turns yet) — banner visible |
| **2.** Robin discovery: "which gym?" / "24 Hour Fitness" | `/stage` tab — still empty; shows Robin is live |
| **3.** Robin: "found 415-776-2200 — want me to call?" | **Switch to `disclosure.html` tab** — full-screen "AI SIMULATION" slide |
| **4.** Robin dials; negotiation begins | **Switch back to `/stage` tab** the moment first turn renders; auto-scroll does the rest |
| **5.** Escalating exchanges / ultimatum | `/stage` — live transcript scrolling; both Robin and Receptionist turns labeled |
| **6.** Receptionist capitulates | `/stage` — final turn renders on screen |
| **7.** Robin reports back (callback) | `/stage` — callback confirmation visible; presenter answers the callback phone audibly |

---

## How the Multi-Minute "Dead Air" Is Filled

There is no dead air. The `/stage` live transcript IS the fill.
While the negotiation runs (typically 2–4 min), the projector shows
each exchange in real time — the room watches Robin negotiate turn-by-turn.
This is the dramatic core of the demo, not a gap to paper over.

---

## CHOREOGRAPHY DECISION (pre-decided — do not change on stage)

### PRIMARY path (default — use this)

Perform the **full discovery + negotiation + callback live**, with the
`/stage` projector showing the live transcript throughout.

- Discovery (Runsheet Steps 1–3): live on stage, ~60 sec.
- Negotiation (Steps 4–6): live, projector shows the scrolling transcript.
  The room hears the audio via PA and watches the text in real time.
- Callback (Step 7): live; callback rings audibly; presenter answers on stage.

Rationale: this is the "something that didn't exist this morning" moment.
The real-time projector feed removes the dead-air risk; the room is engaged
throughout. The median rehearsal duration (fill in above) tells you if the
slot fits.

### CONTINGENCY path (use only if primary risks overrun or the live call drifts)

If, during the negotiation, the live run is clearly drifting from the
canonical script OR the remaining slot time is under 90 seconds AND the
negotiation is less than halfway done:

1. Presenter says: "Let me show you how this played out in our test run."
2. Switch the projector to the backup video (`docs/demo-backup-recording.<ext>`).
3. Play the negotiation segment only (skip discovery already done live).
4. Return live for the callback (or let the recorded callback play).

The recorded backup is the submission artifact regardless — it must exist
before the presenter walks on stage (Plan 06 Task 7 gate).

### Explicit recommendation

**Use the PRIMARY path.** The `/stage` projector feed solves the dead-air
problem. The CONTINGENCY is a safety net, not the plan.

---

## "AI Simulation" Disclosure Checklist (integrity gate)

- [ ] `docs/stage/disclosure.html` open in second tab before walking on stage
- [ ] Disclosure slide visible for ≥ 3 seconds before switching to `/stage`
- [ ] `/stage` disclosure banner ("AI SIMULATION — the receptionist is an AI.
      The real 24 Hour Fitness is never called.") visible the entire time the
      outbound call is in progress
- [ ] "AI simulation" spoken or on-screen at least once during the live demo

---

## If It Breaks (pre-decided fallbacks — do not invent new ones live)

| Failure | Pre-decided response |
|---------|----------------------|
| `/stage` page blank / no turns | Continue — room hears audio via PA; show `disclosure.html` full-screen as alternative visual |
| Tunnel drops mid-demo | Restart cloudflared (12 s cooldown); fall back to backup video immediately if > 30 s |
| Robin call fails to connect | Fall back to backup video; explain "let me show you the pipeline" |
| Callback does not ring | Presenter narrates the result verbally; show the AgentPhone dashboard recording URL |
| Live negotiation running > slot | Invoke CONTINGENCY path above |
```

- [ ] **Step 2: Commit**

```bash
git add docs/stage/av-runbook.md
git commit -m "docs: AV runbook + choreography decision (primary/contingency)"
```

---

### Task 6: Integrated stage rehearsal ×3 with full AV setup

This task supersedes and extends Plan 06 Task 8's bare rehearsal. Perform the full 7-step Stage Runsheet with the projector (`/stage` tab), `disclosure.html` tab, PA audio, and callback audible, 3 times against a clock.

- [ ] **Step 1: Pre-rehearsal AV check**

Before starting the clock:
- Confirm the `/stage` tab is open and shows the disclosure banner.
- Confirm `disclosure.html` is open in a second tab.
- Confirm uvicorn is running and the tunnel is live.
- Confirm PA audio is audible (say a test phrase via Robin → PA speakers carry it).
- Confirm the backup video is queued and plays back.

- [ ] **Step 2: Run ×1 — first rehearsal, timed**

Execute the full 7-step runsheet per `docs/RUNSHEET.md` (Plan 06 Task 8).
Start the clock at "Presenter calls Robin". Stop it at "callback confirmed + confirmation number spoken".
Note duration: _____ min _____ sec.

Verify after this run:
- The `/stage` projector showed all turns in order with auto-scroll.
- The disclosure banner was visible throughout the outbound call.
- The disclosure slide appeared before the first turn rendered.
- The callback rang audibly.

- [ ] **Step 3: Run ×2 — second rehearsal, timed**

Note duration: _____ min _____ sec.

- [ ] **Step 4: Run ×3 — third rehearsal, timed**

Note duration: _____ min _____ sec.

- [ ] **Step 5: Record median duration and update the runbook**

Calculate the median of the three durations. Update the `docs/stage/av-runbook.md` header line:
`Median rehearsal duration: ___ min ___ sec  ← fill in after Task 6 ×3 rehearsals.`
with the actual median.

If median > slot time: immediately tighten the discovery dialogue wording (Plan 02 prompt) or pre-fill the gym name in the demo.

- [ ] **Step 6: Commit**

```bash
git add docs/stage/av-runbook.md
git commit -m "docs: av-runbook updated with median rehearsal duration"
```

---

## Self-Review

- **Spec coverage:** live projector transcript during negotiation (CLAUDE.md "the room hears/sees Robin out-negotiate"); AI simulation disclosure (design doc integrity bright line, "keep the 'AI simulation' disclosure visible"); no dead air during negotiation (the `/stage` feed IS the fill); PA/callback audibility (Stage Runsheet Step 7); choreography decision (primary live + contingency pre-decided — the "<1 min pitch vs multi-minute run" constraint); Plan 04 `on_turn` hook backward-compatible (does not alter the frozen 00-contract interfaces). Covered.
- **Placeholder scan:** all files have complete content. `disclosure-slide.md` and `disclosure.html` have real text. `av-runbook.md` has one intentional blank (median duration) to be filled after Task 6 rehearsal — this is correct, not a missing placeholder. No `TBD` in code. `scripts/test_stage_projector.py` is explicitly labeled "not committed; run interactively" — it is a verification aid, not a required artifact.
- **Type consistency:** `TurnBroadcaster.publish(turn: TranscriptTurn)` matches the `on_turn` callback signature added in Plan 04 Task 5. `make_stage_router(broadcaster)` receives the `_broadcaster` singleton from `main.py` — no global import. `StreamingResponse` is already a FastAPI/Starlette type (no new deps). `asyncio.Queue` is stdlib. All consistent.
