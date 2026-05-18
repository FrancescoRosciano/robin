# W1 — `feat/supermemory-recall` Spec + Plan

**Branch:** `feat/supermemory-recall`
**Date:** 2026-05-17
**Size:** M — ~2 h
**Depends on:** W0 (`feat/extension-seam`) merged to `main` first
**Status:** ready to implement — do NOT begin until W0 is green on `main`

---

## Goal

Robin remembers callers across calls. When a return caller rings in,
Robin opens with context like:

> "Welcome back — last time we cancelled your 24 Hour Gym membership
> and got you a last-month refund. What do you need handled today?"

W1 stores each call's outcome in Super Memory (keyed by caller phone
number) and fetches the same caller's prior outcomes + winning tactics
before the first substantive turn. The recall is injected into the
system prompt as a `[CALLER HISTORY]` block; the canonical gym-cancel
path is **byte-identical with the flag off** (the default).

---

## Orientation

### Portfolio fit

This file is self-contained. It is one of four purely-additive feature
branches layered on top of the W0 extension seam. Read §1 of the master
design for the full isolation contract; the relevant parts are restated
below.

### Isolation contract (from the master design — must be obeyed)

1. **Flag-off = no-op, byte-identical.** Feature is gated by
   `ROBIN_MEMORY_ENABLED=1`. When absent (the default), the full
   existing test suite is green and the canonical gym-cancel path is
   unchanged.
2. **Graceful no-op on any failure.** Missing key, SDK unavailable,
   timeout, or any exception → behave exactly as today, emit one
   `obs.log_event(...)` breadcrumb, never raise into the call turn.
3. **New code in new files only.** This branch adds
   `src/robin/integrations/__init__.py`,
   `src/robin/integrations/supermemory.py`, and
   `tests/test_supermemory.py`. It appends to `tests/fakes.py`,
   `.env.example`, and `requirements.txt`. It writes **only** the
   `>>> W1 supermemory wiring <<<` sub-block in `main.py`. It does NOT
   edit `loop.py`, `app.py`, `stage.py`, `models.py`, `classifier.py`,
   `signature.py`, or any locked fixture.
4. **Constructor injection + fake.** `FakeSupermemoryClient` appended to
   `tests/fakes.py`; the integration module accepts the client as an
   argument (or uses the module-level singleton when called from main.py).
5. **Hard time-box + collapse ladder.** Stated at end of this document.
6. **Security.** `SUPERMEMORY_API_KEY` only from env; never logged,
   never in tests; tests use synthetic `p1555...` container tags only.

### The W0 API you build on

After W0 is on `main`, the following symbols exist:

```python
# src/robin/extensions.py
from dataclasses import dataclass
from typing import Awaitable, Callable

PromptEnricher = Callable[[str | None], Awaitable[str]]
ResearchHook   = Callable[[str | None, dict], Awaitable[None]]
OutcomeHook    = Callable[[str | None, dict], Awaitable[None]]

@dataclass(frozen=True)
class ExtensionHooks:
    prompt_enrichers: tuple[PromptEnricher, ...] = ()
    on_research:      tuple[ResearchHook, ...] = ()
    on_outcome:       tuple[OutcomeHook, ...] = ()
    event_bus:        object | None = None
```

A `PromptEnricher` is `async (call_id: str | None) -> str`. Return `""`
to contribute nothing; return a non-empty string and it is appended to
`effective_system` in `run_turn` (loop.py) with a blank-line separator.

An `OutcomeHook` is `async (call_id: str | None, payload: dict) -> None`.
The payload for the `deliver_result` moment is:
```python
{
    "summary":      str(tool_input.get("summary", "")),
    "confirmation": tool_input.get("confirmation"),   # str | None
    "channel":      tool_input.get("channel"),        # str | None
    "out":          out,                               # the tool's return dict
}
```

Both hook types must return quickly (< ~200 ms) and must never raise.
Long network work is self-scheduled via `asyncio.create_task(...)`;
the hook itself returns immediately.

**`main.py` composition root (post-W0):**

