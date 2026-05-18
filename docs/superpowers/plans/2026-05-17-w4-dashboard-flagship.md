# W4 Dashboard Flagship — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A four-panel live judge-facing dashboard (transcript + Moss citation + Super Memory recall + AgentMail artifact) served at /stage when ROBIN_DASHBOARD_ENHANCED=1; /stage stays unmounted (404) exactly as today when unset.

**Architecture:** `/stage` is NOT mounted today and `TurnBroadcaster` is NOT fed — W4 owns all projector wiring via TWO delimited W4-exclusive insertions in `main.py`. New `src/robin/event_bus.py` (mirrors `TurnBroadcaster` mechanics with an `asyncio.Queue` of `dict` items) and `src/robin/fixtures/stage_dashboard.html` (self-contained four-panel page). Minimal tier = citation+mail panels via W0 `on_research`/`on_outcome` hooks publishing to `EventBus`, plus mounting `make_stage_router` (W0-parametrized, in `stage.py`) from `main.py` — pure-W0-event_bus, fully isolated. Optional transcript-feed tier = a `TurnBroadcaster` instantiated in the W4 wiring block + a flag-gated `_place_with_turns` `_tool_impls` override (mirrors W3 pattern; `make_place_negotiation_call` already accepts `on_turn`). The two W4-exclusive `main.py` insertions are: `>>> W4 dashboard wiring <<<` sub-block (inside the W0 `# --- sponsor extension wiring ---` section, before `build_app`) and `>>> W4 stage mount <<<` lines (immediately after `app = build_app(...)`). Depends on W0 only.

**Tech Stack:** Python 3.12, FastAPI SSE, asyncio, pytest + pytest-asyncio, Docker (all runs inside the container).

---

## File Structure

```
src/robin/
  event_bus.py                         NEW — EventBus (mirrors TurnBroadcaster)
  fixtures/
    stage_dashboard.html               NEW — four-panel SSE dashboard
  main.py                              EDIT — two W4-exclusive delimited insertions only

tests/
  test_event_bus.py                    NEW — 5 unit tests (RED→GREEN)
  test_dashboard_wiring.py             NEW — 9 integration tests (RED→GREEN)
  fakes.py                             APPEND-ONLY — FakeEventBus labeled block

.env.example                           APPEND-ONLY — W4 labeled block
```

**Files that must NOT be modified:** `loop.py`, `stage.py`, `app.py`, `classifier.py`, `signature.py`, `models.py`, `extensions.py`, `broadcast.py`, `config.py`, `context_pack.py`, `prompts.py`, `tools.py`, `agentphone_client.py`, `outbound.py`, `obs.py`, `anthropic_adapter.py`, `fixtures/law.html`, `fixtures/prompts/*.txt`. If any of these appear in `git diff main`, stop and diagnose.

---

### Task 1: Branch

- [ ] **Step 1:** Create the feature branch:
  ```bash
  git checkout -b feat/dashboard-flagship
  ```

---

### Task 2: RED — write `tests/test_event_bus.py` (5 tests)

- [ ] **Step 1:** Read `tests/test_broadcast.py` and `src/robin/broadcast.py` end-to-end to confirm the `TurnBroadcaster` interface (`subscribe`/`unsubscribe`/`publish`) and the `asyncio_mode` convention used across the suite (`pyproject.toml` or `pytest.ini`).

- [ ] **Step 2:** Create `tests/test_event_bus.py` with the following complete content:

  ```python
  """Tests for EventBus — mirrors test_broadcast.py exactly,
  replacing TurnBroadcaster/TranscriptTurn with EventBus/dict."""
  import asyncio
  import pytest
  from robin.event_bus import EventBus


  @pytest.mark.asyncio
  async def test_subscribe_returns_queue():
      bus = EventBus(maxsize=8)
      q = bus.subscribe()
      assert isinstance(q, asyncio.Queue)
      assert q.maxsize == 8


  @pytest.mark.asyncio
  async def test_two_subscribers_both_receive_event():
      bus = EventBus()
      q1 = bus.subscribe()
      q2 = bus.subscribe()
      await bus.publish_event("citation", {"citations": [{"citation": "Cal § 1570"}]})
      item1 = q1.get_nowait()
      item2 = q2.get_nowait()
      assert item1 == {"event": "citation", "data": {"citations": [{"citation": "Cal § 1570"}]}}
      assert item2 == item1


  @pytest.mark.asyncio
  async def test_unsubscribed_queue_does_not_receive():
      bus = EventBus()
      q = bus.subscribe()
      bus.unsubscribe(q)
      await bus.publish_event("citation", {"citations": []})
      assert q.empty()


  @pytest.mark.asyncio
  async def test_full_queue_drops_event_without_raising():
      bus = EventBus(maxsize=1)
      q = bus.subscribe()
      await bus.publish_event("citation", {"citations": []})  # fills the queue
      # second publish must not raise even though the queue is full
      await bus.publish_event("citation", {"citations": []})
      assert q.qsize() == 1  # only the first item; second was dropped


  @pytest.mark.asyncio
  async def test_publish_event_typed_payload_round_trip():
      bus = EventBus()
      q = bus.subscribe()
      citations = [{"citation": "Cal. Health & Safety Code § 1570",
                    "operative_quote": "cancel at any time",
                    "source_url": "https://example.com"}]
      await bus.publish_event("citation", {"citations": citations})
      item = q.get_nowait()
      assert item == {"event": "citation", "data": {"citations": citations}}
  ```

