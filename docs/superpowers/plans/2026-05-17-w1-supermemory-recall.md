# W1 Super Memory Recall — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Robin remembers callers across calls — a Super Memory prompt-enricher injects prior outcomes/tactics at call start and an on_outcome hook persists each result; byte-identical to today when ROBIN_MEMORY_ENABLED is unset.

**Architecture:** A new `src/robin/integrations/supermemory.py` wraps an `AsyncSupermemory` module-level singleton with an 800 ms read budget and a fire-and-forget write, exposing `make_recall_enricher` / `make_persist_outcome_hook` factories plus `_get_client` / `_sanitize_tag` for tests. These are registered as a W0 `prompt_enricher` + `on_outcome` hook via the delimited `>>> W1 supermemory wiring <<<` sub-block in `main.py`, rebuilding the frozen `ExtensionHooks` immutably. The branch depends on W0 (`feat/extension-seam`) being merged to `main` first; it adds new files only and append-only edits to `tests/fakes.py`, `.env.example`, and `requirements.txt`.

**Tech Stack:** Python 3.12, supermemory>=3.42.0 SDK, pytest + pytest-asyncio, Docker (all runs inside the container).

---

## File Structure

```
src/robin/
  integrations/
    __init__.py            NEW — empty, makes integrations a package
    supermemory.py         NEW — full W1 module (singleton + enricher + hook)
  main.py                  EDIT — only the >>> W1 supermemory wiring <<< sub-block
tests/
  fakes.py                 APPEND — FakeSupermemoryClient block (append-only)
  test_supermemory.py      NEW — full W1 test suite
.env.example               APPEND — W1 env vars
requirements.txt           APPEND — supermemory>=3.42.0
```

**Out of scope — W1 never edits these files:**
`src/robin/loop.py`, `src/robin/app.py`, `src/robin/stage.py`,
`src/robin/models.py`, `src/robin/classifier.py`,
`src/robin/signature.py`, any file under `src/robin/fixtures/`, any
other existing test file.

**The W0 API W1 builds on (must already be on `main`):**

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

- A `PromptEnricher` is `async (call_id: str | None) -> str`. Return
  `""` to contribute nothing; a non-empty string is appended to
  `effective_system` in `run_turn` (loop.py) with a blank-line
  separator, in registration order.
- An `OutcomeHook` is `async (call_id: str | None, payload: dict) ->
  None`. The `deliver_result` payload is:
  ```python
  {
      "summary":      str(tool_input.get("summary", "")),
      "confirmation": tool_input.get("confirmation"),   # str | None
      "channel":      tool_input.get("channel"),        # str | None
      "out":          out,                               # the tool's return dict
  }
  ```
- Both hook types must return quickly (< ~200 ms) and must never raise.
  Long network work is self-scheduled via `asyncio.create_task(...)`;
  the hook itself returns immediately.

**`main.py` composition root (post-W0) — only the W1 marker is touched:**

```python
# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<
# >>> W2 agentmail wiring   <<<
# >>> W3 moss wiring        <<<
# >>> W4 dashboard wiring   <<<
# --- end sponsor extension wiring ---
```

**Caller key seam (exact, do not vary):** the Super Memory
`container_tag` is `pack.callback_number` (E.164, from
`src/robin/models.py:8` `ContextPack`) with `+` replaced by `p`, hard
capped at 100 chars. `container_tag` must match `[A-Za-z0-9._-]`; the
`+` sign is invalid. Example: `+14155551234` → `p14155551234` (16
chars). The enricher and the persist hook use the same derivation; there
is no `call_id`-based fallback — `callback_number` is always known at
composition time (validated/required by `load_context_pack`).

---

### Task 1: Milestone 0 — scaffold the integrations package + stub + fake (no behavior yet)

Verify W0 is green on `main`, create the empty `integrations` package, a
fully-stubbed `supermemory.py`, append `FakeSupermemoryClient` to
`tests/fakes.py`, and create a placeholder `tests/test_supermemory.py`
so imports resolve before any RED test is written.