```python
# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<
# >>> W2 agentmail wiring   <<<
# >>> W3 moss wiring        <<<
# >>> W4 dashboard wiring   <<<
# --- end sponsor extension wiring ---
```

W1 inserts its real code **only** inside the `>>> W1 supermemory wiring
<<<` marker.  The other markers are untouched.

**`build_app` signature (post-W0):**

```python
def build_app(*, secret, law_html_path, llm, tool_impls,
              system_prompt="You are Robin.",
              hooks: ExtensionHooks = ExtensionHooks()) -> FastAPI:
```

W0 threads `hooks` into `run_turn(...)` in the webhook route.

---

## Caller key: `container_tag` derivation

The Super Memory key for a caller is their E.164 phone number with `+`
replaced by `p` (required: `container_tag` must match `[A-Za-z0-9._-]`,
max 100 chars). The `+` sign is invalid in that charset.

**Source field:** `pack.callback_number` from `ContextPack`
(`src/robin/models.py:8`). This is the E.164 number Robin calls back —
i.e., the caller's own number. In the real demo it comes from
`context_pack.json`; in tests it uses synthetic `+1555...` values.

Derivation:
```python
def _sanitize_tag(number: str) -> str:
    tag = number.replace("+", "p").strip()
    return tag[:100]  # hard cap; E.164 is at most 15 digits + "p" = 16 chars
```

Example: `+14155551234` → `p14155551234` (16 chars, well within 100).

The enricher and the persist hook both use the same derivation. There is
no `call_id`-based fallback — `callback_number` is always known at
composition time (it is validated and required by `load_context_pack`).

---

## Super Memory SDK contract

**Package:** `supermemory>=3.42.0` (append to `requirements.txt`)
**Import:** `from supermemory import AsyncSupermemory`
**Auth env var:** `SUPERMEMORY_API_KEY` (key from console.supermemory.ai)
**Feature flag:** `ROBIN_MEMORY_ENABLED` (must equal `"1"` to activate)

### Client construction (module-level singleton)

```python
import os
from supermemory import AsyncSupermemory

_client: AsyncSupermemory | None = None

def _get_client() -> AsyncSupermemory | None:
    global _client
    if os.environ.get("ROBIN_MEMORY_ENABLED") != "1":
        return None
    key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not key:
        return None
    if _client is None:
        _client = AsyncSupermemory(api_key=key, timeout=1.5, max_retries=0)
    return _client
```

- Timeout **1.5 s** (overrides the 60 s default) — the full enricher
  budget is 800 ms but we set the SDK timeout slightly above to allow
  the `asyncio.wait_for` to fire first.
- `max_retries=0` — no silent retry storms on stage.
- Singleton initialised lazily so tests that do not set env vars never
  touch the real SDK.

### READ — hot path, called at turn start

```python
import asyncio
from supermemory import AsyncSupermemory

async def _fetch_history(client: AsyncSupermemory, tag: str) -> str:
    try:
        result = await asyncio.wait_for(
            client.search.documents(
                q="prior call outcomes, gym, cancellation tactics, caller preferences",
                container_tag=tag,
                limit=5,
                chunk_threshold=0.3,
                rerank=False,
                rewrite_query=False,
            ),
            timeout=0.8,
        )
        items = getattr(result, "results", []) or []
        if not items:
            return ""
        lines = []
        for item in items:
            text = getattr(item, "content", None) or getattr(item, "memory", "")
            if text:
                lines.append(f"- {text.strip()}")
        if not lines:
            return ""
        return "[CALLER HISTORY]\n" + "\n".join(lines)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        obs.log_event("memory_fetch_timeout_or_error", tag=tag)
        return ""
```

**Budget:** 800 ms hard cap via `asyncio.wait_for`. On `TimeoutError`
or any `Exception` → return `""` (no enrichment, no raise).

### WRITE — fire-and-forget, called after outcome

```python
async def _persist(client: AsyncSupermemory, tag: str,
                   summary: str, confirmation: str | None) -> None:
    content = summary
    if confirmation:
        content += f" | confirmation={confirmation}"
    try:
        await client.add(
            content=content,
            container_tag=tag,
            metadata={"confirmation": confirmation or ""},
        )
        obs.log_event("memory_persist_ok", tag=tag)
    except Exception as exc:  # noqa: BLE001
        obs.log_event("memory_persist_error", tag=tag,
                      err=f"{type(exc).__name__}: {exc}")
```

