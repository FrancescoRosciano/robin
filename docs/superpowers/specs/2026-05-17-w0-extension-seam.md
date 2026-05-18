# W0 — Extension Seam

**Branch:** `feat/extension-seam`
**Size:** S (~0.5–0.75 h)
**Depends-on:** none — lands on `main` first; W1–W4 cut from post-W0 `main`
**Date:** 2026-05-17
**Status:** ready to implement

---

## Goal

Install an **inert, flag-free shared seam** in `loop.py`, `app.py`, `stage.py`, and
`main.py` so that four subsequent feature branches (W1–W4) become purely additive
and never collide at those hot-spots. With every hook list empty (the default) the
canonical gym-cancel demo runs **byte-identical** to `main` today — same outputs,
same timing, same test assertions, zero behavioral change.

---

## Orientation

### Portfolio fit

The master design (`docs/superpowers/specs/2026-05-17-robin-sponsor-extensions-design.md`)
describes a portfolio of four sponsor integrations (Super Memory, Agent Mail, Moss, and
a live dashboard) that all want to react to two moments inside `loop.py`:

1. After `_record_session` processes a tool result — W1/W2 want to persist or email
   the outcome; W4 wants to publish it to a live bus.
2. During `run_turn`'s system-prompt assembly — W1 wants to prepend caller history.

If each feature branch edits those same two locations, they produce merge conflicts.
W0 converts the two edits into **injected callback lists** (`ExtensionHooks`) so every
feature branch only needs to register its own callback at the composition root
(`main.py`) — work that lands in four distinct, pre-labeled insertion points that git
auto-merges.

### Isolation contract (§2 of the master design)

- **Flag-off ⇒ no-op, byte-identical.** `ExtensionHooks()` with all empty tuples is
  the default everywhere. No `ROBIN_*` env var, no config key added to `Settings`.
- **Graceful no-op on any failure.** A hook that raises is caught, logged with
  `obs.log_event("extension_hook_error", ...)`, and the turn continues normally.
- **New code in new files.** `src/robin/extensions.py` is new. The edits to
  `loop.py`, `app.py`, `stage.py`, and `main.py` are additive-only (new params with
  defaults, new optional branches).
- **Constructor injection + fake.** Tests use standalone callables; no live telephony,
  no real SDKs.

### Why W0 is inert

`ExtensionHooks()` contains only empty tuples and `event_bus=None`. Every loop in W0
iterates over an empty tuple ⇒ zero iterations ⇒ zero side effects. The `stage.py`
parametrization uses its current `_STAGE_HTML` as the default ⇒ the served HTML is
identical. `main.py` gains a delimited comment block and `_hooks = ExtensionHooks()`
passed to `build_app` — `build_app` ignores it except to thread it into `run_turn`,
where the empty hooks are again no-ops. The existing test suite verifies this.

---

## Exact seams

All line numbers confirmed by reading the files. The **Before** column states what the
line currently does; **After** states the new intent. Only the minimal, additive
changes are described — nothing else in these files changes.

### 1. New file `src/robin/extensions.py` (lines: entire new file)

**Before:** does not exist.

**After:** a frozen dataclass `ExtensionHooks` with three hook-tuple fields and an
opaque `event_bus` slot, plus three `Callable` type aliases. Docstring makes the
hook-author contract explicit.

```python
"""Extension seam — inert injected hooks. Empty == today's behavior.

Hook-author contract
--------------------
A hook MUST return quickly (<~200 ms wall time) and MUST NOT raise. If a
hook needs to do long work (network I/O, email send, SDK persist) it MUST
schedule that work via ``asyncio.create_task(...)`` inside the hook body and
return immediately. Robin awaits the hook in the hot call-turn path; a slow
or crashing hook degrades every caller's experience.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

# Signature: (call_id: str | None) -> str
# Return "" to contribute nothing; non-empty text is appended to the system prompt.
PromptEnricher = Callable[[str | None], Awaitable[str]]

# Signature: (call_id: str | None, payload: dict) -> None
# Must not raise. Long work → asyncio.create_task inside the hook.
ResearchHook = Callable[[str | None, dict], Awaitable[None]]
OutcomeHook  = Callable[[str | None, dict], Awaitable[None]]


@dataclass(frozen=True)
class ExtensionHooks:
    """Injected callback bundles. All fields default to empty/None == no-op."""

    prompt_enrichers: tuple[PromptEnricher, ...] = ()
    """Awaited once per turn, before the first LLM call. Returns extra system
    prompt text appended after the session-memory block, in registration order."""

    on_research: tuple[ResearchHook, ...] = ()
    """Fired after research_cancellation_law returns status=="OK".
    Payload = the full ``out`` dict from the tool."""

    on_outcome: tuple[OutcomeHook, ...] = ()
    """Fired after deliver_result returns delivered==True.
    Payload = {"summary": str, "confirmation": str|None, "channel": str|None,
               "out": dict}."""

    event_bus: object | None = None
    """Opaque handle supplied by W4. None == inert. W0 passes it through
    make_stage_router; stage.py drains its subscribe()/unsubscribe(q) queue."""
```