- [ ] **Step 1:** Confirm W0 is on `main` and the full suite + lint are green (must pass before W1 starts):

```bash
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: zero failures, zero lint errors. If anything fails, STOP — W1
does not begin until post-W0 `main` is green.

- [ ] **Step 2:** Create the empty `integrations` package directory and `__init__.py`:

```bash
mkdir -p /Users/francescorosciano/docs/robin/src/robin/integrations
touch /Users/francescorosciano/docs/robin/src/robin/integrations/__init__.py
```

- [ ] **Step 3:** Create the STUB `src/robin/integrations/supermemory.py` (all public functions present, all bodies raise `NotImplementedError`):

```python
# src/robin/integrations/supermemory.py  — STUB
async def _fetch_history(client, tag): raise NotImplementedError
async def _persist(client, tag, summary, confirmation): raise NotImplementedError
def make_recall_enricher(client, tag): raise NotImplementedError
def make_persist_outcome_hook(client, tag): raise NotImplementedError
def _get_client(): raise NotImplementedError
def _sanitize_tag(number): raise NotImplementedError
```

- [ ] **Step 4:** Append the `FakeSupermemoryClient` block VERBATIM to the end of `tests/fakes.py` (append-only — do not edit any existing line):

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

- [ ] **Step 5:** Create `tests/test_supermemory.py` with a single placeholder:

```python
# tests/test_supermemory.py
def test_placeholder():
    pass
```

- [ ] **Step 6:** Verify the package and fake import cleanly inside the container:

```bash
docker compose run --rm robin python -c \
    "from tests.fakes import FakeSupermemoryClient; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 7:** Commit the scaffold:

```bash
git add src/robin/integrations/__init__.py src/robin/integrations/supermemory.py tests/fakes.py tests/test_supermemory.py
git commit -m "chore: W1 scaffold supermemory integrations package + fake"
```

---

### Task 2: Milestone 1 — flag-off / no-key no-ops [RED → GREEN]

When the supplied client is `None` (the disabled case), the enricher
returns `""` and the persist hook is a no-op — with **no network call**.
The factories take the already-resolved client as an argument; `None`
means disabled. Tests pass a `FakeSupermemoryClient` or `None` directly.

- [ ] **Step 1:** Replace the placeholder in `tests/test_supermemory.py` with the three RED tests:

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

- [ ] **Step 2:** Run the suite — expect FAIL (stub raises `NotImplementedError`):

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: the three tests FAIL (`NotImplementedError` from the stub
`make_recall_enricher` / `make_persist_outcome_hook`).

- [ ] **Step 3:** Replace the STUB `src/robin/integrations/supermemory.py` with the real module skeleton: imports, the `_get_client` singleton, `_sanitize_tag`, async `_fetch_history` / `_persist` (real bodies — used from Milestone 2 on), and the two factories whose returned closures no-op when `client is None`. Write the FULL module:

