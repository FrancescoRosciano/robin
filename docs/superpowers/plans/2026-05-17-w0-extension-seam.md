# W0 Extension Seam — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land an inert, flag-free shared extension seam (ExtensionHooks injected through loop.py/app.py/stage.py/main.py) so W1–W4 become purely additive; with empty hooks the canonical gym-cancel demo is byte-identical to today.

**Architecture:** A new frozen `ExtensionHooks` dataclass (empty tuples + `event_bus=None` defaults) is threaded through `run_turn`, an async-converted `_record_session` (best-effort `on_research`/`on_outcome` hook dispatch), a prompt-enricher dispatch block in `run_turn`, a parametrized `make_stage_router` (defaults preserve current HTML/SSE byte-for-byte), and a delimited `main.py` wiring section with four labeled `>>> Wn <<<` insertion points. W0 mounts NOTHING — `/stage` stays unmounted exactly as today; W4 owns the flag-gated router mount. Every hook list is empty by default so every loop iterates zero times and produces zero side effects.

**Tech Stack:** Python 3.12, FastAPI, pytest + pytest-asyncio, Docker (all test/lint runs inside the container).

---

## File Structure

- `src/robin/extensions.py` — **NEW.** Frozen `ExtensionHooks` dataclass + three `Callable` type aliases (`PromptEnricher`, `ResearchHook`, `OutcomeHook`). The entire inert seam definition.
- `src/robin/loop.py` — **MODIFIED.** Import `ExtensionHooks`; `_record_session` becomes `async def` + gains `hooks` param + dispatches `on_research`/`on_outcome` best-effort; `run_turn` gains `hooks` keyword param + a prompt-enricher dispatch block after `effective_system`; call site awaits `_record_session(..., hooks)`.
- `src/robin/app.py` — **MODIFIED.** Import `ExtensionHooks`; `build_app` gains `hooks` keyword param threaded into the `run_turn(...)` call in the webhook route.
- `src/robin/stage.py` — **MODIFIED.** `make_stage_router` gains optional `event_bus=None` and `stage_html: str | None = None`; GET `/stage` serves `_html` (defaults to `_STAGE_HTML`); optional non-blocking `event_bus` drain in the SSE generator. Defaults ⇒ byte-identical to today. NO router mount added to `main.py`.
- `src/robin/main.py` — **MODIFIED.** Import `ExtensionHooks`; add delimited `# --- sponsor extension wiring ---` section with `_hooks = ExtensionHooks()` and four labeled `>>> Wn <<<` markers; pass `hooks=_hooks` to `build_app(...)`.
- `tests/test_extensions.py` — **NEW.** All W0 unit tests (dataclass shape, enricher ordering/empty-skip/raise-swallow, `on_research`/`on_outcome` payload + gating + raise-swallow, `build_app` threading, `make_stage_router` default/custom-HTML byte-identity). Synthetic IDs only.
- `tests/test_stage.py` — **UNTOUCHED** (must stay byte-identical and green throughout — regression gate).
- `tests/test_main_wiring.py` — **UNTOUCHED** (must stay byte-identical and green throughout — regression gate).

---

### Task 1: Scaffold `tests/test_extensions.py` (Milestone 0)

Create the test module with docstring, imports, and the shared `_make_msg` helper. No test functions yet — just the structure, so subsequent tasks add tests into a file that already lints. Note the `robin.extensions` import will resolve only after Task 2, so this file is committed alongside the first real test in Task 2; this task just lands the scaffold + lint check.

- [ ] **Step 1: Create the test scaffold file.** Write `tests/test_extensions.py` with exactly this content:

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


def _make_msg(texts: list[str], stop_reason: str):
    class _M:
        content = [{"type": "text", "text": t} for t in texts]
    _M.stop_reason = stop_reason
    return _M()