### 2. `src/robin/loop.py` — `_record_session` (lines 62–86)

**Before (lines 62–63):**
```python
def _record_session(call_id: str | None, name: str, tool_input: dict,
                    out: object) -> None:
```
Synchronous function; no hooks parameter. Its existing best-effort
`session.*` dispatch (the `try/except` with the
`research_cancellation_law` / `place_negotiation_call` / `deliver_result`
branches) is at **lines 71–86**.

**After:** becomes `async def`, gains a trailing `hooks: ExtensionHooks` parameter.
After the existing `session.*` calls (lines 71–86), two new dispatch blocks run
best-effort:

- When `name == "research_cancellation_law"` and `out.get("status") == "OK"`:
  iterate `hooks.on_research`, await each, wrapped in `try/except` →
  `obs.log_event("extension_hook_error", call_id=call_id, hook=repr(h), err=...)`.
  Payload passed = the full `out` dict.
- When `name == "deliver_result"` and `out.get("delivered")`:
  iterate `hooks.on_outcome`, await each with the same guard.
  Payload = `{"summary": str(tool_input.get("summary", "")), "confirmation": tool_input.get("confirmation"), "channel": tool_input.get("channel"), "out": out}`.

One bad hook never kills or delays any other hook or the turn itself.

**Call site (line 140):**

**Before:**
```python
            _record_session(call_id, name, tool_input, out)
```
**After:**
```python
            await _record_session(call_id, name, tool_input, out, hooks)
```

### 3. `src/robin/loop.py` — `run_turn` signature (lines 89–92)

**Before:**
```python
async def run_turn(transcript: str, history: list, *, system: str, llm,
                   tool_impls: dict[str, Callable],
                   call_id: str | None = None
                   ) -> AsyncGenerator[dict, None]:
```

**After:** gains `hooks: ExtensionHooks = ExtensionHooks()` as an additional keyword
parameter (after `call_id`). Import `ExtensionHooks` at the top of the file.

### 4. `src/robin/loop.py` — prompt enricher dispatch (after line 106)

**Before (line 106):**
```python
    effective_system = f"{system}\n\n{mem}" if mem else system
```
Preceded by `mem = session.summary_for_prompt(call_id)` at line 105, and
immediately followed by the `obs.log_event("turn_start", ...)` call at
lines 107–108.

**After:** insert enricher dispatch block between line 106 and line 107
(after `effective_system` is assigned, before the `turn_start` log):

```python
    # --- W0 prompt enrichers (best-effort, no-op when empty) ---
    if hooks.prompt_enrichers:
        _extra: list[str] = []
        for _enricher in hooks.prompt_enrichers:
            try:
                _piece = await _enricher(call_id)
                if _piece:
                    _extra.append(_piece)
            except Exception as _exc:  # noqa: BLE001
                obs.log_event("extension_hook_error", call_id=call_id,
                               hook=repr(_enricher),
                               err=f"{type(_exc).__name__}: {_exc}")
        if _extra:
            effective_system = effective_system + "\n\n" + "\n\n".join(_extra)
    # --- end W0 prompt enrichers ---
```

Enrichers execute in registration order; each non-empty return is appended in that
order. With an empty tuple the `if` is falsy and zero lines of work run.

### 5. `src/robin/app.py` — `build_app` signature (line 21–22)

**Before:**
```python
def build_app(*, secret: str, law_html_path: str, llm: object,
              tool_impls: dict, system_prompt: str = "You are Robin.") -> FastAPI:
```

**After:** gains `hooks: ExtensionHooks = ExtensionHooks()` as an additional keyword
parameter. Import `ExtensionHooks` from `robin.extensions`. Add
`from robin.extensions import ExtensionHooks` at the top of the file.

### 6. `src/robin/app.py` — `run_turn` call site (lines 62–65)

**Before:**
```python
        async for chunk in run_turn(transcript, history,
                                    system=system_prompt, llm=llm,
                                    tool_impls=tool_impls,
                                    call_id=call_id):
```

**After:** add `hooks=hooks` keyword:

```python
        async for chunk in run_turn(transcript, history,
                                    system=system_prompt, llm=llm,
                                    tool_impls=tool_impls,
                                    call_id=call_id,
                                    hooks=hooks):
```