```python
"""W1 Super Memory recall: caller-history prompt-enricher + outcome persist.

Flag-gated by ROBIN_MEMORY_ENABLED. When the supplied client is None
(disabled / no key / SDK absent) every public path is a no-op that
returns "" (enricher) or None (outcome hook) and makes no network call.
"""
import asyncio
import os

from supermemory import AsyncSupermemory

from robin import obs
from robin.extensions import OutcomeHook, PromptEnricher

_FETCH_TIMEOUT_S = 0.8
_TAG_MAX_LEN = 100

_client: AsyncSupermemory | None = None


def _get_client() -> AsyncSupermemory | None:
    """Return the module-level AsyncSupermemory singleton, or None when
    the feature is disabled or no key is configured."""
    global _client
    if os.environ.get("ROBIN_MEMORY_ENABLED") != "1":
        return None
    key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not key:
        return None
    if _client is None:
        _client = AsyncSupermemory(api_key=key, timeout=1.5, max_retries=0)
    return _client


def _sanitize_tag(number: str) -> str:
    """Caller E.164 → container_tag. '+' is invalid in [A-Za-z0-9._-];
    replace with 'p' and hard-cap at 100 chars."""
    tag = number.replace("+", "p").strip()
    return tag[:_TAG_MAX_LEN]


async def _fetch_history(client: AsyncSupermemory, tag: str) -> str:
    """Read prior caller outcomes/tactics. Hard 800 ms budget; any
    timeout or exception → "" (no enrichment, never raise)."""
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
            timeout=_FETCH_TIMEOUT_S,
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


async def _persist(client: AsyncSupermemory, tag: str,
                   summary: str, confirmation: str | None) -> None:
    """Best-effort write of one outcome. Any exception is swallowed and
    logged; never raises into the scheduling hook."""
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


def make_recall_enricher(client, tag: str) -> PromptEnricher:
    """Return an enricher that fetches caller history from Super Memory.

    client is None ⇒ the returned enricher is a no-op returning "".
    """
    async def _enricher(call_id: str | None) -> str:
        if client is None:
            return ""
        return await _fetch_history(client, tag)

    return _enricher


def make_persist_outcome_hook(client, tag: str) -> OutcomeHook:
    """Return an outcome hook that fire-and-forgets a persist task.

    client is None ⇒ the returned hook is a no-op returning None.
    """
    async def _hook(call_id: str | None, payload: dict) -> None:
        if client is None:
            return None
        summary = str(payload.get("summary", ""))
        confirmation = payload.get("confirmation")
        asyncio.create_task(_persist(client, tag, summary, confirmation))
        return None

    return _hook
```

- [ ] **Step 4:** Re-run the suite — expect PASS for the three Milestone 1 tests:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: 3 passing tests.

- [ ] **Step 5:** Commit:

```bash
git add src/robin/integrations/supermemory.py tests/test_supermemory.py
git commit -m "feat: W1 supermemory flag-off/no-key no-op enricher + hook"
```

---

### Task 3: Milestone 2 — enricher formats the `[CALLER HISTORY]` block [RED → GREEN]

With history items present, the enricher returns a `[CALLER HISTORY]`
block listing each item; zero results returns `""` (no header). Search
is called with the correct `container_tag`.

- [ ] **Step 1:** Append the two RED tests to `tests/test_supermemory.py`:

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

- [ ] **Step 2:** Run the suite — expect the new tests to behave per the implemented `_fetch_history`:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: with `_fetch_history` implemented in Task 2 Step 3, these two
tests PASS. If `_fetch_history` was left as a stub, they FAIL here —
implement `_fetch_history` exactly as in Task 2 Step 3 (the
`client.search.documents(...)` call, `.results` iteration, `.content`/
`.memory` extraction, `[CALLER HISTORY]` header) and re-run.

- [ ] **Step 3:** Re-run to confirm PASS:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: 5 passing tests total.

- [ ] **Step 4:** Commit:

```bash
git add tests/test_supermemory.py src/robin/integrations/supermemory.py
git commit -m "feat: W1 supermemory enricher formats CALLER HISTORY block"
```

---

### Task 4: Milestone 3 — enricher timeout / error resilience [RED → GREEN]

A `TimeoutError` or any SDK exception from the fetch must produce `""`
and never raise into the call turn.

- [ ] **Step 1:** Append the two RED tests to `tests/test_supermemory.py`:

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

- [ ] **Step 2:** Run the suite — expect these tests to PASS only if the `try/except (asyncio.TimeoutError, Exception)` wrapper and the `asyncio.wait_for(..., timeout=_FETCH_TIMEOUT_S)` are present in `_fetch_history`:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: PASS with the Task 2 Step 3 `_fetch_history` (it already wraps
the `asyncio.wait_for(...)` in `try/except (asyncio.TimeoutError,
Exception)` returning `""` and logs
`obs.log_event("memory_fetch_timeout_or_error", tag=tag)`). If the
wrapper is missing, add it exactly as in Task 2 Step 3 and re-run.