- [ ] **Step 3:** Run the tests — expect 5 failures (`ModuleNotFoundError` or `ImportError` — `EventBus` does not exist yet). This is the RED state:
  ```bash
  docker compose run --rm robin pytest -q tests/test_event_bus.py
  ```
  Expected output: 5 errors/failures.

- [ ] **Step 4:** Commit the RED tests:
  ```bash
  git add tests/test_event_bus.py
  git commit -m "test: RED test_event_bus (EventBus not yet implemented)"
  ```

---

### Task 3: GREEN — implement `src/robin/event_bus.py`

- [ ] **Step 1:** Create `src/robin/event_bus.py` with the following complete content:

  ```python
  """Event bus for typed sponsor events (citation, memory, mail_draft, ...).

  Duck-typed to the W0 event_bus contract:
    subscribe() -> asyncio.Queue   (items: {"event": str, "data": dict})
    unsubscribe(q: asyncio.Queue) -> None
    async publish_event(event: str, data: dict) -> None

  Mirrors TurnBroadcaster mechanics exactly:
    - bounded queue (maxsize=64 default)
    - put_nowait; drop on full, never block, never raise
    - unsubscribe is idempotent
  """
  import asyncio


  class EventBus:
      def __init__(self, maxsize: int = 64) -> None:
          self._maxsize = maxsize
          self._queues: list[asyncio.Queue] = []

      def subscribe(self) -> asyncio.Queue:
          """Return a new bounded queue that will receive future events."""
          q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
          self._queues.append(q)
          return q

      def unsubscribe(self, q: asyncio.Queue) -> None:
          """Remove a queue; idempotent."""
          try:
              self._queues.remove(q)
          except ValueError:
              pass

      async def publish_event(self, event: str, data: dict) -> None:
          """Fan out {"event": event, "data": data} to every subscriber. Drop on full."""
          item = {"event": event, "data": data}
          for q in list(self._queues):
              try:
                  q.put_nowait(item)
              except asyncio.QueueFull:
                  pass  # slow consumer — drop, do not block
  ```

- [ ] **Step 2:** Run `test_event_bus.py` — expect 5 passes:
  ```bash
  docker compose run --rm robin pytest -q tests/test_event_bus.py
  ```
  Expected output: `5 passed`.

- [ ] **Step 3:** Run the full suite — must be green:
  ```bash
  docker compose run --rm robin pytest -q
  ```
  Expected output: all existing tests pass plus the 5 new ones.

- [ ] **Step 4:** Run ruff — must be clean:
  ```bash
  docker compose run --rm robin ruff check src tests
  ```
  Expected output: no errors.

- [ ] **Step 5:** Commit:
  ```bash
  git add src/robin/event_bus.py
  git commit -m "feat: add EventBus (mirrors TurnBroadcaster, typed events)"
  ```

---

### Task 4: RED — `tests/test_dashboard_wiring.py` Group A + file-content tests 3–4

- [ ] **Step 1:** Read `tests/test_stage.py` end-to-end to understand the `_make_app` fixture pattern and how `TestClient` is used. Confirm the exact four disclosure strings asserted by `test_stage_page_contains_integrity_disclosure_verbatim`. Read `src/robin/stage.py` to confirm `make_stage_router(broadcaster, *, event_bus=None, stage_html=None)` signature and `_STAGE_HTML` string.

