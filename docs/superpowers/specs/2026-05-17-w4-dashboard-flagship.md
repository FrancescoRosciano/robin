# W4 — Dashboard Flagship

**Branch:** `feat/dashboard-flagship`
**Size:** M–L. Minimal tier (citation + mail panels + dashboard HTML +
router mount, pure-W0-event_bus, fully isolated) ≈ 2 h. Optional
transcript-feed tier (+ `TurnBroadcaster` + `_place_with_turns`
override) ≈ +1 h. **The original "~3 h, reuses 70 % existing infra"
estimate assumed `/stage` was already mounted — it is NOT (see §2.3
ground-truth note); W4 owns all projector wiring.**
**Depends on:** W0 (`feat/extension-seam`) merged to `main` — no other branches required.
**Flag:** `ROBIN_DASHBOARD_ENHANCED=1`

---

## 1. Goal

Replace the existing single-column transcript projector page with a four-panel live dashboard that shows, on one screen visible to judges throughout the demo, the live negotiation transcript AND three sponsor integration panels (Moss legal citation, Super Memory recall, Agent Mail draft artifact) filling in in real time from SSE events. The dashboard degrades gracefully: each sponsor panel shows a designed placeholder when its event has not yet arrived, so a missing sponsor SDK or absent W1/W2/W3 branch is a cosmetic gap, never a break.

The canonical demo path (flag absent) is untouched. Every existing test passes. This branch adds only new files and a delimited `main.py` sub-block.

---

## 2. Orientation

### 2.1 Portfolio fit

The master design (`docs/superpowers/specs/2026-05-17-robin-sponsor-extensions-design.md`) defines W4 as the visual flagship. It sits at position 4 in the deadline-collapse priority ladder: W0 → W3 → W4 → W1 → W2. W4 makes all three sponsor integrations legible in one projector view, regardless of which of W1/W2/W3 are actually merged.

### 2.2 Isolation contract

From §2 of the master design — this branch obeys every point:

1. `ROBIN_DASHBOARD_ENHANCED` absent ⇒ no-op, byte-identical to pre-W4 `main`. Existing `test_stage.py` passes untouched.
2. Missing SDK / bus error ⇒ graceful no-op. Hooks must not raise into the call turn.
3. All new code in new files: `src/robin/event_bus.py`, `src/robin/fixtures/stage_dashboard.html`, `tests/test_event_bus.py`, `tests/test_dashboard_wiring.py`. No edits to `loop.py`, `stage.py`, `app.py`, `classifier.py`, `signature.py`, `models.py`, or any locked fixture.
4. Constructor injection + fake pattern. `EventBus` is tested against a `FakeEventBus`-compatible interface; `tests/fakes.py` gains a `FakeEventBus` appended in a labeled block.
5. Time-box + collapse ladder (§8 below).
6. No secrets in dashboard HTML; synthetic data in tests; transcript shown on stage is the controlled demo only.

### 2.3 W0 parametrized-router API (restated — self-contained)

W0 made the following changes that W4 depends on:

**`src/robin/extensions.py`** (added by W0) — the frozen dataclass:

```python
@dataclass(frozen=True)
class ExtensionHooks:
    prompt_enrichers: tuple[PromptEnricher, ...] = ()
    on_research: tuple[ResearchHook, ...] = ()
    on_outcome: tuple[OutcomeHook, ...] = ()
    event_bus: object | None = None  # duck-typed; W4 supplies
```

`ExtensionHooks()` (all fields defaulted) is exactly today's behaviour.

**W0 parametrized `build_app` (in `app.py`) and `make_stage_router` (in `stage.py`):**

- `build_app(*, secret, law_html_path, llm, tool_impls, system_prompt, hooks: ExtensionHooks = ExtensionHooks())` — threads `hooks` into `run_turn`. **W0 adds ONLY the `hooks` parameter.** W0 does **not** add `stage_html`/`event_bus` to `build_app`, and W0 does **not** mount the stage router.
- `make_stage_router(broadcaster, *, event_bus=None, stage_html: str | None = None) -> APIRouter` (in `src/robin/stage.py`) — when `event_bus` is not None, its queue items (`{"event": str, "data": dict}`) are drained into the SSE stream alongside `turn` events; when `stage_html` is not None it is served at `GET /stage` instead of `_STAGE_HTML`. Defaults preserve behaviour byte-for-byte (existing `tests/test_stage.py`, which exercises `make_stage_router` directly, stays green).