- Called via `asyncio.create_task(_persist(...))` so the outcome hook
  returns immediately (< ~200 ms contract).
- Best-effort only: any exception is swallowed and logged.
- `client.add` returns status `"queued"` immediately (the SDK does not
  block on indexing).

---

## Files to create / modify

### New: `src/robin/integrations/__init__.py`

Empty. Makes `integrations` a proper package.

### New: `src/robin/integrations/supermemory.py`

Full module. Public API surface consumed by `main.py`:

```python
def make_recall_enricher(client, tag: str) -> PromptEnricher:
    """Return an enricher that fetches caller history from Super Memory."""
    ...

def make_persist_outcome_hook(client, tag: str) -> OutcomeHook:
    """Return an outcome hook that fire-and-forgets a persist task."""
    ...
```

The module also exposes `_get_client()` and `_sanitize_tag()` for tests.

Full structure (the engineer writes the actual implementation):

```
src/robin/integrations/supermemory.py
├── imports (asyncio, os, supermemory, robin.obs, robin.extensions)
├── _ENABLED / _client singleton + _get_client()
├── _sanitize_tag(number: str) -> str
├── _fetch_history(client, tag) -> str          [async, 800 ms budget]
├── _persist(client, tag, summary, confirmation) [async, best-effort]
├── make_recall_enricher(client, tag) -> PromptEnricher
└── make_persist_outcome_hook(client, tag) -> OutcomeHook
```

**Important invariant:** every code path in this module that is
reachable when `ROBIN_MEMORY_ENABLED` is unset or `SUPERMEMORY_API_KEY`
is absent must be a no-op that returns `""` (enricher) or `None`
(outcome hook) without making any network call.

### Append to `tests/fakes.py`

```python
# --- W1: FakeSupermemoryClient ---

class _FakeSearchResult:
    def __init__(self, content: str, similarity: float = 0.9):
        self.content = content
        self.memory = content
        self.similarity = similarity


class _FakeSearchResponse:
    def __init__(self, items: list[str]):
        self.results = [_FakeSearchResult(t) for t in items]


class _FakeSearchNamespace:
    def __init__(self, items: list[str], raise_exc: Exception | None = None):
        self._items = items
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def documents(self, *, q, container_tag, limit=5,
                        chunk_threshold=0.3, rerank=False,
                        rewrite_query=False):
        self.calls.append({"q": q, "container_tag": container_tag})
        if self._raise:
            raise self._raise
        return _FakeSearchResponse(self._items)


class FakeSupermemoryClient:
    """Scriptable fake for AsyncSupermemory.

    Usage:
        client = FakeSupermemoryClient(items=["- Cancelled 24 Hour Gym"])
        # or: client = FakeSupermemoryClient(items=[], raise_exc=TimeoutError())
    """

    def __init__(self, items: list[str] = (), *,
                 raise_exc: Exception | None = None,
                 add_raise: Exception | None = None):
        self.search = _FakeSearchNamespace(list(items), raise_exc)
        self._add_raise = add_raise
        self.added: list[dict] = []

    async def add(self, *, content: str, container_tag: str,
                  metadata: dict | None = None):
        if self._add_raise:
            raise self._add_raise
        self.added.append({"content": content, "container_tag": container_tag,
                           "metadata": metadata})
        return {"status": "queued"}
```

### Edit `main.py` — W1 sub-block only

Replace the marker line:

```python
# >>> W1 supermemory wiring <<<
```

with:

```python
# >>> W1 supermemory wiring <<<
if os.environ.get("ROBIN_MEMORY_ENABLED") == "1":
    from robin.integrations.supermemory import (
        _get_client, _sanitize_tag,
        make_recall_enricher, make_persist_outcome_hook,
    )
    _sm_client = _get_client()
    if _sm_client is not None:
        _sm_tag = _sanitize_tag(_pack.callback_number)
        _recall = make_recall_enricher(_sm_client, _sm_tag)
        _persist_outcome = make_persist_outcome_hook(_sm_client, _sm_tag)
        _hooks = ExtensionHooks(
            prompt_enrichers=_hooks.prompt_enrichers + (_recall,),
            on_outcome=_hooks.on_outcome + (_persist_outcome,),
            on_research=_hooks.on_research,
            event_bus=_hooks.event_bus,
        )
        obs.log_event("supermemory_enabled", tag=_sm_tag)
# >>> end W1 <<<
```

Note: `_hooks` is rebuilt immutably (new `ExtensionHooks` instance).
The existing `on_research` and `event_bus` tuples are forwarded
unchanged. `ExtensionHooks` is a frozen dataclass so no in-place
mutation occurs.

### Append to `.env.example`

Under the `# --- Optional sponsor hooks ---` block:

```
# --- W1: Super Memory (caller history recall) ---
ROBIN_MEMORY_ENABLED=
SUPERMEMORY_API_KEY=
```

### Append to `requirements.txt`

```
supermemory>=3.42.0
```

---

## Exact seams (file : line)

These are the exact locations to read and modify. Line numbers are from
the post-W0 working tree; they may shift by a few lines after W0 lands.
Verify with `grep -n` before editing.

| File | Location | Action |
|---|---|---|
| `main.py` | line containing `# >>> W1 supermemory wiring <<<` | Replace marker with the W1 wiring block above |
| `main.py` | top-of-file imports | Add `import os` if not already present (it is: `main.py:3`) |
| `main.py` | after `_hooks = ExtensionHooks()` line | The W1 block reads `_pack.callback_number` — `_pack` is defined at line 22; the W1 block must come after it |
| `tests/fakes.py` | end of file | Append `FakeSupermemoryClient` block verbatim |
| `.env.example` | end of file | Append W1 env vars |
| `requirements.txt` | end of file | Append `supermemory>=3.42.0` |

**In scope (W1 creates):**
- `src/robin/integrations/__init__.py` (empty)
- `src/robin/integrations/supermemory.py`
- `tests/test_supermemory.py`

**Out of scope (W1 never touches):**
- `src/robin/loop.py`
- `src/robin/app.py`
- `src/robin/stage.py`
- `src/robin/models.py`
- `src/robin/classifier.py`
- `src/robin/signature.py`
- `src/robin/fixtures/` (any file)
- Any other existing test file

---

## TDD Plan: RED → GREEN → REFACTOR

All test commands run inside Docker. Do not run on the host Python.

### Milestone 0 — scaffold (no tests yet, ~5 min)

```bash
# Verify W0 is on main and the full suite is green
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Create the empty `integrations/` package:

```bash
mkdir -p /path/to/robin/src/robin/integrations
touch /path/to/robin/src/robin/integrations/__init__.py
```

Create the stub `supermemory.py` (all public functions present,
all bodies `raise NotImplementedError`):

```python
# src/robin/integrations/supermemory.py  — STUB
async def _fetch_history(client, tag): raise NotImplementedError
async def _persist(client, tag, summary, confirmation): raise NotImplementedError
def make_recall_enricher(client, tag): raise NotImplementedError
def make_persist_outcome_hook(client, tag): raise NotImplementedError
def _get_client(): raise NotImplementedError
def _sanitize_tag(number): raise NotImplementedError
```

Append `FakeSupermemoryClient` to `tests/fakes.py` (copy verbatim from
the block in the "Files to create / modify" section above).

Create `tests/test_supermemory.py` — empty for now, one placeholder:

```python
# tests/test_supermemory.py
def test_placeholder():
    pass
```

Verify import works:

```bash
docker compose run --rm robin python -c \
    "from tests.fakes import FakeSupermemoryClient; print('ok')"
```

---

### Milestone 1 — flag-off / no-key no-ops [RED → GREEN]

**RED — write these tests first:**

```python
# tests/test_supermemory.py  (replace placeholder)
import os
import pytest

pytestmark = pytest.mark.asyncio