### 7. `src/robin/stage.py` — `make_stage_router` signature (line 102)

**Before:**
```python
def make_stage_router(broadcaster) -> APIRouter:
    """Build the /stage router bound to the given TurnBroadcaster instance."""
```

**After:** gains two optional parameters:

```python
def make_stage_router(
    broadcaster,
    *,
    event_bus=None,
    stage_html: str | None = None,
) -> APIRouter:
    """Build the /stage router bound to the given TurnBroadcaster instance.

    Parameters
    ----------
    broadcaster:
        TurnBroadcaster instance — unchanged from today.
    event_bus:
        Optional W4 EventBus. When provided its subscribe()/unsubscribe(q)
        queue items of shape {"event": str, "data": dict} are drained into
        the SSE stream alongside "turn" events. None (default) == today's
        behavior exactly.
    stage_html:
        Optional HTML string to serve from GET /stage. Defaults to
        _STAGE_HTML (the current inline string) — identical behavior.
    """
    _html = stage_html if stage_html is not None else _STAGE_HTML
```

**GET /stage handler (line 107–108):**

**Before:**
```python
        return HTMLResponse(content=_STAGE_HTML)
```
**After:**
```python
        return HTMLResponse(content=_html)
```

**SSE stream (stage_stream, inside event_generator):**

The existing heartbeat/turn loop stays entirely intact. After the `turn` event is
emitted (or while the generator is running), when `event_bus is not None`, the
generator also attempts to drain the event bus queue non-blocking:

```python
                    # --- W0 event_bus drain (no-op when None) ---
                    if event_bus is not None:
                        try:
                            bus_q = event_bus.subscribe()
                            try:
                                while True:
                                    item = bus_q.get_nowait()
                                    payload = json.dumps(item["data"])
                                    yield (f"event: {item['event']}\n"
                                           f"data: {payload}\n\n")
                            except asyncio.QueueEmpty:
                                pass
                        finally:
                            event_bus.unsubscribe(bus_q)
```

NOTE: the SSE-drain snippet above is **illustrative only** — it is not a
correct multiplexing implementation as written (re-subscribing per
iteration). W4 owns the real multiplexed dashboard SSE design. W0's only
hard requirement here is that with `event_bus=None` (the default) the
generated SSE stream is **byte-identical** to today and all existing
`test_stage.py` assertions pass unmodified. The exact `event_bus`
placement is at the implementer's discretion.

> **Ground-truth reality (do not skip):** `make_stage_router` is
> **never called in `src/robin/main.py`** today — read main.py end to
> end and confirm: there is no `from robin.stage import ...` and no
> `app.include_router(...)`. The `/stage` route is therefore **not
> mounted** in the running app right now; only `tests/test_stage.py`
> exercises `make_stage_router` directly. Consequently:
> - W0 **only parametrizes** `make_stage_router` (defaults ⇒
>   `test_stage.py` stays byte-identical and green). **W0 must NOT add
>   the router mount to `main.py`** — leaving `/stage` unmounted is the
>   correct flag-off (byte-identical) behavior.
> - **W4 owns adding the flag-gated `app.include_router(make_stage_router(...))`
>   mount** in its `>>> W4 <<<` `main.py` sub-block. With
>   `ROBIN_DASHBOARD_ENHANCED` unset, `/stage` remains unmounted exactly
>   as today (a 404), which is the required no-op.

### 8. `src/robin/main.py` — sponsor extension wiring block (after line 63)

**Before (lines 60–63, the entire end of the file):**
```python
app = build_app(
    secret=_settings.agentphone_webhook_secret,
    law_html_path=LAW_HTML_PATH, llm=_llm, tool_impls=_tool_impls,
    system_prompt=render_inbound_system_prompt(_pack))
```

**After:** add the import and the delimited wiring section, then thread `hooks=_hooks`
into `build_app`:

```python
from robin.extensions import ExtensionHooks

# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
# >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
# >>> W4 dashboard wiring   <<<   (added on feat/dashboard-flagship)
# --- end sponsor extension wiring ---

app = build_app(
    secret=_settings.agentphone_webhook_secret,
    law_html_path=LAW_HTML_PATH, llm=_llm, tool_impls=_tool_impls,
    system_prompt=render_inbound_system_prompt(_pack),
    hooks=_hooks)
```

Each feature branch inserts only its own `>>> Wn <<<` sub-block, rebuilding `_hooks`
immutably (e.g. `_hooks = ExtensionHooks(..._hooks, prompt_enrichers=(_hooks.prompt_enrichers + (my_fn,)))`).
The four labeled lines are distinct git lines ⇒ auto-merge, no conflicts.