```

- [ ] **Step 2: Lint the scaffold (expected: import-resolution failure is acceptable here; flake only on syntax).** Run:

```
docker compose run --rm robin ruff check src tests
```

Expected: `ruff` may report unused imports / unresolved `robin.extensions` is NOT a ruff error (ruff does not resolve imports); the file must be **syntactically valid**. If ruff flags `F401` unused-import on `asyncio`/`pytest`/the seam names, that is expected at this scaffold stage and is resolved once Task 2+ tests use them — do not delete the imports. Confirm no `E999` syntax error.

- [ ] **Step 3: Commit the scaffold.** Run:

```
git add tests/test_extensions.py
git commit -m "test: scaffold W0 extension-seam test module"
```

---

### Task 2: `ExtensionHooks` dataclass + type aliases (Milestone 1)

Create `src/robin/extensions.py` so the seam type exists. RED → GREEN → REFACTOR → full-suite gate.

- [ ] **Step 1: Add the three RED tests for the dataclass.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the RED tests (expected: FAIL).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py
```

Expected: 3 failures — `ImportError` / collection error on `from robin.extensions import ...` because `src/robin/extensions.py` does not exist yet.

- [ ] **Step 3: Create `src/robin/extensions.py` (GREEN — full file).** Write `src/robin/extensions.py` with exactly this content:

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

- [ ] **Step 4: Run the tests (expected: PASS).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py
```

Expected: 3 passes.

- [ ] **Step 5: REFACTOR + full-suite gate.** Confirm the docstrings are complete and the type aliases use `Callable[[...], Awaitable[...]]` syntax (no behavioral change). Run the full regression gate:

```
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: full suite green (only `extensions.py` + the new test added; no existing file touched yet); ruff clean.

- [ ] **Step 6: Commit.** Run:

```
git add src/robin/extensions.py tests/test_extensions.py
git commit -m "feat: add inert ExtensionHooks dataclass + type aliases (W0)"
```

---

### Task 3: Thread `hooks` through `run_turn` + async `_record_session` (Milestone 2)

Add the `hooks` keyword to `run_turn`, the enricher dispatch block after `effective_system`, convert `_record_session` to `async def` with hook dispatch, and update the call site to `await`. This is the core seam edit to `loop.py`.

- [ ] **Step 1: Add the RED baseline-identity test.** Append to `tests/test_extensions.py`:

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
```

- [ ] **Step 2: Run the RED test (expected: FAIL).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py::test_run_turn_with_empty_hooks_output_identical_to_no_hooks
```

Expected: 1 failure — `TypeError: run_turn() got an unexpected keyword argument 'hooks'`.

- [ ] **Step 3: Add the `ExtensionHooks` import to `loop.py`.** In `src/robin/loop.py`, the import block currently is (lines 2–6 — there is NO `import re` in this file):

```python
import time
from typing import AsyncGenerator, Callable

from robin import obs, session
from robin.tools import TOOL_SCHEMAS
```

Add the seam import immediately after the `from robin.tools import TOOL_SCHEMAS` line (line 6) so the block becomes:

```python
import time
from typing import AsyncGenerator, Callable

from robin import obs, session
from robin.extensions import ExtensionHooks
from robin.tools import TOOL_SCHEMAS
```

- [ ] **Step 4: Convert `_record_session` to `async def` + add the `hooks` param and hook dispatch.** In `src/robin/loop.py`, `_record_session` currently is (lines 62–86):

```python
def _record_session(call_id: str | None, name: str, tool_input: dict,
                    out: object) -> None:
    """Persist tool outcomes into the per-call session so the NEXT webhook
    turn remembers them (AgentPhone's recentHistory carries no tool state).
    Deliberate, documented coupling to the three stable tool names — this
    is what stops Robin re-researching every turn and lets it progress to
    the dial. Best-effort: never raise into the call turn."""
    if not isinstance(out, dict):
        return
    try:
        if name == "research_cancellation_law" and out.get("status") == "OK":
            cites = out.get("citations") or []
            facts = "; ".join(
                f"{c.get('citation', '')}: {c.get('operative_quote', '')}"
                for c in cites if isinstance(c, dict))
            session.record_research(call_id, facts)
        elif name == "place_negotiation_call" and out.get("call_id"):
            session.mark_approved(call_id)
            session.mark_dial_placed(call_id, str(out.get("call_id")))
        elif name == "deliver_result" and out.get("delivered"):
            session.record_outcome(
                call_id, str(tool_input.get("summary", "delivered")))
    except Exception as exc:  # noqa: BLE001 - memory is best-effort, never fatal
        obs.log_event("session_record_error", call_id=call_id, name=name,
                       err=f"{type(exc).__name__}: {exc}")
```

Replace it entirely with:

```python
async def _record_session(call_id: str | None, name: str, tool_input: dict,
                          out: object, hooks: ExtensionHooks) -> None:
    """Persist tool outcomes into the per-call session so the NEXT webhook
    turn remembers them (AgentPhone's recentHistory carries no tool state).
    Deliberate, documented coupling to the three stable tool names — this
    is what stops Robin re-researching every turn and lets it progress to
    the dial. Best-effort: never raise into the call turn.

    After the session.* persist, dispatches the W0 extension hooks
    (best-effort, each individually guarded). Empty hook tuples == no-op."""
    if not isinstance(out, dict):
        return
    try:
        if name == "research_cancellation_law" and out.get("status") == "OK":
            cites = out.get("citations") or []
            facts = "; ".join(
                f"{c.get('citation', '')}: {c.get('operative_quote', '')}"
                for c in cites if isinstance(c, dict))
            session.record_research(call_id, facts)
        elif name == "place_negotiation_call" and out.get("call_id"):
            session.mark_approved(call_id)
            session.mark_dial_placed(call_id, str(out.get("call_id")))
        elif name == "deliver_result" and out.get("delivered"):
            session.record_outcome(
                call_id, str(tool_input.get("summary", "delivered")))
    except Exception as exc:  # noqa: BLE001 - memory is best-effort, never fatal
        obs.log_event("session_record_error", call_id=call_id, name=name,
                       err=f"{type(exc).__name__}: {exc}")

    # --- W0 outcome hooks (best-effort, no-op when empty) ---
    if name == "research_cancellation_law" and out.get("status") == "OK":
        for _hook in hooks.on_research:
            try:
                await _hook(call_id, out)
            except Exception as _exc:  # noqa: BLE001
                obs.log_event("extension_hook_error", call_id=call_id,
                               hook=repr(_hook),
                               err=f"{type(_exc).__name__}: {_exc}")
    elif name == "deliver_result" and out.get("delivered"):
        _payload = {
            "summary": str(tool_input.get("summary", "")),
            "confirmation": tool_input.get("confirmation"),
            "channel": tool_input.get("channel"),
            "out": out,
        }
        for _hook in hooks.on_outcome:
            try:
                await _hook(call_id, _payload)
            except Exception as _exc:  # noqa: BLE001
                obs.log_event("extension_hook_error", call_id=call_id,
                               hook=repr(_hook),
                               err=f"{type(_exc).__name__}: {_exc}")
    # --- end W0 outcome hooks ---
```

- [ ] **Step 5: Add the `hooks` keyword param to `run_turn`.** In `src/robin/loop.py`, `run_turn`'s signature currently is (lines 89–92):

```python
async def run_turn(transcript: str, history: list, *, system: str, llm,
                   tool_impls: dict[str, Callable],
                   call_id: str | None = None
                   ) -> AsyncGenerator[dict, None]:
```

Replace it with:

```python
async def run_turn(transcript: str, history: list, *, system: str, llm,
                   tool_impls: dict[str, Callable],
                   call_id: str | None = None,
                   hooks: ExtensionHooks = ExtensionHooks()
                   ) -> AsyncGenerator[dict, None]:
```

- [ ] **Step 6: Insert the prompt-enricher dispatch block after `effective_system`.** In `src/robin/loop.py`, the `effective_system` assembly currently is (lines 105–108):

```python
    mem = session.summary_for_prompt(call_id)
    effective_system = f"{system}\n\n{mem}" if mem else system
    obs.log_event("turn_start", call_id=call_id,
                   history=len(messages) - 1, mem=bool(mem))
```

Replace it with (insert the enricher block between the `effective_system =` line and the `obs.log_event("turn_start", ...)` call):

```python
    mem = session.summary_for_prompt(call_id)
    effective_system = f"{system}\n\n{mem}" if mem else system
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
    obs.log_event("turn_start", call_id=call_id,
                   history=len(messages) - 1, mem=bool(mem))
```