async def test_enricher_returns_empty_string_when_flag_off(monkeypatch):
    """Flag absent → enricher no-ops → empty string, no network call."""
    monkeypatch.delenv("ROBIN_MEMORY_ENABLED", raising=False)
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=["some history"])
    enricher = make_recall_enricher(client, "p15550001234")
    result = await enricher(call_id="call_test")
    assert result == ""
    assert client.search.calls == []  # no network call made


async def test_persist_hook_is_noop_when_flag_off(monkeypatch):
    """Flag absent → outcome hook no-ops → no add() call, no exception."""
    monkeypatch.delenv("ROBIN_MEMORY_ENABLED", raising=False)
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    from robin.integrations.supermemory import make_persist_outcome_hook
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient()
    hook = make_persist_outcome_hook(client, "p15550001234")
    await hook(call_id="call_test",
               payload={"summary": "cancelled", "confirmation": "24HF-4471",
                        "channel": None, "out": {"delivered": True}})
    assert client.added == []


async def test_enricher_returns_empty_string_when_key_absent(monkeypatch):
    """Flag set but no key → enricher no-ops."""
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    enricher = make_recall_enricher(FakeSupermemoryClient(), "p15550001234")
    assert await enricher(call_id=None) == ""
```

**Run (expect failures):**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

**GREEN — implement** `_sanitize_tag`, `_get_client`, and the no-op
guards in `make_recall_enricher` / `make_persist_outcome_hook`. The
simplest implementation: each factory function checks whether the
supplied `client` is `None`; when the client is `None`, the returned
enricher/hook is a stub that returns `""` / `None` immediately without
calling `_fetch_history` or `_persist`.

Specifically, the factories take the already-resolved client as an
argument (the real client or a fake); `None` means disabled. In
`main.py`, `_get_client()` is called first and its result (possibly
`None`) is passed to the factories. Tests pass a `FakeSupermemoryClient`
or `None` directly — no env var needed to test the no-op path.

Re-run:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

All three tests must pass.

---

### Milestone 2 — enricher formats recall block [RED → GREEN]

**RED:**

```python
async def test_enricher_formats_history_block(monkeypatch):
    """Enricher with history items returns a [CALLER HISTORY] block."""
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=[
        "Cancelled 24 Hour Gym membership. Last-month refund. conf=24HF-4471",
        "Caller prefers no hold music",
    ])
    enricher = make_recall_enricher(client, "p14155551234")
    result = await enricher(call_id="call_abc")
    assert result.startswith("[CALLER HISTORY]")
    assert "24HF-4471" in result
    assert "hold music" in result
    # Search was called with the right tag
    assert client.search.calls[0]["container_tag"] == "p14155551234"


async def test_enricher_returns_empty_string_when_no_results():
    """Zero results → empty string (no header block)."""
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=[])
    enricher = make_recall_enricher(client, "p14155550000")
    assert await enricher(call_id="call_xyz") == ""
```

**Run (expect failures):**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

**GREEN — implement** `_fetch_history` using the FakeSupermemoryClient
interface. The fake's `search.documents(...)` returns a
`_FakeSearchResponse` with `.results` list; items have `.content`.

Re-run:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

---

### Milestone 3 — enricher timeout / error resilience [RED → GREEN]

**RED:**

```python
async def test_enricher_returns_empty_string_on_timeout():
    """asyncio.TimeoutError from fetch → return "" (never raise)."""
    import asyncio
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(items=[], raise_exc=asyncio.TimeoutError())
    enricher = make_recall_enricher(client, "p15550009999")
    result = await enricher(call_id="call_timeout")
    assert result == ""


async def test_enricher_returns_empty_string_on_api_error():
    """Any exception from the SDK → return "" (never raise)."""
    from robin.integrations.supermemory import make_recall_enricher
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(
        items=[], raise_exc=RuntimeError("SDK unavailable"))
    enricher = make_recall_enricher(client, "p15550008888")
    result = await enricher(call_id="call_error")
    assert result == ""