---

## TDD Plan

All tests live in `tests/test_extensions.py`. The verification commands assume Docker
(mandatory on this machine — all Python runs inside the container):

```
# Fast: new test file only
docker compose run --rm robin pytest -q tests/test_extensions.py

# Full regression gate (must stay green after every milestone)
docker compose run --rm robin pytest -q

# Lint
docker compose run --rm robin ruff check src tests
```

Existing `tests/test_stage.py` is **never touched**. It must remain green throughout.

---

### Milestone 0 — scaffolding (pre-RED)

Create `tests/test_extensions.py` with the module docstring, imports, and the helper
fixtures. Do not write any test function yet — just the file structure. Run `ruff` to
confirm imports resolve.

```python
"""tests/test_extensions.py — W0 extension seam unit tests.

Each test is self-contained: no live telephony, no real SDKs, no env vars.
All async tests use pytest-asyncio (already in requirements-dev.txt).
"""
import asyncio
import pytest

# These imports will fail until the seam is implemented (that's the RED step).
from robin.extensions import ExtensionHooks, PromptEnricher, ResearchHook, OutcomeHook
from robin.loop import run_turn, _record_session
from robin.app import build_app
from robin.stage import make_stage_router
from tests.fakes import FakeLLM
```

**Verify (scaffolding):**
```
docker compose run --rm robin ruff check src tests
```

---

### Milestone 1 — `ExtensionHooks` dataclass

**RED — write the failing test first:**

```python
def test_extension_hooks_default_is_all_empty():
    """ExtensionHooks() must be constructible with zero args and all fields empty."""
    hooks = ExtensionHooks()
    assert hooks.prompt_enrichers == ()
    assert hooks.on_research == ()
    assert hooks.on_outcome == ()
    assert hooks.event_bus is None


def test_extension_hooks_is_frozen():
    """ExtensionHooks is a frozen dataclass — mutation must raise."""
    hooks = ExtensionHooks()
    with pytest.raises((AttributeError, TypeError)):
        hooks.event_bus = object()  # type: ignore[misc]


def test_extension_hooks_callable_aliases_exist():
    """PromptEnricher, ResearchHook, OutcomeHook must be importable type aliases."""
    # Just confirm they are callable/type objects; no runtime check needed.
    assert PromptEnricher is not None
    assert ResearchHook is not None
    assert OutcomeHook is not None
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py
```
Expected: 3 failures (ImportError on `robin.extensions`).

**GREEN — create `src/robin/extensions.py`** with the full dataclass as shown in the
Exact Seams section above. No other files change yet.

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py
```
Expected: 3 passes.

**REFACTOR:** confirm the docstrings are complete; confirm the type aliases use
`Callable[[...], Awaitable[...]]` syntax. No behavioral change.

**Full-suite gate:**
```
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```
Expected: full suite green (no new files touched yet).

---

### Milestone 2 — `run_turn` empty-hooks no-op baseline

**RED — write the failing test:**

```python
async def test_run_turn_with_empty_hooks_output_identical_to_no_hooks():
    """run_turn with ExtensionHooks() must yield the same chunks as today's baseline.

    The baseline is captured inline: one interim ack, then the scripted final text.
    """
    llm = FakeLLM([_make_msg(["Hi, I'm Robin."], "end_turn")])
    hooks = ExtensionHooks()

    out_with_hooks = [c async for c in run_turn(
        "hello", [], system="SYS", llm=llm,
        tool_impls={}, call_id=None, hooks=hooks)]

    llm2 = FakeLLM([_make_msg(["Hi, I'm Robin."], "end_turn")])
    out_no_hooks = [c async for c in run_turn(
        "hello", [], system="SYS", llm=llm2,
        tool_impls={}, call_id=None)]

    assert out_with_hooks == out_no_hooks


def _make_msg(texts: list[str], stop_reason: str):
    class _M:
        content = [{"type": "text", "text": t} for t in texts]
    _M.stop_reason = stop_reason
    return _M()
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py::test_run_turn_with_empty_hooks_output_identical_to_no_hooks
```
Expected: 1 failure (`TypeError: run_turn() got an unexpected keyword argument 'hooks'`).

**GREEN:** edit `src/robin/loop.py`:

1. Add `from robin.extensions import ExtensionHooks` at the top (after existing imports, e.g. after line 6 `from robin.tools import TOOL_SCHEMAS`).
2. Add `hooks: ExtensionHooks = ExtensionHooks()` to the `run_turn` signature
   (line ~92, after `call_id: str | None = None`).
3. Insert the enricher dispatch block after line 106 (after `effective_system = ...`, before the `obs.log_event("turn_start", ...)` at lines 107–108).
4. Change `_record_session` (line 62) to `async def` and add `hooks: ExtensionHooks` parameter.
5. Update the call site at line 140: `await _record_session(call_id, name, tool_input, out, hooks)`.

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py::test_run_turn_with_empty_hooks_output_identical_to_no_hooks
```
Expected: 1 pass.