- [ ] **Step 7: Update the `_record_session` call site to `await`.** In `src/robin/loop.py`, the call site (currently `_record_session(call_id, name, tool_input, out)` — at loop.py:140 in the spec's numbering, inside the tool-execution loop) must become an awaited call passing `hooks`. Find the single line:

```python
            _record_session(call_id, name, tool_input, out)
```

Replace it with:

```python
            await _record_session(call_id, name, tool_input, out, hooks)
```

- [ ] **Step 8: Run the test (expected: PASS).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py::test_run_turn_with_empty_hooks_output_identical_to_no_hooks
```

Expected: 1 pass.

- [ ] **Step 9: Full-suite regression gate (critical — existing tests must not regress).** Run:

```
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: all green. If `test_loop.py` (or any loop test) breaks, confirm: (a) the `_record_session` call site was changed from `_record_session(...)` to `await _record_session(...)`, (b) `_record_session` is `async def`, (c) `run_turn` is still an `async def` generator, (d) the enricher block is between `effective_system =` and `obs.log_event("turn_start", ...)`. ruff must be clean.

- [ ] **Step 10: Commit.** Run:

```
git add src/robin/loop.py tests/test_extensions.py
git commit -m "feat: thread ExtensionHooks through run_turn + async _record_session (W0)"
```

---

### Task 4: Prompt-enricher ordering + empty-string skip (Milestone 3)

Verify enrichers append in registration order and that an empty-string return adds nothing. The dispatch code is already in place from Task 3; these tests pin its behavior.

- [ ] **Step 1: Add the two RED enricher tests.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the tests (expected: PASS — dispatch already implemented in Task 3).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "enricher"
```

Expected: 2 passes. If they fail, confirm the enricher dispatch block from Task 3 Step 6 is present between the `effective_system =` line and the `obs.log_event("turn_start", ...)` call, and that non-empty pieces are joined with `"\n\n"`.

- [ ] **Step 3: REFACTOR check.** Confirm no stray `_extra` variable leaks into the outer scope on the non-enricher path (it is defined inside the `if hooks.prompt_enrichers:` block only — verify visually). No behavioral change.

- [ ] **Step 4: Commit.** Run:

```
git add tests/test_extensions.py
git commit -m "test: pin prompt-enricher registration order + empty-skip (W0)"
```

---

### Task 5: Raising enricher is swallowed; turn completes (Milestone 4)

Verify that a per-enricher `try/except` (not a whole-loop guard) means one crashing enricher does not stop the next enricher or the turn.

- [ ] **Step 1: Add the RED test.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the test (expected: PASS — per-enricher guard already implemented in Task 3).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "raising_enricher"
```

Expected: 1 pass. If it fails, confirm the `try/except` in the enricher block wraps **only** the single `await _enricher(call_id)` (plus the `if _piece:` append), **not** the whole `for` loop. Adjust if the guard is loop-level rather than per-enricher.

- [ ] **Step 3: Commit.** Run:

```
git add tests/test_extensions.py
git commit -m "test: raising prompt-enricher is swallowed, turn completes (W0)"
```

---

### Task 6: `on_research` hook fires with exact payload + gating (Milestone 5)

Verify `on_research` fires with `(call_id, out_dict)` only when `name == "research_cancellation_law"` and `out["status"] == "OK"`, and never for other tools or non-OK status. Dispatch code is in place from Task 3.

- [ ] **Step 1: Add the three RED tests.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the tests (expected: PASS — `on_research` dispatch already implemented in Task 3).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "on_research"
```

Expected: 3 passes. If any fail, confirm the `on_research` block in `_record_session` (Task 3 Step 4) is gated by `name == "research_cancellation_law" and out.get("status") == "OK"` and passes the full `out` dict as the payload (`await _hook(call_id, out)`).

- [ ] **Step 3: Commit.** Run:

```
git add tests/test_extensions.py
git commit -m "test: on_research fires with exact payload + correct gating (W0)"
```

---

### Task 7: `on_outcome` hook fires with exact payload shape + gating (Milestone 6)

Verify `on_outcome` fires with the documented payload dict only when `name == "deliver_result"` and `out["delivered"]` is truthy. Dispatch code is in place from Task 3.

- [ ] **Step 1: Add the two RED tests.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the tests (expected: PASS — `on_outcome` dispatch already implemented in Task 3).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "on_outcome"
```

Expected: 2 passes. If any fail, confirm the `on_outcome` block in `_record_session` is gated by `name == "deliver_result" and out.get("delivered")` and builds the payload as `{"summary": str(tool_input.get("summary", "")), "confirmation": tool_input.get("confirmation"), "channel": tool_input.get("channel"), "out": out}`.

- [ ] **Step 3: Commit.** Run:

```
git add tests/test_extensions.py
git commit -m "test: on_outcome fires with exact payload shape + correct gating (W0)"
```

---

### Task 8: Raising research/outcome hooks are swallowed; turn still completes (Milestone 7)

Verify each `on_research`/`on_outcome` hook call is individually guarded so a crashing hook never propagates and subsequent hooks still run.

- [ ] **Step 1: Add the two RED tests.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the tests (expected: PASS — per-hook guard already implemented in Task 3).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "raising"
```

Expected: passes (this `-k "raising"` selector also re-runs `test_raising_enricher_is_swallowed_and_turn_completes` from Task 5 — all `raising` tests must pass). If the new two fail, confirm each hook call in `_record_session` is wrapped in its own `try/except` (per-hook, inside the `for _hook in ...` loop), not a single guard around the whole loop.

- [ ] **Step 3: Commit.** Run:

```
git add tests/test_extensions.py
git commit -m "test: raising research/outcome hooks are swallowed (W0)"
```

---

### Task 9: `build_app` threads `hooks` through to `run_turn` (Milestone 8)

Add `ExtensionHooks` import + `hooks` keyword param to `build_app` and thread it into the `run_turn(...)` call in the webhook route.

- [ ] **Step 1: Add the RED test.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the RED test (expected: FAIL).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "build_app_passes_hooks"
```

Expected: 1 failure — `build_app() got an unexpected keyword argument 'hooks'`.

- [ ] **Step 3: Add the `ExtensionHooks` import to `app.py`.** In `src/robin/app.py`, the import block currently is (lines 6–11):

```python
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from robin import obs
from robin.loop import run_turn
from robin.signature import MalformedJSONError, SignatureError, verify_signature
```

Add the seam import immediately after `from robin.loop import run_turn` (line 10) so the block becomes:

```python
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from robin import obs
from robin.extensions import ExtensionHooks
from robin.loop import run_turn
from robin.signature import MalformedJSONError, SignatureError, verify_signature
```

- [ ] **Step 4: Add the `hooks` keyword param to `build_app`.** In `src/robin/app.py`, `build_app`'s signature currently is (lines 21–22):

```python
def build_app(*, secret: str, law_html_path: str, llm: object,
              tool_impls: dict, system_prompt: str = "You are Robin.") -> FastAPI:
```

Replace it with:

```python
def build_app(*, secret: str, law_html_path: str, llm: object,
              tool_impls: dict, system_prompt: str = "You are Robin.",
              hooks: ExtensionHooks = ExtensionHooks()) -> FastAPI:
```

- [ ] **Step 5: Thread `hooks` into the `run_turn(...)` call.** In `src/robin/app.py`, the webhook route's `run_turn` call currently is (lines 61–65):

```python
        async def stream():
            async for chunk in run_turn(transcript, history,
                                        system=system_prompt, llm=llm,
                                        tool_impls=tool_impls,
                                        call_id=call_id):
                yield json.dumps(chunk) + "\n"
```

Replace it with:

```python
        async def stream():
            async for chunk in run_turn(transcript, history,
                                        system=system_prompt, llm=llm,
                                        tool_impls=tool_impls,
                                        call_id=call_id,
                                        hooks=hooks):
                yield json.dumps(chunk) + "\n"
```

- [ ] **Step 6: Run the test (expected: PASS).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "build_app_passes_hooks"
```

Expected: 1 pass.

- [ ] **Step 7: Full-suite regression gate.** Run:

```
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: all green (existing `test_app.py` / webhook tests still pass — `hooks` has a default so all existing `build_app(...)` callers are unaffected); ruff clean.

- [ ] **Step 8: Commit.** Run:

```
git add src/robin/app.py tests/test_extensions.py
git commit -m "feat: thread ExtensionHooks through build_app into run_turn (W0)"
```

---

### Task 10: Parametrize `make_stage_router` — default byte-identity (Milestone 9)

Add optional `event_bus` and `stage_html` params to `make_stage_router`. With defaults, the served HTML and SSE stream are byte-identical to today and `test_stage.py` stays green unmodified. **W0 does NOT add any router mount to `main.py`** — `/stage` remains unmounted exactly as today (a 404); W4 owns the mount.

- [ ] **Step 1: Add the three RED tests.** Append to `tests/test_extensions.py`:

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

- [ ] **Step 2: Run the RED tests (expected: FAIL).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "stage_router"
```

Expected: failures — `make_stage_router() got an unexpected keyword argument 'event_bus'`.

- [ ] **Step 3: Read `stage.py` to confirm exact lines, then parametrize the signature.** First read the current `make_stage_router` signature and GET handler:

```
docker compose run --rm robin python -c "import inspect, robin.stage as s; print(inspect.getsource(s.make_stage_router))"
```

In `src/robin/stage.py`, the signature (spec: line 102) currently is:

```python
def make_stage_router(broadcaster) -> APIRouter:
    """Build the /stage router bound to the given TurnBroadcaster instance."""
```

Replace it with:

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

- [ ] **Step 4: Serve `_html` from the GET `/stage` handler.** In `src/robin/stage.py` the GET handler (spec: line 107–108) currently returns:

```python
        return HTMLResponse(content=_STAGE_HTML)
```

Replace it with:

```python
        return HTMLResponse(content=_html)
```

- [ ] **Step 5: Add the optional non-blocking `event_bus` drain to the SSE generator.** In `src/robin/stage.py`, inside the SSE `event_generator` (the heartbeat/turn loop), after the existing `turn` event is emitted, add the optional drain. The existing heartbeat/turn loop stays entirely intact — only add this guarded block (it is a no-op when `event_bus is None`, which is the default):

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
                    # --- end W0 event_bus drain ---
```

NOTE: this drain snippet is **illustrative only** — it is not a correct multiplexing implementation as written (it re-subscribes per iteration). W4 owns the real multiplexed dashboard SSE design. W0's only hard requirement here is that with `event_bus=None` (the default) the generated SSE stream is **byte-identical** to today and all existing `test_stage.py` assertions pass unmodified. The exact `event_bus` placement is at the implementer's discretion — the gate is the default-path byte-identity, verified in Step 7. (If `json` / `asyncio` are not already imported in `stage.py`, add the import only inside this guarded path or at module top as needed, but only if the default-path tests still pass byte-identically.)

- [ ] **Step 6: Run the new tests (expected: PASS).** Run:

```
docker compose run --rm robin pytest -q tests/test_extensions.py -k "stage_router"
```

Expected: 3 passes.

- [ ] **Step 7: Confirm `test_stage.py` is byte-identical and green (regression gate).** First verify the file is unmodified:

```
git diff --quiet tests/test_stage.py && echo "test_stage.py UNMODIFIED" || echo "ERROR: test_stage.py changed"
```

Expected: `test_stage.py UNMODIFIED`. Then run it:

```
docker compose run --rm robin pytest -q tests/test_stage.py -v
```

Expected: all `test_stage.py` tests green, unmodified. If any fail, the default-path (`event_bus=None`, `stage_html=None`) behavior diverged — revert the SSE drain placement until the default stream is byte-identical.

- [ ] **Step 8: Commit.** Run:

```
git add src/robin/stage.py tests/test_extensions.py
git commit -m "feat: parametrize make_stage_router (event_bus + stage_html), defaults byte-identical (W0)"
```

---

### Task 11: `main.py` sponsor-extension wiring block (Milestone 10)

Add the `ExtensionHooks` import, the delimited wiring section with the four labeled `>>> Wn <<<` markers, and thread `hooks=_hooks` into `build_app(...)`. No behavioral test (main.py needs every env var monkeypatched — covered by `test_main_wiring.py`); the gate is a syntax/import check + `test_main_wiring.py` staying green.

- [ ] **Step 1: Read the end of `main.py` to confirm exact lines and the absence of any stage mount.** Run:

```
docker compose run --rm robin python -c "import pathlib; t=pathlib.Path('src/robin/main.py').read_text(); print(t)"
```

Confirm: there is NO `from robin.stage import ...` and NO `app.include_router(...)` anywhere in `main.py` (W0 must NOT add one — `/stage` stays unmounted, which is the correct flag-off behavior; W4 owns the mount). The end of the file (spec: lines 60–63) is:

```python
app = build_app(
    secret=_settings.agentphone_webhook_secret,
    law_html_path=LAW_HTML_PATH, llm=_llm, tool_impls=_tool_impls,
    system_prompt=render_inbound_system_prompt(_pack))
```

- [ ] **Step 2: Add the import + delimited wiring section + thread `hooks=_hooks` into `build_app`.** In `src/robin/main.py`, replace the final `app = build_app(...)` block shown above with the import line, the delimited wiring section, and the `hooks=_hooks` keyword (insert the import and wiring section immediately before the `app = build_app(` call, after the existing line 63 context):

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

(If `main.py`'s style places all imports at the top of the file, move the `from robin.extensions import ExtensionHooks` line up into the existing top-of-file import block instead of immediately before the wiring section — but keep the wiring section + `hooks=_hooks` exactly as shown. The four `>>> Wn <<<` lines must be distinct, in this order, so each feature branch's git insertion auto-merges.)

- [ ] **Step 3: Verify syntax + import + existing wiring tests (gate).** First confirm `main.py` parses and the seam imports:

```
docker compose run --rm robin python -c "import ast, pathlib; ast.parse(pathlib.Path('src/robin/main.py').read_text()); print('syntax OK')"
```

Expected: `syntax OK`. Then confirm `test_main_wiring.py` is unmodified:

```
git diff --quiet tests/test_main_wiring.py && echo "test_main_wiring.py UNMODIFIED" || echo "ERROR: test_main_wiring.py changed"
```

Expected: `test_main_wiring.py UNMODIFIED`. Then run it:

```
docker compose run --rm robin pytest -q tests/test_main_wiring.py
docker compose run --rm robin ruff check src tests
```

Expected: all green. If `test_main_wiring.py::test_tool_impls_has_exact_keys` (or similar) fails, confirm `app = build_app(...)` is not passing an unknown kwarg — only `hooks=_hooks` was added, and `build_app` accepts `hooks` (from Task 9). ruff clean.

- [ ] **Step 4: Commit.** Run:

```
git add src/robin/main.py
git commit -m "feat: add delimited sponsor-extension wiring block + thread hooks (W0)"
```

---

### Task 12: Flag-off / no-op regression gate (Milestone 11 — final gate before merge)

The complete inert-seam proof: full suite green, lint clean, and the two pinned regression files (`test_stage.py`, `test_main_wiring.py`) byte-identical and green. With `ExtensionHooks()` defaults the gym-cancel demo is byte-identical to pre-W0 `main`. This is the collapse-ladder floor — do not merge if any step here fails.

- [ ] **Step 1: Full test suite — must be 100% green.** Run:

```
docker compose run --rm robin pytest -q
```

Expected: every existing test green + the new `tests/test_extensions.py` (~19 tests across Tasks 2–10) green. Zero regressions.

- [ ] **Step 2: Lint — must be clean.** Run:

```
docker compose run --rm robin ruff check src tests
```

Expected: clean (no errors). The `# noqa: BLE001` comments on the broad `except Exception` guards in `loop.py` are intentional and required (best-effort hook isolation).

- [ ] **Step 3: Confirm existing stage tests unmodified and green.** Run:

```
git diff --quiet tests/test_stage.py && echo "test_stage.py UNMODIFIED" || echo "ERROR: test_stage.py changed"
docker compose run --rm robin pytest -q tests/test_stage.py -v
```

Expected: `test_stage.py UNMODIFIED` and all its tests green.

- [ ] **Step 4: Confirm main wiring tests unmodified and green.** Run:

```
git diff --quiet tests/test_main_wiring.py && echo "test_main_wiring.py UNMODIFIED" || echo "ERROR: test_main_wiring.py changed"
docker compose run --rm robin pytest -q tests/test_main_wiring.py -v
```

Expected: `test_main_wiring.py UNMODIFIED` and all its tests green. No existing test file is modified by W0 — if any of the above fail, **do not merge**.

- [ ] **Step 5: Security / PII checklist (self-review the diff before opening the PR).** Run `git diff main...HEAD` (or review staged history) and confirm every item:
  - `src/robin/extensions.py` contains no secrets, no API keys, no phone numbers.
  - `tests/test_extensions.py` uses only `call_id="c1"` / `"call_42"` / `"call_99"` / `"c_hook_test"` synthetic IDs; no real E.164 numbers, no real names, no real emails.
  - `hooks` is never logged; only the hook's error is logged via `obs.log_event("extension_hook_error", ..., hook=repr(_hook), ...)` (a function `repr`, not PII).
  - `event_bus` is never serialized or logged.
  - No `.env`, `*.local.json`, recordings, or real transcript content staged.
  - `tests/fakes.py` is untouched by W0 (W1–W4 add their own `Fake*` clients there).
  - `src/robin/signature.py` is untouched by W0 (webhook Svix verification unchanged).

- [ ] **Step 6: Final no-op commit gate (no-op if nothing left to stage).** Confirm the working tree is clean and the branch is ready:

```
git status --porcelain
```

Expected: empty output (everything committed in Tasks 2–11). If anything is unstaged, it must be intentional and committed with a conventional message before merge.

---

### Task 13: Merge — W0 lands on `main` FIRST; W1–W4 cut from post-W0 `main`

W0 is the first branch to land on `main`. Open and merge its PR before any W1–W4 work begins. After W0 is on `main`, the only file W1–W4 share is `main.py`, and only via the distinct labeled `>>> Wn <<<` sub-blocks → git auto-merges with no manual conflict resolution.

- [ ] **Step 1: Open the W0 PR first.** PR title: `feat: inert extension seam (W0) — unblocks W1-W4`. PR body must reference the flag-off regression gate (Task 12) and state that no existing test file is modified. Merge strategy: squash, merge commit, or rebase — any is fine. **Do not `git push` from inside the agent (denied in repo settings); the human performs the push and opens/merges the PR.** Wait for CI green, then merge to `main`.

- [ ] **Step 2: After W0 is merged, cut the four feature branches from updated `main`.** Once W0 is on `main`, the human (or the next session) runs:

```
git fetch origin main
git checkout -b feat/supermemory-recall origin/main    # W1
git checkout -b feat/agentmail-closeloop origin/main   # W2
git checkout -b feat/moss-statute-search origin/main   # W3
git checkout -b feat/dashboard-flagship origin/main    # W4
```

Each feature branch inserts **only its own** `>>> Wn <<<` sub-block in `main.py` (rebuilding `_hooks` immutably, e.g. `_hooks = ExtensionHooks(*<existing fields>, prompt_enrichers=(_hooks.prompt_enrichers + (my_fn,)))`) and appends to `.env.example` / `requirements.txt` / `tests/fakes.py` in its own labeled blocks. The four labeled marker lines are distinct git lines ⇒ git auto-merges all four; no manual conflict resolution is required. W4 additionally owns adding the flag-gated `app.include_router(make_stage_router(...))` mount inside its `>>> W4 <<<` sub-block — with `ROBIN_DASHBOARD_ENHANCED` unset, `/stage` remains unmounted exactly as today (a 404), the required no-op.

---

## Collapse Ladder (if behind on the clock)

Build/merge in milestone order; every prefix is shippable and the canonical gym-cancel demo is never touched. Time-box reference: Task 1–2 (~0:10), Tasks 3–5 (~0:20), Tasks 6–8 (~0:35), Tasks 9–11 (~0:50), Task 12 (~0:75).

- **Behind at ~0:20 (stuck on `loop.py`):** stop after Task 5 — `extensions.py` + `run_turn` enricher support is the minimum useful seam. W4's `event_bus` and W1/W2's `on_outcome` hooks will not yet be conflict-free, but W3 (Moss) still works. **Do not merge if `_record_session` is not async yet** (a partial `loop.py` with a sync `_record_session` and an awaited call site is broken).
- **Behind at ~0:35 (stuck on `_record_session`):** finish `_record_session` (Tasks 6–8) before touching `app.py`/`stage.py`. The stage-router parametrization is the last cut — W4 can add it on its own branch if W0 omits it, at the cost of one manual merge point.
- **Minimum shippable W0:** `src/robin/extensions.py` (dataclass) + `loop.py` threading (`run_turn` hooks param + `_record_session` async + hook dispatch) + `tests/test_extensions.py` (Tasks 2–8) + `main.py` wiring block (Task 11). That unblocks W1, W2, W3, and the core of W4.
- **Stage.py parametrization (Task 10) is the last cut.** W4 merges last and can add it atomically if W0 ships without it — the `>>> W4 <<<` marker in `main.py` is still present, so W4 stays unblocked.
- A half-done branch is never merged. The flag-off regression gate (Task 12) is the merge floor regardless of where the collapse ladder stops: full suite green + ruff clean + `test_stage.py`/`test_main_wiring.py` byte-identical and green.