```

**Run (expect failures):**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

**GREEN — wrap** `_fetch_history` in `try/except (asyncio.TimeoutError,
Exception)` returning `""`. Also wrap the `asyncio.wait_for(...)` call
with a 0.8 s timeout.

Re-run:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

---

### Milestone 4 — persist hook schedules task and returns fast [RED → GREEN]

**RED:**

```python
async def test_persist_hook_schedules_task_and_returns_immediately():
    """Outcome hook must return without awaiting the persist network call."""
    import asyncio
    from robin.integrations.supermemory import make_persist_outcome_hook
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient()
    hook = make_persist_outcome_hook(client, "p14155557777")
    payload = {"summary": "Cancelled gym. Got refund.", "confirmation": "24HF-4471",
               "channel": "voice", "out": {"delivered": True}}
    # The hook itself must return before client.add is awaited
    await hook(call_id="call_abc", payload=payload)
    # After draining the event loop, the task should have run
    await asyncio.sleep(0)  # let the scheduled task execute
    assert len(client.added) == 1
    assert "24HF-4471" in client.added[0]["content"]
    assert client.added[0]["container_tag"] == "p14155557777"


async def test_persist_hook_never_raises_on_add_failure():
    """add() raising must be swallowed; hook must not propagate."""
    import asyncio
    from robin.integrations.supermemory import make_persist_outcome_hook
    from tests.fakes import FakeSupermemoryClient
    client = FakeSupermemoryClient(add_raise=RuntimeError("storage down"))
    hook = make_persist_outcome_hook(client, "p15550006666")
    # Must not raise
    await hook(call_id="call_fail",
               payload={"summary": "test", "confirmation": None,
                        "channel": None, "out": {}})
    await asyncio.sleep(0)
    # No assert needed; the test passing means no exception was propagated
```

**Run (expect failures):**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

**GREEN — implement** `make_persist_outcome_hook`. The returned hook
extracts `summary` and `confirmation` from `payload`, then calls
`asyncio.create_task(_persist(client, tag, summary, confirmation))`
and returns. `_persist` wraps `client.add(...)` in `try/except`.

Re-run:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

---

### Milestone 5 — container_tag sanitization [RED → GREEN]

**RED:**

```python
def test_sanitize_tag_replaces_plus_with_p():
    from robin.integrations.supermemory import _sanitize_tag
    assert _sanitize_tag("+14155551234") == "p14155551234"


def test_sanitize_tag_caps_at_100_chars():
    from robin.integrations.supermemory import _sanitize_tag
    long_number = "+1" + "5" * 120
    tag = _sanitize_tag(long_number)
    assert len(tag) <= 100


def test_sanitize_tag_no_plus_unchanged():
    from robin.integrations.supermemory import _sanitize_tag
    assert _sanitize_tag("p15555550000") == "p15555550000"
```

**Run (expect failures):**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

**GREEN — implement** `_sanitize_tag` (three lines).

Re-run:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

---

### Milestone 6 — main.py wiring (integration smoke) [RED → GREEN]

Write a wiring smoke test that exercises the W1 main.py sub-block logic
without importing the real `main.py` (which requires a valid
`context_pack.json` and all env vars):

```python
async def test_main_wiring_w1_builds_enriched_hooks(monkeypatch):
    """When ROBIN_MEMORY_ENABLED=1 and a fake client is injected,
    _hooks gains one enricher and one outcome hook."""
    import os
    monkeypatch.setenv("ROBIN_MEMORY_ENABLED", "1")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "fake-key-for-test")
    from robin.extensions import ExtensionHooks
    from robin.integrations.supermemory import (
        _sanitize_tag, make_recall_enricher, make_persist_outcome_hook,
    )
    from tests.fakes import FakeSupermemoryClient

    # Simulate the composition-root block
    sm_client = FakeSupermemoryClient(items=["prior call: gym cancelled"])
    tag = _sanitize_tag("+15555550001")
    recall = make_recall_enricher(sm_client, tag)
    persist = make_persist_outcome_hook(sm_client, tag)
    hooks = ExtensionHooks(
        prompt_enrichers=(recall,),
        on_outcome=(persist,),
    )

    # Enricher works end-to-end
    enriched = await hooks.prompt_enrichers[0](call_id="call_smoke")
    assert "[CALLER HISTORY]" in enriched
    assert len(hooks.on_outcome) == 1