**Full-suite gate (critical — existing tests must not regress):**
```
docker compose run --rm robin pytest -q
```
Expected: all green. If `test_loop.py` breaks, check that `_record_session` call site
was updated from `_record_session(...)` to `await _record_session(...)` and that
`run_turn` is still an `async def` generator.

---

### Milestone 3 — prompt enricher ordering

**RED:**

```python
async def test_prompt_enrichers_append_in_registration_order():
    """Two enrichers: first returns 'AAA', second returns 'BBB'.
    effective_system must end with '\\n\\nAAA\\n\\nBBB' in that order."""
    captured_systems: list[str] = []

    class _CaptureLLM:
        async def create(self, *, system, messages, tools):
            captured_systems.append(system)
            return _make_msg(["done"], "end_turn")

    async def enricher_a(call_id):
        return "AAA"

    async def enricher_b(call_id):
        return "BBB"

    hooks = ExtensionHooks(prompt_enrichers=(enricher_a, enricher_b))
    _ = [c async for c in run_turn(
        "hi", [], system="BASE", llm=_CaptureLLM(),
        tool_impls={}, call_id="c1", hooks=hooks)]

    assert len(captured_systems) == 1
    sys = captured_systems[0]
    assert sys.endswith("\n\nAAA\n\nBBB"), f"Unexpected system: {sys!r}"
    assert sys.startswith("BASE")


async def test_prompt_enricher_returning_empty_string_is_skipped():
    """An enricher returning '' must not add blank lines to the system prompt."""
    captured_systems: list[str] = []

    class _CaptureLLM:
        async def create(self, *, system, messages, tools):
            captured_systems.append(system)
            return _make_msg(["done"], "end_turn")

    async def enricher_empty(call_id):
        return ""

    async def enricher_real(call_id):
        return "REAL"

    hooks = ExtensionHooks(prompt_enrichers=(enricher_empty, enricher_real))
    _ = [c async for c in run_turn(
        "hi", [], system="BASE", llm=_CaptureLLM(),
        tool_impls={}, call_id="c1", hooks=hooks)]

    sys = captured_systems[0]
    assert "REAL" in sys
    assert "\n\n\n" not in sys   # no double-blank from empty return
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "enricher"
```
Expected: 2 failures (enricher dispatch not yet in loop.py).

**GREEN:** confirm the enricher dispatch block from the Exact Seams section is in
place (should already be from Milestone 2 GREEN step). If not, add it now.

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "enricher"
```
Expected: 2 passes.

**REFACTOR:** no behavioral change needed; confirm no stray `_extra` variable leaks
into outer scope in the non-enricher path.

---

### Milestone 4 — raising enricher is swallowed and logged

**RED:**

```python
async def test_raising_enricher_is_swallowed_and_turn_completes():
    """An enricher that raises must not crash the turn; the next enricher still runs."""
    called = []

    async def bad_enricher(call_id):
        raise ValueError("enricher kaboom")

    async def good_enricher(call_id):
        called.append("good")
        return "GOOD"

    class _LLM:
        async def create(self, *, system, messages, tools):
            return _make_msg(["done"], "end_turn")

    hooks = ExtensionHooks(prompt_enrichers=(bad_enricher, good_enricher))
    out = [c async for c in run_turn(
        "hi", [], system="BASE", llm=_LLM(),
        tool_impls={}, call_id="c1", hooks=hooks)]

    # Turn must still deliver a final chunk
    assert any("interim" not in c for c in out)
    # The good enricher still ran
    assert called == ["good"]
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "raising_enricher"
```
Expected: 1 failure if the try/except around individual enrichers is not per-enricher.
Confirm the implementation wraps each enricher call individually, not the whole loop.

**GREEN:** verify the try/except in the enricher block wraps only the single `await
_enricher(call_id)` call, not the whole `for` loop. Adjust if needed.

---

### Milestone 5 — `on_research` hook fires with exact payload

**RED:**

```python
async def test_on_research_hook_fires_with_exact_payload():
    """on_research must be called with (call_id, out_dict) when research returns OK."""
    received: list[tuple] = []

    async def research_hook(call_id, payload):
        received.append((call_id, payload))

    # Simulate what _record_session sees
    out = {"status": "OK", "citations": [{"citation": "FTC §425", "operative_quote": "easy cancel"}]}
    hooks = ExtensionHooks(on_research=(research_hook,))

    await _record_session("call_42", "research_cancellation_law", {}, out, hooks)

    assert len(received) == 1
    cid, payload = received[0]
    assert cid == "call_42"
    # payload is the full out dict
    assert payload is out
    assert payload["status"] == "OK"