> **GROUND-TRUTH REALITY — read `main.py` and `app.py` end to end and confirm before writing code:**
> `make_stage_router` is **never called in `main.py` or `build_app`** today, and `TurnBroadcaster` is **never instantiated or fed**. The `/stage` route is therefore **not mounted in the running app** right now — only `tests/test_stage.py` exercises `make_stage_router` directly. The flagship premise "add panels to the already-live /stage" is **false**. Consequently **W4 owns ALL of the projector wiring** in its `main.py` `>>> W4 <<<` sub-block:
> 1. construct a `TurnBroadcaster()` (from `robin.broadcast`);
> 2. feed it — pass `on_turn=_broadcaster.publish` into the outbound-call factory so negotiation turns reach the transcript panel (see §6.3 for the exact `_place` seam);
> 3. construct the `EventBus()`;
> 4. `app.include_router(make_stage_router(_broadcaster, event_bus=_bus, stage_html=_dashboard_html))` **after** `app = build_app(...)`.
> With `ROBIN_DASHBOARD_ENHANCED` unset, none of this runs ⇒ `/stage` stays unmounted exactly as today (404) — the required byte-identical no-op. **W4 still must NOT edit `app.py` or `stage.py`** — all of the above is composed in the `main.py` sub-block only.

**`src/robin/main.py`** — W0 added the delimited sponsor wiring section:

```python
# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
# >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
# >>> W4 dashboard wiring   <<<   (added on feat/dashboard-flagship)
# --- end sponsor extension wiring ---
```

and passes `hooks=_hooks` to `build_app(...)`.

**`src/robin/loop.py`** — W0 made `_record_session` async, added a `hooks` parameter, dispatches each `hooks.on_research` item when `name == "research_cancellation_law"` and `out["status"] == "OK"` (payload = full `out` dict with `citations`), and each `hooks.on_outcome` item when `name == "deliver_result"` and `out["delivered"]` (payload = `{"summary": str, "confirmation": str|None, "channel": str|None, "out": dict}`). Each hook is wrapped in `try/except` → `obs.log_event("extension_hook_error", ...)`. Hook contract: must return quickly (< 200 ms), must never raise; schedule long work via `asyncio.create_task` inside the hook.

---

## 3. Exact seams (path : line / location — confirm by reading the working tree)

| Seam | Where | What W4 uses |
|---|---|---|
| `_hooks = ExtensionHooks()` marker | `src/robin/main.py` — the `# >>> W4 dashboard wiring <<<` line in the delimited block | W4 inserts its sub-block here, rebuilding `_hooks` immutably |
| `make_stage_router(broadcaster, *, event_bus=None, stage_html=None)` | `src/robin/stage.py` — the parametrized W0 factory (read it; defaults unchanged) | W4 **calls and mounts this itself** in the `main.py` sub-block: `app.include_router(make_stage_router(_broadcaster, event_bus=_bus, stage_html=_dashboard_html))` — it is NOT mounted today |
| `_place` outbound-call closure | `src/robin/main.py` lines 39–48 (`make_place_negotiation_call(...)` inside `_place`) | W4 must pass `on_turn=_broadcaster.publish` so transcript turns reach the projector. Confirm the `make_place_negotiation_call` signature accepts `on_turn` by reading `src/robin/outbound.py` |
| `build_app(..., hooks=_hooks)` call | `src/robin/main.py` — composition root (currently `main.py:60-63`) | W4's rebuilt `_hooks` is passed via the W0 `hooks=` param. `stage_html`/`event_bus` are **NOT** build_app params — mount the router separately (above) |
| `TurnBroadcaster` mechanics | `src/robin/broadcast.py` (read it; confirm `subscribe`/`unsubscribe`/`publish`) | `EventBus` mirrors this exact pattern (subscribe/unsubscribe/put_nowait/drop-on-full). W4 also *instantiates* a `TurnBroadcaster` for the transcript panel |
| `_STAGE_HTML` inline string | `src/robin/stage.py` lines 16–99 | Dashboard HTML must preserve the disclosure banner text VERBATIM (see §4) |
| Disclosure banner test | `tests/test_stage.py` lines 69–76 (`test_stage_page_contains_integrity_disclosure_verbatim`) | Flag-off ⇒ this test must still pass against the original `_STAGE_HTML`; flag-on ⇒ the dashboard HTML must also satisfy the same assertions |
| `ResearchHook` / `OutcomeHook` signatures | `src/robin/extensions.py` | `async (call_id: str | None, out_dict: dict) -> None` |

---

## 4. Disclosure banner — verbatim requirement