```

**Run (expect failure if wiring logic is wrong):**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

**GREEN** — no code change needed if Milestones 1–5 are complete; this
test exercises already-implemented code. It is a regression guard.

---

### Milestone 7 — flag-off regression gate [RED → GREEN]

This is the mandatory gate before merge. It must be a test, not a
manual check.

```python
async def test_full_suite_canonical_path_unchanged_when_flag_off(monkeypatch):
    """With ROBIN_MEMORY_ENABLED unset, run_turn produces identical output
    to a pre-W1 baseline (no enricher text injected)."""
    monkeypatch.delenv("ROBIN_MEMORY_ENABLED", raising=False)
    from robin.loop import run_turn
    from tests.fakes import FakeLLM

    class _Msg:
        def __init__(self, content, stop_reason):
            self.content = content
            self.stop_reason = stop_reason

    llm = FakeLLM([_Msg(
        [{"type": "text", "text": "Hi, this is Robin."}], "end_turn")])
    # Use default hooks (no enrichers) — W0's ExtensionHooks default
    from robin.extensions import ExtensionHooks
    out = [c async for c in run_turn(
        "hello", [], system="SYS", llm=llm, tool_impls={},
        hooks=ExtensionHooks(), call_id=None)]
    assert out[-1]["text"] == "Hi, this is Robin."
    # No enricher text in the system passed to the LLM
    assert "CALLER HISTORY" not in llm.calls[0]["system"]
```

**Run:**

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

---

### Milestone 8 — REFACTOR + full-suite green

```bash
# Run the full W1 suite
docker compose run --rm robin pytest -q tests/test_supermemory.py

# Run the complete project suite (must be entirely green)
docker compose run --rm robin pytest -q

# Lint
docker compose run --rm robin ruff check src tests
```

Refactor checklist:
- [ ] `_fetch_history` and `_persist` are private helpers (<50 lines each)
- [ ] `make_recall_enricher` and `make_persist_outcome_hook` are the only
      public functions (plus `_get_client`, `_sanitize_tag` for tests)
- [ ] No hardcoded values (no literal `0.8`, use `_FETCH_TIMEOUT_S = 0.8`)
- [ ] No print statements; all observability via `obs.log_event`
- [ ] `FakeSupermemoryClient` in `tests/fakes.py` is append-only, not edited

---

## Demo moment

**Second call scenario** (ROBIN_MEMORY_ENABLED=1, same caller's number):

1. Caller rings Robin again.
2. Before the first substantive Claude turn, the enricher runs
   `_fetch_history("p14155551234")` — budget: 800 ms.
3. Super Memory returns: `"Cancelled 24 Hour Gym membership. Last-month
   refund confirmed. Confirmation: 24HF-4471."`.
4. The `[CALLER HISTORY]` block is appended to `effective_system`.
5. Claude opens: *"Welcome back — last time we cancelled your 24 Hour
   Gym membership and got you a full last-month refund with confirmation
   24HF-4471. What do you need handled today?"*

The judge sees Robin immediately personalise the interaction without any
explicit caller ID input from the stage presenter — the phone number
alone is enough to surface prior context.

---

## Time-box table

| T | Goal | Deliverable |
|---|---|---|
| +0 h | Milestone 0: scaffold + stub | Package exists, imports OK |
| +15 min | Milestone 1: flag-off no-ops GREEN | 3 passing tests |
| +35 min | Milestone 2: enricher formats history GREEN | 5 passing tests |
| +50 min | Milestone 3: timeout/error resilience GREEN | 7 passing tests |
| +70 min | Milestone 4: persist hook GREEN | 9 passing tests |
| +80 min | Milestone 5: tag sanitization GREEN | 12 passing tests |
| +90 min | Milestone 6: wiring smoke GREEN | 13 passing tests |
| +100 min | Milestone 7: flag-off regression gate GREEN | 14 passing tests |
| +110 min | Milestone 8: REFACTOR + full suite + ruff | All green, no lint |
| +120 min | Commit, push branch, open PR | Branch ready for merge |