- [ ] **Step 2:** Create `tests/test_dashboard_wiring.py` with Group A (tests 1–2) and the file-content tests (3–4). Full content for this step:

  ```python
  """Dashboard wiring tests — W4 flag-off/flag-on.

  Group A — flag-off: original HTML and disclosure banner preserved.
  Group B (tests 3–4 this step) — dashboard HTML file-content assertions.
  Group B (tests 5–9 later) — integration wiring (added in Task 6).
  """
  import asyncio
  import pathlib
  import pytest
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  from robin.stage import _STAGE_HTML, make_stage_router
  from robin.broadcast import TurnBroadcaster
  from robin.event_bus import EventBus

  _DASHBOARD_PATH = pathlib.Path("src/robin/fixtures/stage_dashboard.html")

  _DISCLOSURE_STRINGS = [
      "CONTROLLED DEMO",
      "Robin's side is fully live.",
      "a briefed teammate",
      "no real business is called.",
  ]


  def _make_app_flagoff():
      """Minimal app with make_stage_router using defaults (flag-off behaviour)."""
      broadcaster = TurnBroadcaster()
      app = FastAPI()
      app.include_router(make_stage_router(broadcaster))
      return app


  # --- Group A: flag-off ---

  def test_flagoff_stage_serves_original_html():
      """GET /stage with flag off returns byte-identical _STAGE_HTML."""
      client = TestClient(_make_app_flagoff())
      resp = client.get("/stage")
      assert resp.status_code == 200
      assert resp.text == _STAGE_HTML


  def test_flagoff_existing_test_stage_suite_still_passes():
      """Disclosure banner strings present in flag-off /stage response."""
      client = TestClient(_make_app_flagoff())
      resp = client.get("/stage")
      for s in _DISCLOSURE_STRINGS:
          assert s in resp.text, f"Missing disclosure string in flag-off HTML: {s!r}"


  # --- Group B tests 3–4: dashboard HTML file-content (no server needed) ---

  def test_dashboard_html_contains_disclosure_banner():
      """stage_dashboard.html must contain all four disclosure strings."""
      html = _DASHBOARD_PATH.read_text(encoding="utf-8")
      for s in _DISCLOSURE_STRINGS:
          assert s in html, f"Missing disclosure string in dashboard HTML: {s!r}"


  def test_dashboard_html_contains_placeholder_text():
      """stage_dashboard.html must contain all three sponsor placeholder strings."""
      html = _DASHBOARD_PATH.read_text(encoding="utf-8")
      assert "Moss legal citation will appear here" in html
      assert "Super Memory recall will appear here" in html
      assert "Agent Mail confirmation draft will appear here" in html
  ```

- [ ] **Step 3:** Run the tests — expect Group A to pass, tests 3–4 to fail with `FileNotFoundError` (dashboard HTML does not exist yet). This is the RED state:
  ```bash
  docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
  ```
  Expected output: 2 passed (Group A), 2 errors (tests 3–4 — file not found).

- [ ] **Step 4:** Commit the RED tests:
  ```bash
  git add tests/test_dashboard_wiring.py
  git commit -m "test: RED dashboard HTML file-content assertions"
  ```

---

### Task 5: GREEN — write `src/robin/fixtures/stage_dashboard.html`