The existing `_STAGE_HTML` in `src/robin/stage.py` (lines 69–71) contains this disclosure banner, which is tested in `tests/test_stage.py:test_stage_page_contains_integrity_disclosure_verbatim`:

```html
<div id="banner">
  CONTROLLED DEMO &mdash; Robin's side is fully live. The receptionist
  runs in a safe test environment (a briefed teammate); no real business is called.
</div>
```

The four strings asserted by the existing test are:

- `"CONTROLLED DEMO"`
- `"Robin's side is fully live."`
- `"a briefed teammate"`
- `"no real business is called."`

**Requirement (non-negotiable):** `src/robin/fixtures/stage_dashboard.html` must contain all four of these strings, in a visible banner at the same top-of-page fixed position, with styling that preserves the red background and white bold text. The banner text may differ slightly in surrounding punctuation or linebreaks from `&mdash;` vs `—`, but the four asserted substrings must be present byte-for-byte.

The `tests/test_dashboard_wiring.py` must include a test that asserts all four strings are present in the dashboard HTML (mirroring the existing `test_stage_page_contains_integrity_disclosure_verbatim` test but targeting the dashboard HTML file directly). This test must pass both in flag-on mode (where the endpoint serves the dashboard) and as a standalone file-content assertion.

---

## 5. Panel ↔ RUNSHEET step mapping

The four panels in the dashboard grid must populate in the following order, matching `docs/RUNSHEET.md`:

| Panel | SSE event type | RUNSHEET step | When it fills |
|---|---|---|---|
| **Live Transcript** | `turn` (existing, from `TurnBroadcaster`) | All steps — starts at Step 1 | Immediately, on every call turn |
| **Super Memory Recall** | `memory` | Step 1–2 (call start, prompt enrichment) | If W1 merged + `ROBIN_MEMORY_ENABLED`: a memory enricher result could be published here. W4-alone: placeholder shown. W4 publishes this event only if a `memory` event arrives on the bus — it does not generate it. If W1 is merged and wires its own memory data onto the bus (via its `main.py` sub-block), the panel fills. Otherwise the placeholder remains. |
| **Moss Legal Citation** | `citation` | Step 2 (Browser Use legal research completes, before dial) | W4's `on_research` hook fires on `research_cancellation_law` completion, publishes `citation` with the `citations` list |
| **Agent Mail Draft** | `mail_draft` | Step 5–6 (ultimatum / capitulation, outcome delivered) | W4's `on_outcome` hook fires on `deliver_result`, publishes `mail_draft` with `summary`, `confirmation`, `channel` |

Note on `memory` panel: W4 does not import, depend on, or hard-code any W1 behaviour. The panel simply listens for a `memory` SSE event. If W1 is merged and its `main.py` sub-block publishes a `memory` event onto the shared `event_bus`, the panel fills. If W1 is absent, the panel shows its placeholder for the full demo. This is explicit in the implementation and in the test (a test asserts that after flag-on wiring with no `memory` event, the memory panel placeholder text is present in the initial HTML).

---

## 6. File specifications

### 6.1 `src/robin/event_bus.py`

Mirror `src/robin/broadcast.py` exactly, replacing the `TranscriptTurn`-typed queue with an `asyncio.Queue` of `dict`. The class is duck-typed to satisfy W0's `event_bus` contract: `subscribe() -> asyncio.Queue`, `unsubscribe(q)`, `async publish_event(event: str, data: dict) -> None`.

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

This is the complete implementation. No external dependencies. 100% testable without telephony.

### 6.2 `src/robin/fixtures/stage_dashboard.html`

Self-contained (no CDN, no external fonts, no external JS — everything inline). Serves as the dashboard at `GET /stage` when `ROBIN_DASHBOARD_ENHANCED=1`.

**Structure:**

- Fixed top banner (red, bold, white) containing the four mandatory disclosure strings (§4).
- CSS grid: `grid-template-columns: 1fr 1fr` on the top row (transcript | super memory), `grid-template-columns: 1fr 1fr` on the bottom row (moss citation | agent mail). On smaller viewports, collapse to a single column.
- One `EventSource('/stage/stream')` — the same endpoint as the existing page. The event bus items are emitted by the W0-parametrized stage router's SSE generator alongside `turn` events, so no endpoint change is needed.
- Event listeners:
  - `turn`: same logic as the existing page — create a `.turn.agent` or `.turn.user` div, append to the transcript panel, scroll into view.
  - `citation`: populate the Moss panel with the `data.citations` array (each citation rendered as `<blockquote>` with `data`, `operative_quote`, `source_url`). Before the event arrives, the Moss panel shows a placeholder: `<p class="placeholder">Moss legal citation will appear here when Browser Use completes the statute search.</p>`.
  - `memory`: populate the Super Memory panel with `data.recall` (or `data.summary`). Before the event arrives, the panel shows: `<p class="placeholder">Super Memory recall will appear here when caller history is loaded.</p>`.
  - `mail_draft`: populate the Agent Mail panel with `data.summary`, `data.confirmation`. Before the event arrives, the panel shows: `<p class="placeholder">Agent Mail confirmation draft will appear here after outcome is delivered.</p>`.