---

## Collapse ladder

If behind schedule at T+60 min, apply cuts in this order:

1. **Min shippable (enricher only, no persist):** Ship Milestones 0–3
   and 7–8. Drop Milestones 4–6. Remove the `make_persist_outcome_hook`
   implementation (stub it returning a no-op async lambda). The demo
   moment still works for the first return call if prior data already
   exists in Super Memory from an earlier manual seed.

2. **Fallback (read-only, keyed on env tag):** If `callback_number`
   derivation is problematic, hardcode `_sm_tag` from a single
   `SUPERMEMORY_CALLER_TAG` env var (added to `.env.example`). This
   narrows the scope to a single known caller. Still fully flag-gated.

3. **Do not merge a half-done branch.** If Milestone 7 (flag-off
   regression gate) cannot be reached, keep the branch unmerged. The
   canonical demo is unaffected; W1's value is incremental.

---

## Flag-off regression gate (mandatory pre-merge)

Before opening the PR, run the full suite with the flag explicitly absent:

```bash
# Unset the flag — simulate the default production env
docker compose run --rm -e ROBIN_MEMORY_ENABLED= robin pytest -q
```

**Acceptance criterion:** zero test failures. If any existing test
breaks, the branch is not mergeable. Fix it before opening the PR.

Also verify `ruff`:

```bash
docker compose run --rm robin ruff check src tests
```

---

## Merge instructions

1. Confirm W0 is on `main` and `git log --oneline` shows the extension
   seam commit before branching.
2. Cut branch from post-W0 `main`:
   ```bash
   git checkout main && git pull
   git checkout -b feat/supermemory-recall
   ```
3. Implement in the order above (scaffold → Milestones 1–8).
4. Commit using conventional format:
   ```
   feat: W1 supermemory caller recall (enricher + outcome persist)
   ```
5. The PR diff must be additive only:
   - `src/robin/integrations/__init__.py` (new, empty)
   - `src/robin/integrations/supermemory.py` (new)
   - `tests/test_supermemory.py` (new)
   - `tests/fakes.py` (append only — no existing lines changed)
   - `main.py` (the W1 sub-block only — no other lines changed)
   - `.env.example` (append only)
   - `requirements.txt` (append only)
6. Run the flag-off regression gate one final time before pushing.
7. Do NOT `git push` from inside the agent session (denied in
   `.claude/settings.json`); the human performs the push.

**Git auto-merge guarantee:** Because W1 touches only the
`>>> W1 supermemory wiring <<<` sub-block in `main.py`, and W2–W4 each
touch only their own labeled sub-blocks, there are zero merge conflicts
with any other feature branch. `.env.example`, `requirements.txt`, and
`tests/fakes.py` are append-only; git merges these cleanly.

---

## Security + PII checklist

- [ ] `SUPERMEMORY_API_KEY` read only from `os.environ`; never in
      source, tests, or any log line (the key matches `_SECRET_KEY_PARTS`
      in `obs.py` so it is auto-dropped from any `obs.log_event` call
      that accidentally receives it)
- [ ] `container_tag` in log events uses the sanitized form (`p...`);
      it is a masked phone number — `obs.redact` will further mask the
      digits, showing only the last 4 (e.g. `p*******1234`)
- [ ] All tests use synthetic numbers: `+15550001234`, `+15555557777`,
      etc. — never a real phone number
- [ ] No real transcripts, recordings, or PII committed; the
      `FakeSupermemoryClient.added` list contains only synthetic content
      from test payloads
- [ ] `.env`, `context_pack.json`, and any `*.local.json` are gitignored
      (enforced by `.gitignore` and `.claude/settings.json`); W1 adds no
      new gitignore exceptions
- [ ] `_persist` logs `obs.log_event("memory_persist_ok", tag=tag)` —
      not the content, not the confirmation number, not the summary text
- [ ] `_fetch_history` logs `obs.log_event("memory_fetch_timeout_or_error",
      tag=tag)` on failure — not the exception detail that might contain
      an API response body with PII

---

*File path:* `docs/superpowers/specs/2026-05-17-w1-supermemory-recall.md`