- [ ] **Step 3:** Re-run to confirm PASS:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: 7 passing tests total.

- [ ] **Step 4:** Commit:

```bash
git add tests/test_supermemory.py src/robin/integrations/supermemory.py
git commit -m "feat: W1 supermemory enricher timeout/error returns empty"
```

---

### Task 5: Milestone 4 — persist hook schedules a task and returns fast [RED → GREEN]

The outcome hook must return without awaiting the network write
(`asyncio.create_task`), the scheduled task must persist content +
confirmation under the correct tag, and an `add()` failure must be
swallowed.

- [ ] **Step 1:** Append the two RED tests to `tests/test_supermemory.py`:

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

- [ ] **Step 2:** Run the suite — expect these tests to PASS only if `make_persist_outcome_hook` schedules `_persist` via `asyncio.create_task` and `_persist` wraps `client.add(...)` in `try/except`:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: PASS with the Task 2 Step 3 implementation (the hook extracts
`summary`/`confirmation` from `payload`, calls
`asyncio.create_task(_persist(client, tag, summary, confirmation))`, and
returns; `_persist` builds `content` with
`" | confirmation={confirmation}"` and swallows any `add()` exception).
If missing, implement exactly as in Task 2 Step 3 and re-run.

- [ ] **Step 3:** Re-run to confirm PASS:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: 9 passing tests total.

- [ ] **Step 4:** Commit:

```bash
git add tests/test_supermemory.py src/robin/integrations/supermemory.py
git commit -m "feat: W1 supermemory persist hook fire-and-forget + swallow"
```

---

### Task 6: Milestone 5 — `container_tag` sanitization [RED → GREEN]

`_sanitize_tag` replaces `+` with `p`, caps length at 100 chars, and
leaves an already-sanitized tag unchanged.

- [ ] **Step 1:** Append the three RED tests to `tests/test_supermemory.py`:

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

- [ ] **Step 2:** Run the suite — expect these to PASS only if `_sanitize_tag` is the real three-line implementation:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: PASS with the Task 2 Step 3 `_sanitize_tag`
(`tag = number.replace("+", "p").strip(); return tag[:_TAG_MAX_LEN]`,
`_TAG_MAX_LEN = 100`). If still a stub, implement exactly as in Task 2
Step 3 and re-run.

- [ ] **Step 3:** Re-run to confirm PASS:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: 12 passing tests total.

- [ ] **Step 4:** Commit:

```bash
git add tests/test_supermemory.py src/robin/integrations/supermemory.py
git commit -m "feat: W1 supermemory _sanitize_tag plus->p, 100-char cap"
```

---

### Task 7: Milestone 6 — main.py wiring (integration smoke) + insert the W1 sub-block [RED → GREEN]

Add a wiring smoke test that exercises the W1 composition-root logic
without importing the real `main.py` (which needs a valid
`context_pack.json` and all env vars), then insert the real W1 sub-block
into `main.py` between the W0 markers.

- [ ] **Step 1:** Append the RED smoke test to `tests/test_supermemory.py`:

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

- [ ] **Step 2:** Run the suite — expect PASS (this exercises already-implemented Milestone 1–5 code; it is a regression guard):

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: PASS — 13 passing tests total. (No source change is required
for this test; if it fails, a Milestone 1–5 path is broken — fix it,
do not weaken the test.)

- [ ] **Step 3:** Locate the exact W1 marker line in `main.py` and confirm `import os` and `_pack` ordering before editing:

```bash
grep -n ">>> W1 supermemory wiring <<<" /Users/francescorosciano/docs/robin/src/robin/main.py
grep -n "^import os" /Users/francescorosciano/docs/robin/src/robin/main.py
grep -n "_pack" /Users/francescorosciano/docs/robin/src/robin/main.py
```

Expected: the `>>> W1 supermemory wiring <<<` marker exists; `import os`
is already present (`main.py:3`); `_pack` is defined (around
`main.py:22`) **before** the marker. The W1 block must come after
`_pack` because it reads `_pack.callback_number`. If `import os` is
absent, add it at the top of `main.py` imports.