async def test_on_research_hook_does_not_fire_when_status_not_ok():
    """on_research must NOT fire if research returns status != 'OK'."""
    received: list = []

    async def research_hook(call_id, payload):
        received.append(payload)

    out = {"status": "ERR", "citations": []}
    hooks = ExtensionHooks(on_research=(research_hook,))

    await _record_session("call_42", "research_cancellation_law", {}, out, hooks)

    assert received == []


async def test_on_research_hook_does_not_fire_for_other_tools():
    """on_research must not fire for place_negotiation_call or deliver_result."""
    received: list = []

    async def research_hook(call_id, payload):
        received.append(payload)

    hooks = ExtensionHooks(on_research=(research_hook,))

    await _record_session("c1", "place_negotiation_call", {}, {"call_id": "x"}, hooks)
    await _record_session("c1", "deliver_result", {"summary": "done"}, {"delivered": True}, hooks)

    assert received == []
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "on_research"
```
Expected: failures because `_record_session` does not yet dispatch hooks.

**GREEN:** the `async def _record_session` with hook dispatch (Milestone 2 GREEN)
should already be in place. If the dispatch block is correct, these tests pass
immediately. If not, add the `on_research` dispatch block as specified in Exact Seams.

---

### Milestone 6 — `on_outcome` hook fires with exact payload

**RED:**

```python
async def test_on_outcome_hook_fires_with_exact_payload_shape():
    """on_outcome must be called with the documented payload dict."""
    received: list[tuple] = []

    async def outcome_hook(call_id, payload):
        received.append((call_id, payload))

    tool_input = {
        "summary": "Cancelled + last-month refund",
        "confirmation": "24HF-4471",
        "channel": "callback",
    }
    out = {"delivered": True}
    hooks = ExtensionHooks(on_outcome=(outcome_hook,))

    await _record_session("call_99", "deliver_result", tool_input, out, hooks)

    assert len(received) == 1
    cid, payload = received[0]
    assert cid == "call_99"
    assert payload["summary"] == "Cancelled + last-month refund"
    assert payload["confirmation"] == "24HF-4471"
    assert payload["channel"] == "callback"
    assert payload["out"] is out


async def test_on_outcome_hook_does_not_fire_when_delivered_false():
    """on_outcome must NOT fire if delivered is False/absent."""
    received: list = []

    async def outcome_hook(call_id, payload):
        received.append(payload)

    hooks = ExtensionHooks(on_outcome=(outcome_hook,))

    await _record_session("c1", "deliver_result", {"summary": "x"}, {"delivered": False}, hooks)
    await _record_session("c1", "deliver_result", {"summary": "x"}, {}, hooks)

    assert received == []
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "on_outcome"
```
Expected: passes if Milestone 5's dispatch block covers both on_research and on_outcome.

---

### Milestone 7 — raising hooks are swallowed and logged; turn still completes

**RED:**

```python
async def test_raising_research_hook_is_swallowed_next_hook_still_runs():
    """A crashing on_research hook must not propagate; subsequent hooks still execute."""
    called = []

    async def bad_hook(call_id, payload):
        raise RuntimeError("hook boom")

    async def good_hook(call_id, payload):
        called.append("good")

    hooks = ExtensionHooks(on_research=(bad_hook, good_hook))
    out = {"status": "OK", "citations": []}

    # Must not raise
    await _record_session("c1", "research_cancellation_law", {}, out, hooks)

    assert called == ["good"]