- Styling: consistent with the existing page's dark theme (`#0a0a0a` background, `#f0f0f0` text), panel headers in a distinctive accent colour per sponsor (`#3b82f6` Moss, `#8b5cf6` Super Memory, `#f59e0b` Agent Mail). Each sponsor panel card has a top border in its accent colour.
- No JavaScript framework, no build step, no external requests. Works from the same Docker-served origin.

**Required placeholder text strings** (tested in `tests/test_dashboard_wiring.py`):

- Moss panel: `"Moss legal citation will appear here"`
- Memory panel: `"Super Memory recall will appear here"`
- Mail panel: `"Agent Mail confirmation draft will appear here"`

These strings are asserted to be present in the static dashboard HTML file so the test does not require a running server.

### 6.3 `src/robin/main.py` — W4 wiring (TWO delimited insertions)

W4 makes **two** clearly-labelled, W4-exclusive insertions in `main.py`
(both auto-merge — no other branch touches either location):

**(A) the `>>> W4 dashboard wiring <<<` sub-block** inside the W0
`# --- sponsor extension wiring ---` section (this runs *before*
`app = build_app(...)`, so `app` does not exist here yet — only build
the bus/broadcaster/hooks here):

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

    # --- OPTIONAL transcript-feed tier (collapse-cut #1; see §8) ---
    # The citation + mail panels above are pure-W0-event_bus and need NO
    # broadcaster. The TRANSCRIPT panel needs TurnBroadcaster fed by the
    # outbound call's on_turn. main.py:_place (lines 39-48) builds
    # make_place_negotiation_call WITHOUT on_turn, so feed it by overriding
    # the place tool impl here — same pattern as W3's research override.
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

The `app = build_app(...)` line is unchanged from W0 — it already takes
`hooks=_hooks`. **Do NOT pass `stage_html`/`event_bus` to `build_app`**
(W0 did not add those; W0 only added `hooks`).

**(B) the `>>> W4 stage mount <<<` line immediately AFTER
`app = build_app(...)`** (this is where `app` exists and the
W0-parametrized router gets mounted — W0 deliberately left the mount to
W4 because `/stage` is not mounted today):

```python
app = build_app(                                  # <-- existing W0 line, unchanged
    secret=_settings.agentphone_webhook_secret,
    law_html_path=LAW_HTML_PATH, llm=_llm, tool_impls=_tool_impls,
    system_prompt=render_inbound_system_prompt(_pack),
    hooks=_hooks)
# >>> W4 stage mount <<<
if os.environ.get("ROBIN_DASHBOARD_ENHANCED") == "1":
    from robin.stage import make_stage_router
    app.include_router(make_stage_router(
        _broadcaster, event_bus=_bus, stage_html=_dashboard_html))
# >>> end W4 stage mount <<<
```

**Verify before writing:** read `src/robin/app.py` (post-W0) to confirm
`build_app` exposes only `hooks` (not `stage_html`/`event_bus`), and
`src/robin/stage.py` to confirm `make_stage_router(broadcaster, *,
event_bus=None, stage_html=None)`. **Do NOT edit `app.py` or
`stage.py`.** With the flag unset, neither insertion runs ⇒ `/stage`
stays unmounted (404) exactly as today — the required byte-identical
no-op. Both insertions are W4-exclusive and contiguous-labelled, so git
auto-merges them against W1/W2/W3.

### 6.4 `tests/test_event_bus.py`

Mirror `tests/test_broadcast.py` exactly, replacing `TurnBroadcaster`/`TranscriptTurn` with `EventBus`/`dict`. All three test cases from `test_broadcast.py` must have direct analogues, plus two additional tests:

1. **`test_subscribe_returns_queue`**: `subscribe()` returns an `asyncio.Queue` with correct `maxsize`.
2. **`test_two_subscribers_both_receive_event`** (mirror of `test_broadcast.py:test_two_subscribers_both_receive_published_turn`): two queues both receive the same `{"event": "citation", "data": {...}}` dict.
3. **`test_unsubscribed_queue_does_not_receive`** (mirror of `test_broadcast.py:test_unsubscribed_queue_does_not_receive`).
4. **`test_full_queue_drops_event_without_raising`** (mirror of `test_broadcast.py:test_full_queue_drops_turn_without_raising`): full queue drops silently; no exception.
5. **`test_publish_event_typed_payload_round_trip`**: publish `event="citation"`, `data={"citations": [{"citation": "Cal. Health & Safety Code § 1570"}]}` → dequeue → assert item equals `{"event": "citation", "data": {"citations": [...]}}`. Verifies the dict wrapper is constructed correctly.

All tests use `pytest-asyncio` (same `asyncio_mode = "auto"` or `@pytest.mark.asyncio` pattern as the rest of the suite — check `pyproject.toml` or `pytest.ini` for the project convention).

### 6.5 `tests/test_dashboard_wiring.py`

Two test groups:

**Group A — flag-off (no env var):**

1. **`test_flagoff_stage_serves_original_html`**: with `ROBIN_DASHBOARD_ENHANCED` unset (or `"0"`), `GET /stage` response text is byte-identical to the `_STAGE_HTML` string imported from `robin.stage`. Uses `TestClient` (same pattern as `test_stage.py`). This proves the existing page is untouched.
2. **`test_flagoff_existing_test_stage_suite_still_passes`**: not a literal re-run of the whole suite, but an explicit assertion that the existing disclosure-banner strings (`"CONTROLLED DEMO"`, `"Robin's side is fully live."`, `"a briefed teammate"`, `"no real business is called."`) are present in the flag-off page response (mirrors `test_stage_page_contains_integrity_disclosure_verbatim`).

**Group B — flag-on (`ROBIN_DASHBOARD_ENHANCED=1`):**

3. **`test_dashboard_html_contains_disclosure_banner`**: read `src/robin/fixtures/stage_dashboard.html` directly from disk and assert all four disclosure strings are present. Standalone file-content assertion — no server needed.
4. **`test_dashboard_html_contains_placeholder_text`**: read the dashboard HTML from disk and assert the three placeholder strings are present (`"Moss legal citation will appear here"`, `"Super Memory recall will appear here"`, `"Agent Mail confirmation draft will appear here"`).
5. **`test_flagons_stage_serves_dashboard_html`**: with `ROBIN_DASHBOARD_ENHANCED=1` patched in environment, build the app via the composition seam (not by importing `main.py` directly — use a test fixture that constructs `EventBus` + reads dashboard HTML + passes to `build_app` / `make_stage_router` with the correct parameters), then `TestClient(app).get("/stage")` → assert response contains `"Moss legal citation will appear here"` (confirming the dashboard HTML is served).
6. **`test_citation_hook_publishes_citation_event`**: construct an `EventBus`, call `_citation_pub(call_id="c1", out_dict={"status": "OK", "citations": [{"citation": "Cal § 1570", "operative_quote": "cancel at any time", "source_url": "https://example.com"}]})`, subscribe before the call, assert the dequeued item equals `{"event": "citation", "data": {"call_id": "c1", "citations": [...]}}`.
7. **`test_mail_hook_publishes_mail_draft_event`**: analogous for `_mail_pub`.
8. **`test_sse_emits_citation_event_after_hook_fires`**: construct `EventBus`, build a minimal `make_stage_router(broadcaster, event_bus=bus)` test app, subscribe, call `bus.publish_event("citation", {"citations": []})`, drain the SSE body iterator → assert a chunk with `event: citation\n` is emitted.
9. **`test_memory_panel_placeholder_present_when_no_memory_event`**: open `stage_dashboard.html` and assert `"Super Memory recall will appear here"` is present — confirming the panel shows the placeholder when no `memory` event has arrived. This is a static file assertion (the panel is always in the initial HTML; JS would hide/replace it only after an event).

**Implementation note for test group B, test 5:** to avoid importing `main.py` (which runs production side-effects), the test fixture should directly import `EventBus`, read the dashboard HTML via `pathlib.Path`, and call `make_stage_router` with those arguments, then mount the router into a minimal `FastAPI()`. This mirrors the pattern in `tests/test_stage.py:_make_app`.

### 6.6 `tests/fakes.py` — append only

Append a labeled block (do not touch existing content):

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

### 6.7 `.env.example` — append only

Append at the end (labeled):

```
# W4 — Dashboard Flagship
ROBIN_DASHBOARD_ENHANCED=
```