- [ ] **Step 4:** Replace the single marker line `# >>> W1 supermemory wiring <<<` in `main.py` with the FULL W1 sub-block (touch ONLY this sub-block; leave `>>> W2/W3/W4 <<<` markers and every other line unchanged):

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

Note: `_hooks` is rebuilt immutably (a new frozen `ExtensionHooks`); the
existing `on_research` and `event_bus` are forwarded unchanged. No
in-place mutation occurs.

- [ ] **Step 5:** Run the FULL project suite to confirm the `main.py` edit broke nothing (the W1 block is dormant because `ROBIN_MEMORY_ENABLED` is unset in CI):

```bash
docker compose run --rm robin pytest -q
```

Expected: the entire suite is green (W1 block is a no-op with the flag
unset).

- [ ] **Step 6:** Commit:

```bash
git add tests/test_supermemory.py src/robin/main.py
git commit -m "feat: W1 supermemory main.py wiring sub-block + smoke test"
```

---

### Task 8: Milestone 7 — flag-off regression gate [RED → GREEN]

A test (not a manual check) proving `run_turn` produces identical output
with `ROBIN_MEMORY_ENABLED` unset and default `ExtensionHooks()` — no
`[CALLER HISTORY]` text injected.

- [ ] **Step 1:** Append the flag-off regression test to `tests/test_supermemory.py`:

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

- [ ] **Step 2:** Run the suite — expect PASS (default `ExtensionHooks()` has no enrichers, so no `[CALLER HISTORY]` text reaches the LLM system prompt):

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: PASS — 14 passing tests total. (This guards the byte-identical
flag-off contract; if it fails, the no-op design is broken — fix the
source, never the test.)

- [ ] **Step 3:** Commit:

```bash
git add tests/test_supermemory.py
git commit -m "test: W1 supermemory flag-off regression gate (run_turn unchanged)"
```

---

### Task 9: Milestone 8 — REFACTOR + full-suite green + append env/requirements

Run the full W1 suite, the complete project suite, and lint; complete
the refactor checklist; append the W1 env vars and the SDK requirement.

- [ ] **Step 1:** Run the W1 suite:

```bash
docker compose run --rm robin pytest -q tests/test_supermemory.py
```

Expected: 14 passing tests.

- [ ] **Step 2:** Run the complete project suite (must be entirely green):

```bash
docker compose run --rm robin pytest -q
```

Expected: zero failures across the whole project.

- [ ] **Step 3:** Lint:

```bash
docker compose run --rm robin ruff check src tests
```

Expected: zero lint errors.

- [ ] **Step 4:** Verify the refactor checklist against `src/robin/integrations/supermemory.py` and `tests/fakes.py` (the module written in Task 2 Step 3 already satisfies all of these — confirm, do not rewrite):
  - [ ] `_fetch_history` and `_persist` are private helpers (<50 lines each)
  - [ ] `make_recall_enricher` and `make_persist_outcome_hook` are the only public functions (plus `_get_client`, `_sanitize_tag` for tests)
  - [ ] No hardcoded values (no literal `0.8` — use `_FETCH_TIMEOUT_S = 0.8`; no literal `100` — use `_TAG_MAX_LEN = 100`)
  - [ ] No print statements; all observability via `obs.log_event`
  - [ ] `FakeSupermemoryClient` in `tests/fakes.py` is append-only, not edited

- [ ] **Step 5:** Append the W1 env vars to the end of `.env.example`, under the existing `# --- Optional sponsor hooks ---` block (append-only):

```
# --- W1: Super Memory (caller history recall) ---
ROBIN_MEMORY_ENABLED=
SUPERMEMORY_API_KEY=
```

- [ ] **Step 6:** Append the SDK requirement to the end of `requirements.txt` (append-only):

```
supermemory>=3.42.0
```

- [ ] **Step 7:** Rebuild the container so the new requirement is installed, then re-run the full suite + lint to confirm nothing regressed with the real SDK present:

```bash
docker compose build robin
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Expected: image rebuilds with `supermemory>=3.42.0`; full suite green;
lint clean.

- [ ] **Step 8:** Commit:

```bash
git add .env.example requirements.txt src/robin/integrations/supermemory.py tests/fakes.py
git commit -m "chore: W1 supermemory env vars + supermemory SDK requirement"
```

---

### Task 10: Flag-off regression gate (mandatory pre-merge) + merge instructions

The final gate and the additive-merge handoff. This branch is additive
on post-W0 `main`; only the W1 `main.py` sub-block plus append-only files
change. Do NOT `git push` — the human performs the push.

- [ ] **Step 1:** Run the full suite with the flag explicitly absent (simulates the default production env):

```bash
docker compose run --rm -e ROBIN_MEMORY_ENABLED= robin pytest -q
```

Acceptance criterion: **zero test failures.** If any existing test
breaks, the branch is NOT mergeable — fix it before opening the PR.

- [ ] **Step 2:** Final lint:

```bash
docker compose run --rm robin ruff check src tests
```

Expected: zero lint errors.

- [ ] **Step 3:** Confirm the PR diff is additive only — exactly these paths, nothing else:
  - `src/robin/integrations/__init__.py` (new, empty)
  - `src/robin/integrations/supermemory.py` (new)
  - `tests/test_supermemory.py` (new)
  - `tests/fakes.py` (append only — no existing line changed)
  - `src/robin/main.py` (the `>>> W1 … <<<` sub-block only — no other line changed)
  - `.env.example` (append only)
  - `requirements.txt` (append only)

```bash
git diff --stat main...HEAD
```

Expected: only the seven paths above appear; `loop.py`, `app.py`,
`stage.py`, `models.py`, `classifier.py`, `signature.py`, and
`src/robin/fixtures/*` do NOT appear.

- [ ] **Step 4:** Confirm W0 is the base. Verify `git log --oneline` shows the W0 extension-seam commit before this branch's commits, and that this branch was cut from post-W0 `main`:

```bash
git log --oneline main...HEAD
git log --oneline -1 main
```

Expected: post-W0 `main` includes the extension-seam commit; this
branch's commits sit on top of it.

- [ ] **Step 5:** Squash/confirm the conventional branch commit message (no attribution / no `Co-Authored-By` lines):

```
feat: W1 supermemory caller recall (enricher + outcome persist)
```

- [ ] **Step 6:** Do NOT `git push`. `git push` is denied in
  `.claude/settings.json`; the human performs the push and opens the PR.
  Report the branch name (`feat/supermemory-recall`), the green
  flag-off-gate result, and the additive-only `git diff --stat` to the
  human for the push/submission step.

**Git auto-merge guarantee:** W1 touches only the
`>>> W1 supermemory wiring <<<` sub-block in `main.py`; W2–W4 each touch
only their own labeled sub-blocks → zero merge conflicts.
`.env.example`, `requirements.txt`, and `tests/fakes.py` are
append-only; git merges these cleanly. W1 merges into post-W0 `main` in
any order relative to W2–W4.

> **Collapse ladder (note — apply only if behind schedule at ~T+60 min):**
> 1. **Min shippable (enricher only, no persist):** ship Tasks 1–4 and
>    8–10; drop Tasks 5–7's persist work — stub
>    `make_persist_outcome_hook` to return a no-op async hook. The demo
>    moment still works for the first return call if prior data was
>    manually seeded.
> 2. **Fallback (read-only, fixed tag):** if `callback_number`
>    derivation is problematic, hardcode `_sm_tag` from a single
>    `SUPERMEMORY_CALLER_TAG` env var (add to `.env.example`),
>    narrowing scope to one known caller. Still fully flag-gated.
> 3. **Do not merge a half-done branch.** If Task 8 (flag-off
>    regression gate) cannot be reached, leave the branch unmerged. The
>    canonical demo is unaffected; W1's value is incremental.