async def test_raising_outcome_hook_does_not_affect_turn_completion():
    """A crashing on_outcome hook must not prevent _record_session from returning."""
    async def bad_outcome_hook(call_id, payload):
        raise ValueError("outcome boom")

    hooks = ExtensionHooks(on_outcome=(bad_outcome_hook,))
    out = {"delivered": True}

    # Must not raise and must return without error
    await _record_session("c1", "deliver_result", {"summary": "done"}, out, hooks)
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "raising"
```
Expected: passes if each hook call is individually wrapped in try/except.

---

### Milestone 8 — `build_app` threads hooks through to `run_turn`

**RED:**

```python
async def test_build_app_passes_hooks_to_run_turn(monkeypatch, tmp_path):
    """build_app(hooks=...) must thread hooks into run_turn.

    We inject an enricher that records it was called; then POST to /webhook
    and verify the enricher ran.
    """
    from fastapi.testclient import TestClient
    import json

    enricher_called: list[str | None] = []

    async def spy_enricher(call_id):
        enricher_called.append(call_id)
        return ""

    hooks = ExtensionHooks(prompt_enrichers=(spy_enricher,))

    class _LLM:
        async def create(self, *, system, messages, tools):
            return _make_msg(["done"], "end_turn")

    law = tmp_path / "law.html"
    law.write_text("<html>law</html>")

    import robin.app as app_mod
    monkeypatch.setattr(app_mod, "_SKIP_VERIFY", True)

    app = build_app(
        secret="s", law_html_path=str(law), llm=_LLM(),
        tool_impls={}, hooks=hooks)

    payload = json.dumps({
        "event": "agent.message",
        "data": {"transcript": "hello", "callId": "c_hook_test"},
        "recentHistory": [],
    })
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post("/webhook", content=payload,
                       headers={"content-type": "application/json"})
    # Consume the streaming body
    _ = resp.text

    assert "c_hook_test" in enricher_called
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "build_app_passes_hooks"
```
Expected: failure (`build_app() got an unexpected keyword argument 'hooks'`).

**GREEN:** edit `src/robin/app.py` — add `ExtensionHooks` import and the `hooks`
parameter to `build_app`, thread it into `run_turn` call (Exact Seams §5–6).

---

### Milestone 9 — `make_stage_router` with defaults is byte-identical

**RED:**

```python
def test_make_stage_router_default_html_is_byte_identical():
    """make_stage_router() with no args (besides broadcaster) must return the same HTML
    as the original call — existing test_stage.py assertions must all still hold."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from robin.broadcast import TurnBroadcaster

    b = TurnBroadcaster()

    # New call with explicit defaults (should match original)
    app_new = FastAPI()
    app_new.include_router(make_stage_router(b, event_bus=None, stage_html=None))
    body_new = TestClient(app_new).get("/stage").text

    # Original call (positional broadcaster only)
    app_orig = FastAPI()
    app_orig.include_router(make_stage_router(b))
    body_orig = TestClient(app_orig).get("/stage").text

    assert body_new == body_orig


def test_make_stage_router_custom_html_is_served():
    """When stage_html is supplied it replaces the default HTML."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from robin.broadcast import TurnBroadcaster

    b = TurnBroadcaster()
    custom = "<html><body>CUSTOM</body></html>"
    app = FastAPI()
    app.include_router(make_stage_router(b, stage_html=custom))
    body = TestClient(app).get("/stage").text
    assert body == custom


def test_make_stage_router_no_event_bus_sse_identical():
    """With event_bus=None the SSE stream produces the same turn events as before."""
    # This is validated indirectly by running test_stage.py (which we do NOT modify).
    # This test just confirms make_stage_router accepts the new signature with defaults.
    from robin.broadcast import TurnBroadcaster
    router = make_stage_router(TurnBroadcaster(), event_bus=None, stage_html=None)
    assert router is not None
```

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "stage_router"
```
Expected: failures (`make_stage_router() got an unexpected keyword argument 'event_bus'`).

**GREEN:** edit `src/robin/stage.py` — add `event_bus=None, stage_html: str | None = None`
parameters (Exact Seams §7). Replace `_STAGE_HTML` reference with `_html = stage_html if stage_html is not None else _STAGE_HTML`. Serve `_html` from the GET route.

Run:
```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "stage_router"
docker compose run --rm robin pytest -q tests/test_stage.py    # must stay green!
```

---

### Milestone 10 — `main.py` wiring block (syntax + import check)

This milestone has no behavioral test (main.py is hard to unit-test without monkeypatching
every env var; that is covered by `test_main_wiring.py`). The goal is to:

1. Add `from robin.extensions import ExtensionHooks` to `main.py`.
2. Insert the delimited wiring section with empty `_hooks` and the four labeled markers.
3. Pass `hooks=_hooks` to `build_app(...)`.

**Verify syntax and existing wiring tests still pass:**

```
docker compose run --rm robin python -c "import ast, pathlib; ast.parse(pathlib.Path('src/robin/main.py').read_text()); print('syntax OK')"
docker compose run --rm robin pytest -q tests/test_main_wiring.py
docker compose run --rm robin ruff check src tests
```

Expected: all green. If `test_main_wiring.py::test_tool_impls_has_exact_keys` fails,
confirm that the `app = build_app(...)` call is not accidentally passing unknown kwargs.

---