- [ ] **Step 1:** Confirm `src/robin/fixtures/` directory exists (it contains `law.html` and `prompts/`). Create `src/robin/fixtures/stage_dashboard.html` with the following complete content. Requirements that must all be satisfied:

  **Mandatory disclosure banner** (four tested strings, verbatim, red background, white bold text, fixed top):
  - `"CONTROLLED DEMO"`
  - `"Robin's side is fully live."`
  - `"a briefed teammate"`
  - `"no real business is called."`

  **Three mandatory placeholder strings** (tested by test 4):
  - Moss panel: `"Moss legal citation will appear here when Browser Use completes the statute search."`
  - Memory panel: `"Super Memory recall will appear here when caller history is loaded."`
  - Mail panel: `"Agent Mail confirmation draft will appear here after outcome is delivered."`

  **Panel layout and SSE event mapping:**

  | Panel | Position | SSE event | Accent colour |
  |---|---|---|---|
  | Live Transcript | top-left | `turn` (existing TurnBroadcaster) | white (`#f0f0f0`) |
  | Super Memory Recall | top-right | `memory` | `#8b5cf6` (purple) |
  | Moss Legal Citation | bottom-left | `citation` | `#3b82f6` (blue) |
  | Agent Mail Draft | bottom-right | `mail_draft` | `#f59e0b` (amber) |

  **Full self-contained HTML** (no CDN, no external fonts, no external JS, everything inline):

  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Robin — Live Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0a0a0a;
      color: #f0f0f0;
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 14px;
      padding-top: 52px;
    }
    #banner {
      position: fixed;
      top: 0; left: 0; right: 0;
      background: #b91c1c;
      color: #fff;
      font-weight: bold;
      font-size: 13px;
      padding: 10px 16px;
      z-index: 999;
      text-align: center;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: auto auto;
      gap: 12px;
      padding: 12px;
      height: calc(100vh - 52px);
    }
    @media (max-width: 700px) {
      .grid { grid-template-columns: 1fr; }
    }
    .panel {
      background: #111;
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border-top: 3px solid transparent;
    }
    .panel-transcript { border-top-color: #f0f0f0; }
    .panel-memory     { border-top-color: #8b5cf6; }
    .panel-citation   { border-top-color: #3b82f6; }
    .panel-mail       { border-top-color: #f59e0b; }
    .panel-header {
      padding: 10px 14px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      border-bottom: 1px solid #222;
    }
    .panel-transcript .panel-header { color: #f0f0f0; }
    .panel-memory     .panel-header { color: #8b5cf6; }
    .panel-citation   .panel-header { color: #3b82f6; }
    .panel-mail       .panel-header { color: #f59e0b; }
    .panel-body {
      flex: 1;
      overflow-y: auto;
      padding: 12px 14px;
    }
    .turn { margin-bottom: 6px; line-height: 1.5; }
    .turn.agent { color: #60a5fa; }
    .turn.user  { color: #a3e635; }
    .placeholder {
      color: #555;
      font-style: italic;
      margin-top: 8px;
    }
    .citation-block {
      margin-bottom: 12px;
      border-left: 3px solid #3b82f6;
      padding-left: 10px;
    }
    .citation-block .statute { font-weight: 700; color: #93c5fd; font-size: 13px; }
    .citation-block .quote   { color: #cbd5e1; margin: 4px 0; }
    .citation-block a        { color: #60a5fa; font-size: 11px; }
    .mail-summary   { color: #fde68a; font-weight: 600; margin-bottom: 8px; }
    .mail-confirm   { color: #a3e635; font-size: 13px; }
    .memory-recall  { color: #c4b5fd; line-height: 1.6; }
  </style>
  </head>
  <body>

  <div id="banner">
    CONTROLLED DEMO &mdash; Robin's side is fully live. The receptionist
    runs in a safe test environment (a briefed teammate); no real business is called.
  </div>

  <div class="grid">

    <!-- Transcript panel (top-left) -->
    <div class="panel panel-transcript">
      <div class="panel-header">Live Transcript</div>
      <div class="panel-body" id="transcript-body"></div>
    </div>

    <!-- Super Memory panel (top-right) -->
    <div class="panel panel-memory">
      <div class="panel-header">Super Memory Recall</div>
      <div class="panel-body" id="memory-body">
        <p class="placeholder">Super Memory recall will appear here when caller history is loaded.</p>
      </div>
    </div>

    <!-- Moss Citation panel (bottom-left) -->
    <div class="panel panel-citation">
      <div class="panel-header">Moss Legal Citation</div>
      <div class="panel-body" id="citation-body">
        <p class="placeholder">Moss legal citation will appear here when Browser Use completes the statute search.</p>
      </div>
    </div>

    <!-- Agent Mail panel (bottom-right) -->
    <div class="panel panel-mail">
      <div class="panel-header">Agent Mail</div>
      <div class="panel-body" id="mail-body">
        <p class="placeholder">Agent Mail confirmation draft will appear here after outcome is delivered.</p>
      </div>
    </div>

  </div>

  <script>
  (function () {
    var es = new EventSource('/stage/stream');

    es.addEventListener('turn', function (e) {
      var data = JSON.parse(e.data);
      var div = document.createElement('div');
      div.className = 'turn ' + (data.role === 'agent' ? 'agent' : 'user');
      div.textContent = (data.role === 'agent' ? 'Robin: ' : 'Caller: ') + (data.text || '');
      var body = document.getElementById('transcript-body');
      body.appendChild(div);
      div.scrollIntoView({behavior: 'smooth'});
    });

    es.addEventListener('citation', function (e) {
      var data = JSON.parse(e.data);
      var body = document.getElementById('citation-body');
      body.innerHTML = '';
      (data.citations || []).forEach(function (c) {
        var block = document.createElement('div');
        block.className = 'citation-block';
        block.innerHTML =
          '<div class="statute">' + esc(c.citation || '') + '</div>' +
          '<div class="quote">' + esc(c.operative_quote || '') + '</div>' +
          (c.source_url ? '<a href="' + esc(c.source_url) + '" target="_blank">source</a>' : '');
        body.appendChild(block);
      });
      if (!data.citations || data.citations.length === 0) {
        body.innerHTML = '<p class="placeholder">No citations received.</p>';
      }
    });

    es.addEventListener('memory', function (e) {
      var data = JSON.parse(e.data);
      var body = document.getElementById('memory-body');
      body.innerHTML = '<div class="memory-recall">' + esc(data.recall || data.summary || '') + '</div>';
    });

    es.addEventListener('mail_draft', function (e) {
      var data = JSON.parse(e.data);
      var body = document.getElementById('mail-body');
      body.innerHTML =
        '<div class="mail-summary">' + esc(data.summary || '') + '</div>' +
        (data.confirmation ? '<div class="mail-confirm">Confirmation: ' + esc(data.confirmation) + '</div>' : '');
    });

    es.onerror = function () {
      /* EventSource auto-reconnects on error — no action needed */
    };

    function esc(s) {
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }
  }());
  </script>

  </body>
  </html>
  ```

- [ ] **Step 2:** Run the dashboard wiring tests — expect all 4 to pass now:
  ```bash
  docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
  ```
  Expected output: `4 passed`.

- [ ] **Step 3:** Run the full suite — must stay green:
  ```bash
  docker compose run --rm robin pytest -q
  ```

- [ ] **Step 4:** Run ruff — must be clean (HTML is not linted):
  ```bash
  docker compose run --rm robin ruff check src tests
  ```

- [ ] **Step 5:** Commit:
  ```bash
  git add src/robin/fixtures/stage_dashboard.html
  git commit -m "feat: add stage_dashboard.html (four-panel, disclosure banner, sponsor placeholders)"
  ```

---

### Task 6: RED — remaining `tests/test_dashboard_wiring.py` tests (5–9)

- [ ] **Step 1:** Read `src/robin/main.py` end-to-end to locate: (a) the `_hooks = ExtensionHooks()` line and `>>> W4 dashboard wiring <<<` marker, (b) the `app = build_app(...)` call and the `>>> W4 stage mount <<<` marker location immediately after it, (c) the `_place` closure (lines ~39–48) and the `make_place_negotiation_call(...)` call. Read `src/robin/outbound.py` to confirm `make_place_negotiation_call` accepts `on_turn`. Read `src/robin/app.py` (post-W0) to confirm `build_app` exposes only `hooks` (NOT `stage_html`/`event_bus`).

- [ ] **Step 2:** Add tests 5–9 to `tests/test_dashboard_wiring.py`. Append the following to the existing file:

  ```python
  # --- Group B tests 5–9: flag-on integration wiring ---

  def _make_app_flagons():
      """Minimal flag-on app: EventBus + dashboard HTML + stage router mounted.
      Does NOT import main.py (avoids production side-effects).
      Mirrors the composition main.py does under ROBIN_DASHBOARD_ENHANCED=1.
      """
      broadcaster = TurnBroadcaster()
      bus = EventBus()
      dashboard_html = _DASHBOARD_PATH.read_text(encoding="utf-8")
      app = FastAPI()
      from robin.stage import make_stage_router
      app.include_router(make_stage_router(broadcaster, event_bus=bus, stage_html=dashboard_html))
      return app, bus


  def test_flagons_stage_serves_dashboard_html():
      """GET /stage with flag-on config returns the dashboard HTML."""
      app, _bus = _make_app_flagons()
      client = TestClient(app)
      resp = client.get("/stage")
      assert resp.status_code == 200
      assert "Moss legal citation will appear here" in resp.text


  @pytest.mark.asyncio
  async def test_citation_hook_publishes_citation_event():
      """_citation_pub hook publishes the correct citation event to the bus."""
      bus = EventBus()
      q = bus.subscribe()

      async def _citation_pub(call_id, out_dict):
          try:
              await bus.publish_event("citation", {
                  "call_id": call_id,
                  "citations": out_dict.get("citations", []),
              })
          except Exception:
              pass

      citations = [{"citation": "Cal § 1570",
                    "operative_quote": "cancel at any time",
                    "source_url": "https://example.com"}]
      await _citation_pub(call_id="c1", out_dict={"status": "OK", "citations": citations})
      item = q.get_nowait()
      assert item == {
          "event": "citation",
          "data": {"call_id": "c1", "citations": citations},
      }


  @pytest.mark.asyncio
  async def test_mail_hook_publishes_mail_draft_event():
      """_mail_pub hook publishes the correct mail_draft event to the bus."""
      bus = EventBus()
      q = bus.subscribe()

      async def _mail_pub(call_id, payload):
          try:
              await bus.publish_event("mail_draft", {
                  "call_id": call_id,
                  "summary": payload.get("summary", ""),
                  "confirmation": payload.get("confirmation"),
                  "channel": payload.get("channel"),
              })
          except Exception:
              pass

      payload = {"summary": "cancelled + last-month refund",
                 "confirmation": "24HF-4471", "channel": "voice",
                 "out": {"delivered": True}}
      await _mail_pub(call_id="c2", payload=payload)
      item = q.get_nowait()
      assert item == {
          "event": "mail_draft",
          "data": {"call_id": "c2",
                   "summary": "cancelled + last-month refund",
                   "confirmation": "24HF-4471",
                   "channel": "voice"},
      }


  @pytest.mark.asyncio
  async def test_sse_emits_citation_event_after_hook_fires():
      """SSE stream emits a citation event chunk when one is published to the bus."""
      bus = EventBus()
      broadcaster = TurnBroadcaster()
      dashboard_html = _DASHBOARD_PATH.read_text(encoding="utf-8")
      app = FastAPI()
      from robin.stage import make_stage_router
      app.include_router(make_stage_router(broadcaster, event_bus=bus, stage_html=dashboard_html))

      await bus.publish_event("citation", {"citations": []})

      client = TestClient(app)
      with client.stream("GET", "/stage/stream") as resp:
          body = b""
          for chunk in resp.iter_bytes():
              body += chunk
              if b"event: citation" in body:
                  break
      assert b"event: citation" in body


  def test_memory_panel_placeholder_present_when_no_memory_event():
      """Dashboard HTML contains the Super Memory placeholder (no event needed)."""
      html = _DASHBOARD_PATH.read_text(encoding="utf-8")
      assert "Super Memory recall will appear here" in html
  ```

- [ ] **Step 3:** Run the wiring tests — expect tests 5–8 to fail (hooks not wired in main yet; test 9 passes as static file assertion). This is the RED state:
  ```bash
  docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
  ```
  Expected output: tests 1–4 pass, test 9 passes, tests 5–8 fail.

- [ ] **Step 4:** Commit the RED tests:
  ```bash
  git add tests/test_dashboard_wiring.py
  git commit -m "test: RED dashboard wiring integration tests"
  ```

---

### Task 7: GREEN — wire W4 sub-block in `main.py` + append `fakes.py` + `.env.example`

- [ ] **Step 1:** Open `src/robin/main.py`. Locate the line `# >>> W4 dashboard wiring <<<`. Insert the following sub-block immediately after that comment line (replacing it — keep the comment as the opening label):

  **Insertion A — inside `# --- sponsor extension wiring ---` section (before `app = build_app(...)`):**

  ```python
  # >>> W4 dashboard wiring <<<
  if os.environ.get("ROBIN_DASHBOARD_ENHANCED") == "1":
      import pathlib as _pathlib
      from robin.broadcast import TurnBroadcaster
      from robin.event_bus import EventBus

      _bus = EventBus()
      _broadcaster = TurnBroadcaster()           # transcript fan-out target
      _dashboard_html = _pathlib.Path(
          "src/robin/fixtures/stage_dashboard.html").read_text(encoding="utf-8")

      async def _citation_pub(call_id, out_dict):      # on_research hook
          try:
              await _bus.publish_event("citation", {
                  "call_id": call_id,
                  "citations": out_dict.get("citations", []),
              })
          except Exception:
              pass  # hook must never raise

      async def _mail_pub(call_id, payload):           # on_outcome hook
          try:
              await _bus.publish_event("mail_draft", {
                  "call_id": call_id,
                  "summary": payload.get("summary", ""),
                  "confirmation": payload.get("confirmation"),
                  "channel": payload.get("channel"),
              })
          except Exception:
              pass  # hook must never raise

      _hooks = ExtensionHooks(
          prompt_enrichers=_hooks.prompt_enrichers,
          on_research=_hooks.on_research + (_citation_pub,),
          on_outcome=_hooks.on_outcome + (_mail_pub,),
          event_bus=_bus,
      )

      # --- OPTIONAL transcript-feed tier (collapse-cut #1; see collapse ladder) ---
      # The citation + mail panels above are pure-W0-event_bus and need NO
      # broadcaster. The TRANSCRIPT panel needs TurnBroadcaster fed by the
      # outbound call's on_turn. main.py:_place builds make_place_negotiation_call
      # WITHOUT on_turn, so feed it by overriding the place tool impl here —
      # same pattern as W3's research override.
      # make_place_negotiation_call already accepts on_turn (outbound.py:59-63).
      from robin.models import Citation as _Cit
      from robin.outbound import make_place_negotiation_call as _mk_place
      from robin.prompts import render_outbound_system_prompt as _ros

      async def _place_with_turns(phone, member_name, citations):
          _cites = [_Cit(c.get("citation", ""), c.get("operative_quote", ""),
                         c.get("source_url", "")) for c in citations]
          _impl = _mk_place(
              client=_ap, registry=_registry,
              agent_id=_settings.robin_agent_id,
              from_number_id=_settings.from_number_id,
              receptionist_to_number=_settings.receptionist_to_number,
              outbound_system_prompt=_ros(_pack, _cites),
              on_turn=_broadcaster.publish)
          return await _impl(phone=phone, member_name=member_name,
                             citations=citations)

      _tool_impls["place_negotiation_call"] = _place_with_turns
      # --- end optional transcript-feed tier ---
  # >>> end W4 dashboard wiring <<<
  ```

  **Critical:** Do NOT pass `stage_html` or `event_bus` to `build_app(...)`. W0 only added `hooks` to `build_app`. The `app = build_app(...)` line is unchanged from W0.

- [ ] **Step 2:** Locate the `app = build_app(...)` call in `main.py`. Immediately after the closing `)` of that call, insert **Insertion B**:

  ```python
  # >>> W4 stage mount <<<
  if os.environ.get("ROBIN_DASHBOARD_ENHANCED") == "1":
      from robin.stage import make_stage_router
      app.include_router(make_stage_router(
          _broadcaster, event_bus=_bus, stage_html=_dashboard_html))
  # >>> end W4 stage mount <<<
  ```

  This is where `app` exists and the W0-parametrized router gets mounted. W0 deliberately left the mount to W4.

- [ ] **Step 3:** Open `tests/fakes.py`. Append the following labeled block at the end (do not touch existing content):

  ```python
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
  ```

  Note: `fakes.py` likely already imports `asyncio` for `FakeBroadcaster`. If not, add `import asyncio` at the top of the appended block only if not already present at module level.

- [ ] **Step 4:** Open `.env.example`. Append the following labeled block at the end:

  ```
  # W4 — Dashboard Flagship
  ROBIN_DASHBOARD_ENHANCED=
  ```

- [ ] **Step 5:** Run all dashboard wiring tests — expect all 9 to pass:
  ```bash
  docker compose run --rm robin pytest -q tests/test_event_bus.py tests/test_dashboard_wiring.py
  ```
  Expected output: `14 passed` (5 event bus + 9 wiring).

- [ ] **Step 6:** Run the full suite — must be green:
  ```bash
  docker compose run --rm robin pytest -q
  ```

- [ ] **Step 7:** Run ruff — must be clean:
  ```bash
  docker compose run --rm robin ruff check src tests
  ```

- [ ] **Step 8:** Commit:
  ```bash
  git add src/robin/main.py tests/fakes.py .env.example
  git commit -m "feat: wire W4 dashboard (EventBus + hooks + flag-gated main.py block)"
  ```

---

### Task 8: REFACTOR

- [ ] **Step 1:** Review `src/robin/event_bus.py` for clarity — ensure the docstring, method names, and comments are precise. No behavior changes.

- [ ] **Step 2:** Review the hook closures `_citation_pub` and `_mail_pub` in the `main.py` W4 sub-block — confirm the `try/except Exception: pass` guards are present in both and the payload shapes match the spec.

- [ ] **Step 3:** Check `src/robin/fixtures/stage_dashboard.html` — verify no duplicate CSS rules, no stale placeholder that was accidentally removed. Confirm the `esc()` helper is applied consistently to all user-controlled strings rendered into the DOM.

- [ ] **Step 4:** Verify `FakeEventBus` in `tests/fakes.py` is clean — `published` list correctly stores every item; `subscribe`/`unsubscribe` mirror `EventBus` exactly.

- [ ] **Step 5:** Run the full suite and ruff throughout refactor — tests must remain green:
  ```bash
  docker compose run --rm robin pytest -q
  docker compose run --rm robin ruff check src tests
  ```

- [ ] **Step 6:** Commit if any changes were made:
  ```bash
  git add src/robin/event_bus.py src/robin/fixtures/stage_dashboard.html src/robin/main.py tests/fakes.py
  git commit -m "refactor: W4 cleanup — event_bus, dashboard hooks, fakes"
  ```

---

### Task 9: Manual browser check

- [ ] **Step 1:** Start the server with the dashboard flag enabled:
  ```bash
  ROBIN_DASHBOARD_ENHANCED=1 docker compose up robin
  ```

- [ ] **Step 2:** Open `http://localhost:8000/stage` in a browser. Verify all of the following:
  - [ ] Four-panel grid is visible (transcript top-left, Super Memory top-right, Moss bottom-left, Agent Mail bottom-right).
  - [ ] Disclosure banner present at the top with red background, white bold text, and all four disclosure strings visible.
  - [ ] All three sponsor placeholder texts are visible in their panels (Moss, Super Memory, Agent Mail).
  - [ ] `EventSource` connects to `/stage/stream` — check browser DevTools → Network → EventStream tab, confirm the connection is established and heartbeat events arrive.
  - [ ] No JavaScript console errors.

- [ ] **Step 3:** Stop the server (`Ctrl+C`). Start without the flag:
  ```bash
  docker compose up robin
  ```

- [ ] **Step 4:** Open `http://localhost:8000/stage` in a browser. Verify:
  - [ ] The **original** single-column transcript page is served (not the four-panel dashboard).
  - [ ] The original disclosure banner text is present.

---

### Task 10: Coverage check

- [ ] **Step 1:** Run coverage on the new modules:
  ```bash
  docker compose run --rm robin pytest --cov=src/robin/event_bus --cov=src/robin --cov-report=term-missing -q tests/test_event_bus.py tests/test_dashboard_wiring.py
  ```
  Target: ≥ 80% on `event_bus.py` and the hook closures reachable via `test_dashboard_wiring.py`. The dashboard HTML is not Python and is excluded from coverage.

- [ ] **Step 2:** If coverage is below 80% on `event_bus.py`, add a targeted test for the uncovered branch (likely the multi-subscriber drop path). Do not lower the target.

---

### Task 11: Flag-off regression gate (mandatory before PR)

- [ ] **Step 1:** Run the flag-off regression gate — both existing test files must pass without modification:
  ```bash
  docker compose run --rm robin pytest -q tests/test_stage.py tests/test_broadcast.py
  ```
  Expected: all existing tests in both files pass. If either fails, stop and diagnose before merging.

- [ ] **Step 2:** Run the full suite with the flag explicitly off:
  ```bash
  docker compose run --rm robin pytest -q
  ```
  Expected: all tests green.

- [ ] **Step 3:** Run the full suite with the flag explicitly set to `"0"` (not `"1"`) — must also be green:
  ```bash
  ROBIN_DASHBOARD_ENHANCED=0 docker compose run --rm robin pytest -q
  ```

- [ ] **Step 4:** Verify `git diff main` shows ONLY the expected new files and `main.py` W4 sub-blocks. If any of the locked files appear (`loop.py`, `stage.py`, `app.py`, `classifier.py`, `signature.py`, `models.py`, `extensions.py`, `broadcast.py`, `config.py`, `context_pack.py`, `prompts.py`, `tools.py`, `agentphone_client.py`, `outbound.py`, `obs.py`, `anthropic_adapter.py`, `fixtures/law.html`, `fixtures/prompts/*.txt`), stop and diagnose immediately.

- [ ] **Step 5:** Create the PR:
  ```bash
  git push -u origin feat/dashboard-flagship
  ```
  Then open the PR targeting `main`. Title: `feat: W4 dashboard flagship (EventBus, four-panel SSE dashboard, citation + mail hooks)`.

---

## Collapse Ladder

If the clock runs out, cut in this exact order (isolation cleanliness drives the order — the transcript-feed tier is the only part that reaches outside the pure-W0-event_bus contract):

1. **First cut — drop the optional transcript-feed tier.** Remove the `_place_with_turns` override and the `_tool_impls["place_negotiation_call"] = _place_with_turns` line entirely. Keep `TurnBroadcaster()` instantiated (unfed) so `make_stage_router` still mounts and `/stage/stream` SSE serves the event_bus events; the transcript panel shows its placeholder. This returns W4 to a **pure-W0-event_bus, fully isolated** branch — no `_tool_impls` override, no outbound rewire. Citation + mail panels still fill live. **This is the recommended minimal shippable W4.**

2. **Second cut — memory panel.** Remove the `memory` SSE listener from `stage_dashboard.html` (or leave it — it is harmless). The panel becomes a permanent styled placeholder. The string `"Super Memory recall will appear here"` stays in the HTML so file-content tests are unchanged.

3. **Third cut — mail draft panel.** Remove `_mail_pub` hook and the `mail_draft` SSE listener. Register only `_citation_pub`. Citation panel still fills in real time — Moss data appearing before the dial is the single highest-wow moment and the $10K-track tie-in.

4. **Last cut — do not merge.** If the citation panel is not green by T+2:30, leave the branch unmerged and demo from `main`. Costs nothing — the canonical demo is unchanged and `/stage` is unmounted exactly as today.

---

## Notes

- **Flag-off is byte-identical to today.** With `ROBIN_DASHBOARD_ENHANCED` unset, neither W4 `main.py` insertion runs. `/stage` stays unmounted (404). `test_stage.py` and `test_broadcast.py` must pass untouched — this is the mandatory final gate.
- **Do NOT pass `stage_html` or `event_bus` to `build_app`.** W0 only added `hooks` to `build_app`. The stage router is mounted separately via `app.include_router(...)` **after** `app = build_app(...)`. This is the corrected two-insertion architecture.
- **No edits to `app.py` or `stage.py`.** All wiring is composed in the `main.py` W4 sub-block only.
- **`make_stage_router` is not called anywhere today** — W4 owns ALL projector wiring. The premise "add panels to the already-live /stage" is false; W4 creates the live `/stage` for the first time.
- **Security:** `stage_dashboard.html` contains no hardcoded secrets. Transcript shown during the demo is the controlled gym-cancel demo only. `context_pack.json` is gitignored. Tests use synthetic data only (`call_id="test-call-001"`, `+1555…` numbers, citation text from the verified law corpus).