---

## 7. TDD Plan — RED → GREEN → REFACTOR

Run every step inside Docker. Never on the host Python.

```bash
docker compose run --rm robin pytest -q tests/test_event_bus.py tests/test_dashboard_wiring.py
docker compose run --rm robin pytest -q   # full suite
docker compose run --rm robin ruff check src tests
```

### Step 1 — Branch

```bash
git checkout -b feat/dashboard-flagship
```

### Step 2 — RED: write `tests/test_event_bus.py` (all 5 tests)

Write the full test file. Run:

```bash
docker compose run --rm robin pytest -q tests/test_event_bus.py
```

Expected: 5 failures (`ImportError: cannot import name 'EventBus' from 'robin.event_bus'` or `ModuleNotFoundError`). This is the RED state. Commit: `test: RED test_event_bus (EventBus not yet implemented)`.

### Step 3 — GREEN: implement `src/robin/event_bus.py`

Write the implementation (§6.1). Run:

```bash
docker compose run --rm robin pytest -q tests/test_event_bus.py
docker compose run --rm robin pytest -q   # full suite — must be green
docker compose run --rm robin ruff check src tests
```

Expected: 5 pass, full suite green, ruff clean. Commit: `feat: add EventBus (mirrors TurnBroadcaster, typed events)`.

### Step 4 — RED: write `src/robin/fixtures/stage_dashboard.html` assertions in `tests/test_dashboard_wiring.py` (Group A + Group B tests 3–4)

Write group A tests and the two file-content tests (3, 4). Run:

```bash
docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
```

Expected: group A tests pass (flag-off serves original HTML — the original `_STAGE_HTML` is already the default); tests 3 and 4 fail with `FileNotFoundError` (dashboard HTML does not exist yet). This is RED. Commit: `test: RED dashboard HTML file-content assertions`.

### Step 5 — GREEN: write `src/robin/fixtures/stage_dashboard.html`

Write the full self-contained HTML (§6.2). Verify manually by opening in a browser. Run:

```bash
docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: tests 3 and 4 pass; group A green; full suite green; ruff clean. Commit: `feat: add stage_dashboard.html (four-panel, disclosure banner, sponsor placeholders)`.

### Step 6 — RED: write remaining `tests/test_dashboard_wiring.py` tests (5–9)

Add tests 5 through 9. Run:

```bash
docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
```

Expected: tests 5–8 fail (hooks not wired, `EventBus` not passed to stage router). Test 9 passes (static file content). RED state. Commit: `test: RED dashboard wiring integration tests`.

### Step 7 — GREEN: wire W4 sub-block in `main.py` + append `fakes.py` + `.env.example`

Edit `main.py` to insert the W4 sub-block (§6.3). Append to `tests/fakes.py` (§6.6). Append to `.env.example` (§6.7). Run:

```bash
docker compose run --rm robin pytest -q tests/test_dashboard_wiring.py
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: all 9 dashboard wiring tests pass; full suite green; ruff clean. Commit: `feat: wire W4 dashboard (EventBus + hooks + flag-gated main.py block)`.

### Step 8 — REFACTOR

Review `event_bus.py` and the hook closures in the `main.py` sub-block for clarity. Check `stage_dashboard.html` for any duplicate or stale CSS. Verify `FakeEventBus` is clean. No behavior changes — tests must remain green throughout. Run:

```bash
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Commit: `refactor: W4 cleanup — event_bus, dashboard hooks, fakes`.

### Step 9 — Manual browser check

```bash
ROBIN_DASHBOARD_ENHANCED=1 docker compose up robin
```

Open `http://localhost:8000/stage` in a browser. Verify:

- [ ] Four-panel grid visible.
- [ ] Disclosure banner present at top, red background, correct text.
- [ ] All three sponsor placeholders visible (Moss, Super Memory, Agent Mail).
- [ ] `EventSource` connects to `/stage/stream` (check browser DevTools → Network → EventStream).
- [ ] No console errors.

Then test flag-off:

```bash
docker compose up robin
```

Open `http://localhost:8000/stage`. Verify the original single-column transcript page is served (not the dashboard).

### Step 10 — Coverage check

```bash
docker compose run --rm robin pytest --cov=src/robin/event_bus --cov=src/robin --cov-report=term-missing -q tests/test_event_bus.py tests/test_dashboard_wiring.py
```

Target: ≥ 80% on `event_bus.py` and the hook closures reachable via `test_dashboard_wiring.py`. The dashboard HTML is not Python, so it is excluded from coverage.