### Milestone 11 — flag-off regression gate (final gate before merge)

**The complete flag-off gate:**

```
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: every existing test green. The new `tests/test_extensions.py` adds to the
suite; `tests/test_stage.py` and `tests/test_main_wiring.py` must be **unmodified and
green**. With `ExtensionHooks()` defaults the gym-cancel demo is byte-identical to
pre-W0 `main`.

---

## Time-box Table

| T (elapsed) | Expected state | Shippable? |
|---|---|---|
| 0:10 | Milestone 0–1 complete: `extensions.py` exists, 3 tests green, lint clean | No (seam not in loop yet) |
| 0:20 | Milestones 2–4: `loop.py` `run_turn` + enricher dispatch done, 6 tests green | Minimum shippable (partial) |
| 0:35 | Milestones 5–7: `_record_session` async + hooks dispatch done, 11 tests green | Yes — W1/W2/W4 can register hooks |
| 0:50 | Milestones 8–10: `app.py` + `stage.py` + `main.py` done, full suite green | Full W0 — all branches unblocked |
| 0:75 | Milestone 11: flag-off regression gate, lint clean, ready to merge | Ship |

### Collapse ladder (if behind at T)

- **Behind at T=0:20 (stuck on loop.py):** stop after Milestone 4 — `extensions.py`
  + `run_turn` enricher support is the minimum useful seam. W4's event_bus and
  W2/W1's on_outcome hooks will not be conflict-free, but W3 (Moss) still works.
  Do not merge if `_record_session` is not async yet.
- **Behind at T=0:35 (stuck on _record_session):** finish `_record_session` before
  `app.py`/`stage.py`. The stage router parametrization is the last cut — W4 can
  add it on its own branch if W0 omits it, at the cost of one manual merge point.
- **Minimum shippable W0:** `src/robin/extensions.py` (dataclass) + `loop.py`
  threading (`run_turn` hooks param + `_record_session` async + hook dispatch) +
  `tests/test_extensions.py` (Milestones 1–7) + `main.py` wiring block. That
  unblocks W1, W2, W3, and the core of W4.
- **Stage.py parametrization (Milestone 9) is the last cut.** W4 merges last and
  can add it atomically if W0 ships without it — the `>>> W4 <<<` marker in
  `main.py` is still present.

---

## Flag-off / No-op Regression Gate

Before opening the PR, run this exact sequence:

```bash
# 1. Full test suite — must be 100% green
docker compose run --rm robin pytest -q

# 2. Lint — must be clean
docker compose run --rm robin ruff check src tests

# 3. Confirm existing stage tests unmodified and green
docker compose run --rm robin pytest -q tests/test_stage.py -v

# 4. Confirm main wiring tests unmodified and green
docker compose run --rm robin pytest -q tests/test_main_wiring.py -v
```

No existing test file is modified by W0. If any of the above fail, do not merge.

---

## Merge Instructions

1. This branch is **the first to land on `main`** — open its PR first, get CI green,
   merge, and only then cut W1–W4 from the updated `main`.
2. PR title: `feat: inert extension seam (W0) — unblocks W1-W4`
3. Merge strategy: squash or merge commit — either is fine. Rebase is fine too.
4. After merging W0, cut new branches from the updated `main`:
   ```
   git fetch origin main
   git checkout -b feat/supermemory-recall origin/main    # W1
   git checkout -b feat/agentmail-closeloop origin/main   # W2
   git checkout -b feat/moss-statute-search origin/main   # W3
   git checkout -b feat/dashboard-flagship origin/main    # W4
   ```
5. Each feature branch inserts only its own `>>> Wn <<<` sub-block in `main.py`
   (and appends to `.env.example`, `requirements.txt`, `tests/fakes.py` in labeled
   blocks). Git auto-merges all four — no manual conflict resolution needed.

---

## Security / PII Checklist

- [ ] `src/robin/extensions.py` contains no secrets, no API keys, no phone numbers.
- [ ] `tests/test_extensions.py` uses only `call_id="c1"` / `"call_42"` / `"call_99"` synthetic IDs; no real E.164 numbers, no real names, no real emails.
- [ ] `hooks` parameter never logged; only the hook's error is logged (`repr(h)` of the callable, which is a function name — not PII).
- [ ] `event_bus` is never serialized or logged.
- [ ] No `.env`, `*.local.json`, recordings, or real transcript content staged.
- [ ] `tests/fakes.py` is append-only — W0 adds nothing to it (W1–W4 add their own `Fake*` clients there).
- [ ] Webhook signature verification in `signature.py` is untouched by W0.

---

*End of spec. Implementable end-to-end from this file + the working tree.*