### Step 11 — Flag-off regression gate (mandatory before PR)

```bash
docker compose run --rm robin pytest -q tests/test_stage.py tests/test_broadcast.py
```

Both existing test files must pass without modification. This is the canonical flag-off regression gate. If either fails, stop and diagnose before merging.

---

## 8. Time-box table + collapse ladder

**Hard time-box: 3 hours.** Start clock at `git checkout -b feat/dashboard-flagship`.

| Time (T+) | Milestone | Min-shippable? |
|---|---|---|
| T+0:00 | Branch created | — |
| T+0:15 | `test_event_bus.py` written (RED) | — |
| T+0:30 | `event_bus.py` green, full suite green | No (nothing visible yet) |
| T+0:45 | File-content tests written (RED) | — |
| T+1:00 | `stage_dashboard.html` green (disclosure + placeholders) | **YES** — transcript panel works, flag-off untouched. Stop here if needed. |
| T+1:30 | Integration tests written (RED) | — |
| T+2:00 | `main.py` sub-block wired, all tests green | **YES** — citation + mail panels work |
| T+2:30 | Refactor + manual browser check | **YES** |
| T+3:00 | Final regression gate + PR ready | **YES — merge target** |

**Collapse ladder (cut in this order if behind). Note the ordering is
driven by isolation cleanliness: the transcript-feed tier is the only
part that reaches outside the pure-W0-event_bus contract, so it is cut
first.**

1. **First cut: the optional transcript-feed tier.** Drop the
   `_place_with_turns` override entirely. Keep the `TurnBroadcaster()`
   (unfed) so `make_stage_router` still mounts and the `/stage/stream`
   SSE serves the event_bus events; the transcript panel simply shows
   its placeholder. This returns W4 to a **pure-W0-event_bus, fully
   isolated** branch (no `_tool_impls` override, no outbound rewire) —
   citation + mail panels still fill live. This is the recommended
   minimal shippable W4.
2. **Second cut: memory panel.** Permanent styled placeholder (no
   `memory` listener). `"Super Memory recall will appear here"` stays in
   the HTML so file-content tests are unchanged.
3. **Third cut: mail draft panel.** Remove the `mail_draft` listener and
   `_mail_pub` hook; register only `_citation_pub`. Citation panel still
   fills in real time — Moss data appearing before the dial is the
   single highest-wow moment and the $10K-track tie-in.
4. **Last cut: do not merge.** If citation panel is not green by T+2:30,
   leave the branch unmerged. Demo from `main`. Costs nothing — the
   canonical demo is unchanged and `/stage` is unmounted exactly as
   today.

---

## 9. Flag-off regression gate

The following command is the mandatory final gate before any merge into `main`:

```bash
docker compose run --rm robin pytest -q tests/test_stage.py tests/test_broadcast.py
```

With `ROBIN_DASHBOARD_ENHANCED` unset (the default), the full suite must pass including all of `test_stage.py` — which pins the original HTML, the disclosure banner, the `Robin` / `Receptionist` labels, the `EventSource('/stage/stream')` wiring, the SSE headers, and the turn / heartbeat / unsubscribe behaviours. None of these must be broken.

Additionally:

```bash
docker compose run --rm robin pytest -q
```

The full suite (all test files) must be green.

And:

```bash
ROBIN_DASHBOARD_ENHANCED=0 docker compose run --rm robin pytest -q
```

Explicit flag-off (string `"0"`, which is not `"1"`) — same result.

---

## 10. Demo moment

With `ROBIN_DASHBOARD_ENHANCED=1` running and a browser open at `http://localhost:8000/stage` (or the ngrok/tunnel URL projected to the auditorium):

- **Step 1–2 (discovery + Browser Use):** Transcript panel fills with the inbound dialogue. Moss citation panel shows its placeholder with the caption "Moss legal citation will appear here when Browser Use completes the statute search."
- **Step 2 complete (Browser Use finishes `research_cancellation_law`):** The `citation` event fires. The Moss panel fills with the three pre-verified statutes — `cal_health_safety`, `ftc_rule_37`, `cal_civil_code` (or whichever are in the verified corpus) — rendered with operative quotes. This is the first visible sponsor integration.
- **Step 3–5 (outbound negotiation):** Transcript panel shows both sides of the negotiation as turns are published. Super Memory panel holds its placeholder (W4-alone; if W1 merged, it fills at Step 1). Agent Mail panel holds its placeholder.
- **Step 6–7 (capitulation + callback):** `deliver_result` fires, the `mail_draft` event publishes, the Agent Mail panel fills with the summary ("cancelled + last-month refund") and confirmation number (`24HF-4471`). This is the second visible sponsor integration.

All three sponsor panels are visible on one projector screen simultaneously. Judges can see Moss legal data populating at Step 2 and Agent Mail output populating at Step 6–7 without switching views. The disclosure banner remains fixed at the top throughout.

**Graceful degradation on stage:** if the `EventSource` connection drops, the browser auto-reconnects (native `EventSource` behaviour). If a hook raises (the `try/except` in both hooks ensures it cannot propagate), the turn continues normally. If the dashboard HTML fails to serve (e.g., file not found at startup), the Docker startup itself fails with a `FileNotFoundError` (since `pathlib.Path(...).read_text()` runs at import time inside the flag block) — this is intentional fail-fast behaviour so the problem is caught before going on stage. Mitigation: the manual browser check at T+2:30 (Step 9 of TDD plan) catches this.

---

## 11. Explicit fallback

If this branch is not merge-ready by 6:00 PM (the plan's feature freeze), the presenter demos from `main` with the existing single-column transcript page. The branch is left open in repo history as visible evidence of the work. No merge, no cherry-pick, no partial application. The canonical demo is identical to pre-W4 `main`.

---

## 12. Merge instructions

### Pre-conditions

- W0 (`feat/extension-seam`) is merged to `main` and the full suite is green on `main`.
- This branch has a clean `git log --oneline feat/dashboard-flagship ^main` (no accidental W0 commits replayed).

### What this branch adds to `main`

| File | Change |
|---|---|
| `src/robin/event_bus.py` | New file |
| `src/robin/fixtures/stage_dashboard.html` | New file |
| `tests/test_event_bus.py` | New file |
| `tests/test_dashboard_wiring.py` | New file |
| `tests/fakes.py` | Append-only (W4 labeled block) |
| `.env.example` | Append-only (W4 labeled block) |
| `src/robin/main.py` | W4 sub-block only (between `# >>> W4 dashboard wiring <<<` and `# >>> end W4 <<<`; git auto-merges) |

### Files that must NOT be modified by this branch

`loop.py`, `stage.py`, `app.py`, `classifier.py`, `signature.py`, `models.py`, `extensions.py`, `broadcast.py`, `config.py`, `context_pack.py`, `prompts.py`, `tools.py`, `agentphone_client.py`, `outbound.py`, `obs.py`, `anthropic_adapter.py`, `fixtures/law.html`, `fixtures/prompts/*.txt`. If any of these appear in `git diff main`, stop and diagnose.

### Merge command

```bash
git checkout main
git merge --no-ff feat/dashboard-flagship -m "feat: W4 dashboard flagship (EventBus, four-panel SSE dashboard, citation + mail hooks)"
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Full suite must be green before the merge commit is pushed (by the human — git push is denied in agent settings).

---

## 13. Security and PII checklist

Before every commit on this branch:

- [ ] `stage_dashboard.html` contains no hardcoded API keys, tokens, or secrets. All data is populated client-side via SSE at runtime.
- [ ] Transcript shown in the dashboard during the demo is the simulated gym-cancel demo only — the `context_pack.json` is gitignored; no real names, real numbers, or real emails appear in any committed file.
- [ ] The `citations` data published on the bus originates from `out_dict` returned by `research_cancellation_law` — pre-verified statutes from `src/robin/fixtures/law.html`, no web text or PII.
- [ ] `_citation_pub` and `_mail_pub` log via `obs.log_event` only if there is an exception (inside the `except Exception: pass` blocks the hooks swallow silently — no logging of payload content containing PII).
- [ ] `tests/test_event_bus.py` and `tests/test_dashboard_wiring.py` use synthetic fixture data only: `call_id="test-call-001"`, citation text from the verified law corpus or placeholder strings, no real phone numbers.
- [ ] `tests/fakes.py` `FakeEventBus.published` list is never printed to stdout; tests assert on its contents in memory only.
- [ ] Disclosure banner text is preserved verbatim per §4. Do not weaken or remove the "a briefed teammate" and "no real business is called" language.
- [ ] `.env.example` entry `ROBIN_DASHBOARD_ENHANCED=` has no default value set (empty = feature disabled by default).
- [ ] `src/robin/event_bus.py` does not import `os`, does not read env vars, does not log. It is a pure asyncio pub/sub primitive.
- [ ] No `print()` or `logging.debug` calls added that could leak event payload content to stdout in production.
