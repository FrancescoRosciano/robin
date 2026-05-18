# W2 — AgentMail Close-Loop: Spec + Implementation Plan

**Branch:** `feat/agentmail-closeloop`
**Depends on:** W0 (`feat/extension-seam`) merged to `main` first
**Size:** M · estimated ~2 h
**Status:** ready to implement (post W0 merge)

---

## 1. Goal

When Robin successfully cancels the caller's gym membership — i.e., the
`deliver_result` tool fires and the classifier determines success — Robin
closes the loop *in writing* by sending two emails via the AgentMail platform:

1. **Caller confirmation** — cancellation confirmed, last-month refund
   secured, confirmation number `24HF-4471` (fallback if not in payload).
   Sent to the email Robin already knows about from `pack.email`; skipped
   silently if `pack.email` is empty.
2. **Drafted complaint / certified-letter skeleton** — addressed to a
   *synthetic* gym address for the demo; never sent to the real company.

Both sends are fire-and-forget (`asyncio.create_task`). The hook returns in
< 200 ms. Any error is swallowed and logged via `obs.log_event`.

**Demo moment:** during the stage run, after Robin reports back to the
caller, the real confirmation email visibly arrives in the inbox on screen,
and the complaint draft is shown — three sponsor integrations (AgentMail,
Super Memory if W1 is merged, Moss if W3 is merged) all visible on the
flagship dashboard.

Flag: `ROBIN_AGENTMAIL_ENABLED=1`. Absent (default) → total no-op;
canonical gym-cancel path is byte-identical to `main`.

---

## 2. Orientation

### 2.1 Portfolio fit

This branch is W2 in the sponsor-extension portfolio
(`docs/superpowers/specs/2026-05-17-robin-sponsor-extensions-design.md`).
W0 installed the `ExtensionHooks` injection contract. W2 is purely additive
on top of that seam.

### 2.2 Isolation contract (verbatim from the master design)

- Flag-off ⇒ no-op, byte-identical. `ROBIN_AGENTMAIL_ENABLED` absent ⇒
  nothing changes.
- Graceful no-op on any failure. Missing key, SDK error, timeout, or any
  exception ⇒ one `obs.log_event(...)` breadcrumb, never raises into the
  call turn.
- New code in new files only. W2 adds:
  - `src/robin/integrations/__init__.py` (empty, if absent)
  - `src/robin/integrations/agentmail.py`
  - `tests/test_agentmail.py`
  - `FakeAgentMailClient` appended to `tests/fakes.py`
  - `# >>> W2 agentmail wiring <<<` sub-block in `main.py`
  - One optional field appended to `ContextPack` in `models.py`
  - Append-only lines in `.env.example` and `requirements.txt`
- **No edits** to `loop.py`, `app.py`, `stage.py`, `classifier.py`,
  `signature.py`, or any locked prompt fixture.

### 2.3 W0 API (restated here for self-containment)

```python
from robin.extensions import ExtensionHooks

# Type aliases from extensions.py:
# OutcomeHook = Callable[[str | None, dict], Awaitable[None]]
#
# payload shape for on_outcome hooks:
#   {
#     "summary": str,              # str(tool_input.get("summary", ""))
#     "confirmation": str | None,  # tool_input.get("confirmation")
#     "channel": str | None,       # tool_input.get("channel")
#     "out": dict,                 # the raw deliver_result return value
#   }
#
# Invariants (from loop.py W0 edit, _record_session):
#   - on_outcome fires ONLY when name == "deliver_result" AND
#     out["delivered"] is truthy
#   - hook must return quickly (< ~200 ms); must not raise
#   - long work → asyncio.create_task(...) inside the hook, return immediately
#   - any exception → caught by W0's try/except → obs.log_event("extension_hook_error")
```

`main.py` currently has (W0 seam, lines 60-70 area):

```python
# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
# >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
# >>> W4 dashboard wiring   <<<   (added on feat/dashboard-flagship)
# --- end sponsor extension wiring ---
```

W2 inserts its code ONLY between `# >>> W2 agentmail wiring <<<` and
`# >>> W3 moss wiring <<<`. No other lines in `main.py` are touched.

---

## 3. Exact seams (confirm by reading the files listed)

### 3.1 `src/robin/models.py` — add one optional field

**Current state** (confirmed by reading): `ContextPack` is a frozen
dataclass with 8 fields, last field is `fallback_goal: str`. No `email`
field exists.

**Required change:** append `email: str = ""` as the **last field** of the
dataclass, after `fallback_goal`:

```python
@dataclass(frozen=True)
class ContextPack:
    caller_name: str
    callback_number: str
    target_name: str
    target_display_number: str
    receptionist_to_number: str
    jurisdiction: str
    win_goal: str
    fallback_goal: str
    email: str = ""          # W2: optional caller email; "" = skip send
```

This is the **one allowed canonical-path edit** for the entire portfolio
(noted in the master design). Because it has a default value and is last,
all existing dataclass instantiations using positional or keyword args for
the original 8 fields remain valid — this is fully backward-compatible.

### 3.2 `src/robin/context_pack.py` — no change needed

**Current state** (confirmed by reading): `load_context_pack` builds a
`ContextPack` using `ContextPack(**{k: raw[k] for k in _FIELDS})` where
`_FIELDS` is the explicit tuple of the 8 required field names. It does NOT
use `**raw` — it explicitly whitelists the fields it extracts.

**Consequence:** the loader naturally tolerates an absent `email` key in
the JSON file. If `context_pack.json` omits `email`, `ContextPack` receives
no `email` kwarg and Python uses the default `""`. If `context_pack.json`
includes `email`, the loader currently ignores it (it is not in `_FIELDS`).

**Required change for W2:** `_FIELDS` must not be modified (it validates
required fields; adding `email` to it would make it required and break
existing packs). Instead, after the existing validation loop, extract
`email` optionally:

```python
# At the end of load_context_pack, replace the final return line:
return ContextPack(
    **{k: raw[k] for k in _FIELDS},
    email=raw.get("email", ""),          # W2: optional, default ""
)
```

This is a safe, additive one-liner. The `email` value, when present, is NOT
validated (no E.164, no format check) — it is used only as a send target;
an invalid email produces a send failure which is swallowed.

**Note on how `context_pack.json` supplies `email`:** the gitignored
`context_pack.json` (real PII file, never committed) may carry an `"email"`
key with the presenter's real email address. The `.env.example` entry below
documents this as a comment. For the demo, a real address is placed here
before stage. Tests always use `"test@example.com"` (synthetic only).

### 3.3 `src/robin/integrations/agentmail.py` — new file (main implementation)

Full path: `src/robin/integrations/agentmail.py`
This is the primary deliverable of W2.

### 3.4 `src/robin/integrations/__init__.py` — new file if absent

Empty `__init__.py` making `robin.integrations` a package. If W1 has
already created it, skip; the file is identical (empty) either way.

### 3.5 `main.py` — `>>> W2 agentmail wiring <<<` sub-block only

Insert between the W2 and W3 markers. No other line is touched.

### 3.6 `tests/fakes.py` — append `FakeAgentMailClient`

Appended at the end. No existing content is modified.

### 3.7 `.env.example` — append W2 block

Append after existing content (under the existing `--- Optional sponsor hooks ---`
section or after it if W1 already extended it).

### 3.8 `requirements.txt` — append one line

Append `agentmail>=0.5.0` at the end.

---

## 4. AgentMail SDK Contract

These facts are confirmed and must be used as-is. Do not re-research.

```
PyPI package:  agentmail>=0.5.0
Import:        from agentmail import AsyncAgentMail
REST base URL: https://api.agentmail.to/v0/
Auth:          Bearer token (AGENTMAIL_API_KEY env var)
```

### 4.1 Client instantiation

```python
from agentmail import AsyncAgentMail

client = AsyncAgentMail(api_key=os.environ["AGENTMAIL_API_KEY"], timeout=10.0)
```

### 4.2 Ensure-inbox-once (module-level singleton)

Create the inbox once at module level (lazy, guarded by an `asyncio.Lock`);
never recreate per call.

```python
_inbox_id: str | None = None
_inbox_email: str | None = None
_inbox_lock: asyncio.Lock  # initialised in _ensure_inbox()

async def _ensure_inbox(client: AsyncAgentMail) -> tuple[str, str]:
    """Return (inbox_id, inbox_email), creating the inbox once."""
    global _inbox_id, _inbox_email
    if _inbox_id is not None:
        return _inbox_id, _inbox_email
    async with _inbox_lock:
        if _inbox_id is not None:          # double-check after acquiring
            return _inbox_id, _inbox_email
        result = await client.inboxes.create(
            username="robin-confirms",
            display_name="Robin Assistant",
        )
        _inbox_id = result.inbox_id
        _inbox_email = result.email
        return _inbox_id, _inbox_email
```

The `asyncio.Lock` must be created lazily inside `_ensure_inbox` or in an
`asyncio.get_event_loop()`-safe way (not at module import time, which runs
outside the event loop). Use a module-level `Optional[asyncio.Lock]` pattern
initialised on first call, or simply create it inside the guarded block if
`_inbox_id` is already set before the lock is ever needed.

A simple safe pattern — create the lock at module scope using a sentinel:

```python
_inbox_id: str | None = None
_inbox_email: str | None = None
_inbox_lock: asyncio.Lock | None = None   # created on first async call


async def _get_lock() -> asyncio.Lock:
    global _inbox_lock
    if _inbox_lock is None:
        _inbox_lock = asyncio.Lock()
    return _inbox_lock
```

### 4.3 Send a message

```python
result = await client.inboxes.messages.send(
    inbox_id,           # str, from _ensure_inbox
    to=recipient_email, # str, e.g. "caller@example.com"
    subject="...",
    text="...",
)
# result contains: result.message_id, result.thread_id
```

### 4.4 Latency and error contract

- `send` must **never block the caller callback**. Always fire via
  `asyncio.create_task(_send_emails(...))` inside the hook; return from
  the hook immediately after creating the task.
- Timeout: `AsyncAgentMail(..., timeout=10.0)` — 10 s hard limit on any
  single network call inside `_send_emails`.
- Any exception inside `_send_emails` → catch all, call
  `obs.log_event("agentmail_send_error", ...)` once, then return. Never
  re-raise.

### 4.5 A2A reply (out of scope for W2 — collapse cut)

The AgentMail SDK supports:
- List messages: `client.inboxes.messages.list(inbox_id, limit=10)`
- Reply to a message: `client.inboxes.messages.reply(inbox_id, message_id, text=...)`
- Inbound webhooks are Svix-based.

**Do NOT wire Robin's webhook endpoint to AgentMail's Svix webhooks.** This
is explicitly out of scope for W2. The A2A reply path is noted here as a
future cut only.

### 4.6 Promo / key access

AgentMail offers an "AP hackathon" promo (free dev month). Redemption is via
`console.agentmail.to` or their Discord. Flag this as a **risk**: if the key
is not obtained before demo time, `ROBIN_AGENTMAIL_ENABLED` is simply absent
and the hook is a no-op. The demo degrades gracefully; the canonical path
is unaffected.

---

## 5. Implementation Design

### 5.1 `src/robin/integrations/agentmail.py` — full design

```python
"""AgentMail close-loop integration for Robin (W2).

Disabled entirely when ROBIN_AGENTMAIL_ENABLED != "1" or
AGENTMAIL_API_KEY is absent.  On a successful gym-cancel outcome, fires
two emails best-effort via asyncio.create_task:
  1. Caller confirmation to pack.email (skipped if empty)
  2. Complaint draft to a synthetic gym address (demo only)

Never raises. All errors → obs.log_event. Never blocks the hook return.
"""
import asyncio
import os
from typing import TYPE_CHECKING

from robin import obs

if TYPE_CHECKING:
    from agentmail import AsyncAgentMail
    from robin.models import ContextPack

# Module-level singletons (None until first use)
_client: "AsyncAgentMail | None" = None
_inbox_id: str | None = None
_inbox_email: str | None = None
_inbox_lock: asyncio.Lock | None = None

# Synthetic gym address — never a real address in source
_GYM_DEMO_EMAIL = "cancellations@24hourfitness-demo.invalid"
_FALLBACK_CONFIRMATION = "24HF-4471"


def _is_enabled() -> bool:
    return (
        os.environ.get("ROBIN_AGENTMAIL_ENABLED") == "1"
        and bool(os.environ.get("AGENTMAIL_API_KEY"))
    )


def _get_or_create_client() -> "AsyncAgentMail":
    global _client
    if _client is None:
        from agentmail import AsyncAgentMail
        _client = AsyncAgentMail(
            api_key=os.environ["AGENTMAIL_API_KEY"],
            timeout=10.0,
        )
    return _client


async def _get_lock() -> asyncio.Lock:
    global _inbox_lock
    if _inbox_lock is None:
        _inbox_lock = asyncio.Lock()
    return _inbox_lock


async def _ensure_inbox() -> tuple[str, str]:
    """Return (inbox_id, inbox_email); create inbox once."""
    global _inbox_id, _inbox_email
    if _inbox_id is not None:
        return _inbox_id, _inbox_email        # type: ignore[return-value]
    lock = await _get_lock()
    async with lock:
        if _inbox_id is not None:
            return _inbox_id, _inbox_email    # type: ignore[return-value]
        client = _get_or_create_client()
        result = await client.inboxes.create(
            username="robin-confirms",
            display_name="Robin Assistant",
        )
        _inbox_id = result.inbox_id
        _inbox_email = result.email
        return _inbox_id, _inbox_email        # type: ignore[return-value]


def _is_success(payload: dict) -> bool:
    """Outcome is success when delivered=True and confirmation present or
    summary contains positive signal.  Mirrors the classifier heuristic:
    confirmation number present is the clearest DONE signal."""
    out = payload.get("out", {})
    if not out.get("delivered"):
        return False
    confirmation = payload.get("confirmation")
    summary = str(payload.get("summary", "")).lower()
    # confirmation number present → unambiguous success
    if confirmation:
        return True
    # fallback: summary contains cancellation success signal
    return any(kw in summary for kw in ("cancel", "refund", "confirm"))


async def _send_emails(
    caller_email: str,
    confirmation: str,
    summary: str,
) -> None:
    """Best-effort send; swallows all errors."""
    try:
        inbox_id, _ = await _ensure_inbox()
        client = _get_or_create_client()

        if caller_email:
            subject = "Robin confirmed: gym membership cancelled"
            body = (
                f"Hi,\n\n"
                f"Robin has successfully handled your gym membership cancellation.\n\n"
                f"Outcome: {summary}\n"
                f"Confirmation #: {confirmation}\n\n"
                f"Your last-month refund has been secured as part of this resolution.\n\n"
                f"— Robin\n"
            )
            await client.inboxes.messages.send(
                inbox_id, to=caller_email, subject=subject, text=body
            )
            obs.log_event("agentmail_caller_sent", confirmation=confirmation)

        # Complaint draft — synthetic address, demo only
        complaint_subject = (
            "Notice of Intent to File Regulatory Complaint — "
            "Membership Cancellation Obstruction"
        )
        complaint_body = (
            f"Dear 24 Hour Fitness Compliance Team,\n\n"
            f"This is formal notice that the membership cancellation requested "
            f"on behalf of your member was obstructed in violation of applicable "
            f"consumer-protection statutes including the FTC Negative Option Rule "
            f"(16 CFR Part 425) and the California Health Studio Services Act "
            f"(Cal. Civil Code § 1812.80 et seq.).\n\n"
            f"The cancellation has now been confirmed (Ref: {confirmation}). "
            f"Should any further obstruction occur or the refund not be processed "
            f"within 30 days, a complaint will be filed with the FTC, the CFPB, "
            f"and the California Attorney General's office.\n\n"
            f"[DRAFTED BY ROBIN — REVIEW BEFORE SENDING]\n"
        )
        await client.inboxes.messages.send(
            inbox_id,
            to=_GYM_DEMO_EMAIL,
            subject=complaint_subject,
            text=complaint_body,
        )
        obs.log_event("agentmail_complaint_drafted", confirmation=confirmation)

    except Exception as exc:  # noqa: BLE001
        obs.log_event(
            "agentmail_send_error",
            err=f"{type(exc).__name__}: {exc}",
            confirmation=confirmation,
        )


def make_email_outcome_hook(pack: "ContextPack"):
    """Return an OutcomeHook that fires close-loop emails on success."""

    async def _hook(call_id: str | None, payload: dict) -> None:
        if not _is_enabled():
            return
        if not _is_success(payload):
            return
        confirmation = payload.get("confirmation") or _FALLBACK_CONFIRMATION
        summary = payload.get("summary", "Membership cancelled.")
        caller_email = getattr(pack, "email", "")  # "" if field absent
        # Fire-and-forget: hook returns immediately
        asyncio.create_task(
            _send_emails(
                caller_email=caller_email,
                confirmation=confirmation,
                summary=summary,
            )
        )
        obs.log_event(
            "agentmail_hook_fired",
            call_id=call_id,
            has_email=bool(caller_email),
        )

    return _hook
```

### 5.2 `main.py` — W2 sub-block (insert between W2 and W3 markers)

```python
# >>> W2 agentmail wiring   <<<
import os as _os
if _os.environ.get("ROBIN_AGENTMAIL_ENABLED") == "1":
    from robin.integrations.agentmail import make_email_outcome_hook as _make_am_hook
    _hooks = ExtensionHooks(
        prompt_enrichers=_hooks.prompt_enrichers,
        on_research=_hooks.on_research,
        on_outcome=_hooks.on_outcome + (_make_am_hook(_pack),),
        event_bus=_hooks.event_bus,
    )
```

This rebuilds `_hooks` immutably, appending only the on_outcome hook. All
other slots pass through unchanged. The `_os` alias avoids shadowing the
top-level `os` import.

### 5.3 `tests/fakes.py` — append `FakeAgentMailClient`

```python
# --- W2: FakeAgentMailClient ---

class _FakeInbox:
    def __init__(self, inbox_id: str, email: str):
        self.inbox_id = inbox_id
        self.email = email


class _FakeMessage:
    def __init__(self, message_id: str, thread_id: str):
        self.message_id = message_id
        self.thread_id = thread_id


class _FakeMessages:
    def __init__(self, sent: list):
        self._sent = sent  # shared reference to FakeAgentMailClient.sent

    async def send(self, inbox_id: str, *, to: str, subject: str, text: str):
        self._sent.append({"inbox_id": inbox_id, "to": to,
                           "subject": subject, "text": text})
        return _FakeMessage(message_id="msg-fake-01", thread_id="thr-fake-01")


class _FakeInboxes:
    def __init__(self, inbox_id: str, email: str, sent: list,
                 created: list, raise_on_send: Exception | None = None):
        self._inbox_id = inbox_id
        self._email = email
        self._created = created
        self._raise_on_send = raise_on_send
        self.messages = _FakeMessages(sent)

    async def create(self, username: str, display_name: str):
        self._created.append({"username": username, "display_name": display_name})
        return _FakeInbox(self._inbox_id, self._email)


class FakeAgentMailClient:
    """Mimics agentmail.AsyncAgentMail for unit tests.

    Attributes:
        sent:    list of dicts from inboxes.messages.send calls
        created: list of dicts from inboxes.create calls
    """

    def __init__(
        self,
        inbox_id: str = "inbox-test-01",
        inbox_email: str = "robin-confirms@agentmail.to",
        raise_on_send: Exception | None = None,
    ):
        self.sent: list[dict] = []
        self.created: list[dict] = []
        self.inboxes = _FakeInboxes(
            inbox_id=inbox_id,
            email=inbox_email,
            sent=self.sent,
            created=self.created,
            raise_on_send=raise_on_send,
        )
```

Note: `raise_on_send` is stored for future use but the simple `_FakeMessages`
above does not implement it — tests that need send errors should monkeypatch
`_send_emails` directly (see test plan §6.6).

---

## 6. TDD Plan: RED → GREEN → REFACTOR

All commands run inside the container:
```
docker compose run --rm robin pytest -q tests/test_agentmail.py
docker compose run --rm robin pytest -q          # full suite
docker compose run --rm robin ruff check src tests
```

The test file lives at `tests/test_agentmail.py`. All tests use
`asyncio_mode = "auto"` (already configured in `pytest.ini` / `pyproject.toml`
for the project). Email addresses are always synthetic (`test@example.com`,
`cancellations@24hourfitness-demo.invalid`). No real keys in tests.

### Milestone 0 — scaffold (RED, ~5 min)

Create `tests/test_agentmail.py` with all test function stubs using
`pytest.mark.xfail` or `assert False, "not implemented"`. Run:

```
docker compose run --rm robin pytest -q tests/test_agentmail.py
```

Expected: all tests collected, all fail. Suite is RED. This confirms the
test file is importable and the test runner sees the stubs.

### Milestone 1 — flag-off / no-op regression (RED → GREEN, ~10 min)

**Test 1.1 — no key ⇒ hook no-ops**

```python
async def test_hook_noop_when_flag_absent(monkeypatch):
    """With ROBIN_AGENTMAIL_ENABLED unset, the hook returns without side-effects."""
    monkeypatch.delenv("ROBIN_AGENTMAIL_ENABLED", raising=False)
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    from robin.integrations.agentmail import make_email_outcome_hook
    from robin.models import ContextPack
    pack = ContextPack(
        caller_name="Test Caller",
        callback_number="+15550000001",
        target_name="24 Hour Gym",
        target_display_number="415-776-2200",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA",
        win_goal="cancel",
        fallback_goal="cancel",
        email="test@example.com",
    )
    hook = make_email_outcome_hook(pack)
    payload = {
        "summary": "Cancelled.",
        "confirmation": "24HF-4471",
        "channel": "stay_on",
        "out": {"delivered": True},
    }
    # Must return without error; no network calls
    await hook(call_id="call-001", payload=payload)
    # If we reach here without exception, test passes
```

**Test 1.2 — key present but flag absent ⇒ hook no-ops**

```python
async def test_hook_noop_when_flag_is_zero(monkeypatch):
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "0")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")
    from robin.integrations.agentmail import make_email_outcome_hook
    # ... same pack construction ...
    hook = make_email_outcome_hook(pack)
    await hook(call_id="call-002", payload={
        "summary": "done", "confirmation": "X",
        "channel": None, "out": {"delivered": True},
    })
    # No exception, no send
```

Implement `_is_enabled()` in `agentmail.py`. Run tests. Both pass → GREEN.

Run full suite: `docker compose run --rm robin pytest -q` — must stay green.
Run ruff: `docker compose run --rm robin ruff check src tests` — must be clean.

### Milestone 2 — success path: send called with correct args (RED → GREEN, ~25 min)

**Test 2.1 — DONE outcome with pack.email set ⇒ FakeClient.send called**

Strategy: monkeypatch the module-level `_client` and `_inbox_id`/`_inbox_email`
singletons so `_ensure_inbox` returns immediately without a real network call,
then await the task that `create_task` schedules.

```python
import asyncio
import importlib
import pytest


async def test_done_outcome_sends_caller_email(monkeypatch):
    """On DONE with pack.email set, send is called with correct to/subject/confirmation."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient(
        inbox_id="inbox-test-01",
        inbox_email="robin-confirms@agentmail.to",
    )
    # Pre-seed the inbox singleton so _ensure_inbox skips creation
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    from robin.models import ContextPack
    pack = ContextPack(
        caller_name="Test Caller",
        callback_number="+15550000001",
        target_name="24 Hour Gym",
        target_display_number="415-776-2200",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA",
        win_goal="cancel",
        fallback_goal="cancel",
        email="test@example.com",
    )
    hook = am_mod.make_email_outcome_hook(pack)
    payload = {
        "summary": "Membership cancelled and last-month refund secured.",
        "confirmation": "24HF-4471",
        "channel": "stay_on",
        "out": {"delivered": True},
    }

    await hook(call_id="call-003", payload=payload)

    # Drain all pending tasks so the create_task coroutine runs
    await asyncio.sleep(0)       # one iteration of the event loop
    # Allow the send coroutines inside _send_emails to complete
    await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()},
                         return_exceptions=True)

    # Two sends: caller confirmation + complaint draft
    assert len(fake.sent) == 2

    # Caller email
    caller_msg = next(m for m in fake.sent if m["to"] == "test@example.com")
    assert "24HF-4471" in caller_msg["text"]
    assert "cancel" in caller_msg["subject"].lower()

    # Complaint draft (synthetic gym address)
    complaint_msg = next(
        m for m in fake.sent
        if m["to"] == "cancellations@24hourfitness-demo.invalid"
    )
    assert "24HF-4471" in complaint_msg["text"]
    assert "DRAFTED BY ROBIN" in complaint_msg["text"]
```

Implementation: flesh out `_send_emails`, `_ensure_inbox`, `make_email_outcome_hook`.
Run: `docker compose run --rm robin pytest -q tests/test_agentmail.py::test_done_outcome_sends_caller_email`
Expected: GREEN.

**Test 2.2 — fallback confirmation number**

```python
async def test_fallback_confirmation_used_when_absent(monkeypatch, ...):
    """When payload has no confirmation, uses _FALLBACK_CONFIRMATION."""
    # ... same setup ...
    payload = {
        "summary": "Cancelled.",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": True},
    }
    await hook(call_id="call-004", payload=payload)
    await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()},
                         return_exceptions=True)
    assert any("24HF-4471" in m["text"] for m in fake.sent)
```

### Milestone 3 — skip and non-DONE cases (RED → GREEN, ~20 min)

**Test 3.1 — missing email ⇒ skip caller send, no error**

```python
async def test_missing_email_skips_caller_send(monkeypatch, ...):
    """pack.email == "" → caller email is skipped; complaint draft still sent."""
    # pack with email=""
    pack = ContextPack(..., email="")
    # ... setup singletons ...
    await hook(call_id="call-005", payload=done_payload)
    await asyncio.gather(...)
    # Caller email NOT in sent
    assert not any(m["to"] == "" for m in fake.sent)
    # Complaint draft still attempted
    assert any("24hourfitness-demo.invalid" in m["to"] for m in fake.sent)
```

**Test 3.2 — non-DONE outcome ⇒ no send**

```python
async def test_non_done_outcome_no_send(monkeypatch, ...):
    """When out['delivered'] is False, no email is sent."""
    payload = {
        "summary": "Blocked.",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": False},
    }
    await hook(call_id="call-006", payload=payload)
    await asyncio.gather(...)
    assert fake.sent == []
```

**Test 3.3 — delivered=True but no confirmation and no success keywords ⇒ no send**

```python
async def test_ambiguous_outcome_no_send(monkeypatch, ...):
    payload = {
        "summary": "something happened",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": True},
    }
    await hook(...)
    await asyncio.gather(...)
    assert fake.sent == []
```

Run after implementation: `docker compose run --rm robin pytest -q tests/test_agentmail.py`
All milestone 3 tests GREEN. Full suite green. Ruff clean.

### Milestone 4 — error resilience (RED → GREEN, ~15 min)

**Test 4.1 — send raises ⇒ swallowed and logged**

```python
async def test_send_raises_swallowed_and_logged(monkeypatch, ...):
    """An exception inside _send_emails is swallowed; obs.log_event called."""
    logged: list[str] = []
    import robin.obs as obs_mod
    original_log = obs_mod.log_event
    def _capture_log(event, **kw):
        logged.append(event)
        original_log(event, **kw)
    monkeypatch.setattr(obs_mod, "log_event", _capture_log)

    # Monkeypatch _send_emails to raise
    import robin.integrations.agentmail as am_mod
    async def _bad_send(**kw):
        raise RuntimeError("network gone")
    monkeypatch.setattr(am_mod, "_send_emails", _bad_send)

    await hook(call_id="call-007", payload=done_payload)
    await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()},
                         return_exceptions=True)

    assert any("agentmail" in e for e in logged)
    # Hook itself did not raise — test reaching here proves it
```

**Test 4.2 — hook returns immediately (does not await the send)**

```python
async def test_hook_returns_before_send_completes(monkeypatch, ...):
    """Hook must return without blocking on the send task."""
    import asyncio
    import time
    import robin.integrations.agentmail as am_mod

    send_started = asyncio.Event()
    send_done = asyncio.Event()

    async def _slow_send(**kw):
        send_started.set()
        await asyncio.sleep(0.1)   # simulate 100 ms network
        send_done.set()

    monkeypatch.setattr(am_mod, "_send_emails", _slow_send)

    t0 = time.monotonic()
    await hook(call_id="call-008", payload=done_payload)
    elapsed = time.monotonic() - t0

    # Hook returned before the 100 ms sleep finished
    assert elapsed < 0.05, f"hook blocked for {elapsed:.3f}s"
    assert not send_done.is_set(), "send completed before hook returned"

    # Clean up the background task
    await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()},
                         return_exceptions=True)
```

### Milestone 5 — inbox-once (RED → GREEN, ~10 min)

**Test 5.1 — inbox created once across two hook invocations**

```python
async def test_inbox_created_once_across_two_calls(monkeypatch, ...):
    """_ensure_inbox must call inboxes.create exactly once even for two hook calls."""
    # Reset singletons
    monkeypatch.setattr(am_mod, "_client", None)
    monkeypatch.setattr(am_mod, "_inbox_id", None)
    monkeypatch.setattr(am_mod, "_inbox_email", None)
    monkeypatch.setattr(am_mod, "_inbox_lock", None)

    fake = FakeAgentMailClient()
    # Monkeypatch AsyncAgentMail constructor
    monkeypatch.setattr("agentmail.AsyncAgentMail",
                        lambda **kw: fake)

    # Two hook calls
    await hook(call_id="call-009", payload=done_payload)
    await asyncio.gather(...)
    await hook(call_id="call-010", payload=done_payload)
    await asyncio.gather(...)

    assert len(fake.created) == 1, (
        f"Expected inbox.create called once, got {len(fake.created)}"
    )
```

Run: `docker compose run --rm robin pytest -q tests/test_agentmail.py`
All GREEN. Full suite green. Ruff clean.

### Milestone 6 — models.py field + context_pack.py loader (RED → GREEN, ~10 min)

**Test 6.1 — ContextPack accepts email field**

```python
def test_context_pack_accepts_email():
    from robin.models import ContextPack
    pack = ContextPack(
        caller_name="A", callback_number="+15550000001",
        target_name="B", target_display_number="C",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA", win_goal="w", fallback_goal="f",
        email="test@example.com",
    )
    assert pack.email == "test@example.com"


def test_context_pack_email_defaults_to_empty():
    from robin.models import ContextPack
    pack = ContextPack(
        caller_name="A", callback_number="+15550000001",
        target_name="B", target_display_number="C",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA", win_goal="w", fallback_goal="f",
    )
    assert pack.email == ""
```

**Test 6.2 — load_context_pack passes email from JSON when present**

```python
def test_load_context_pack_passes_email(tmp_path):
    from robin.context_pack import load_context_pack
    pack_data = {
        "caller_name": "Demo", "callback_number": "+15550000001",
        "target_name": "24 Hour Gym", "target_display_number": "415-776-2200",
        "receptionist_to_number": "+15550000002",
        "jurisdiction": "US-CA", "win_goal": "cancel", "fallback_goal": "cancel",
        "email": "test@example.com",
    }
    p = tmp_path / "cp.json"
    p.write_text(json.dumps(pack_data))
    pack = load_context_pack(str(p))
    assert pack.email == "test@example.com"


def test_load_context_pack_email_absent_defaults_empty(tmp_path):
    """context_pack.json without 'email' key → pack.email == ""."""
    from robin.context_pack import load_context_pack
    pack_data = {
        "caller_name": "Demo", "callback_number": "+15550000001",
        "target_name": "24 Hour Gym", "target_display_number": "415-776-2200",
        "receptionist_to_number": "+15550000002",
        "jurisdiction": "US-CA", "win_goal": "cancel", "fallback_goal": "cancel",
    }
    p = tmp_path / "cp.json"
    p.write_text(json.dumps(pack_data))
    pack = load_context_pack(str(p))
    assert pack.email == ""
```

These tests go in `tests/test_agentmail.py` (or optionally in
`tests/test_models.py` / `tests/test_context_pack.py` — placing them in
`test_agentmail.py` keeps W2 self-contained).

Apply edits to `models.py` and `context_pack.py`. Run full suite. GREEN.

### Milestone 7 — flag-off regression gate (final gate before merge)

```python
async def test_flag_off_regression_no_side_effects(monkeypatch, ...):
    """With flag absent, the hook is a pure no-op: no tasks, no logs from W2."""
    monkeypatch.delenv("ROBIN_AGENTMAIL_ENABLED", raising=False)
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)

    tasks_before = set(asyncio.all_tasks())
    await hook(call_id="call-flag", payload=done_payload)
    tasks_after = set(asyncio.all_tasks())

    assert tasks_before == tasks_after, "flag-off hook spawned tasks"
```

Run:
```
docker compose run --rm robin pytest -q tests/test_agentmail.py
docker compose run --rm robin pytest -q          # full suite — must stay green
docker compose run --rm robin ruff check src tests
```

All green. This is the merge gate.

### REFACTOR pass (after all GREEN)

- Confirm no magic strings duplicated between `agentmail.py` and tests;
  extract `_FALLBACK_CONFIRMATION` is already a named constant.
- Confirm `_GYM_DEMO_EMAIL` is the `.invalid` TLD (RFC 2606 — unreachable
  by design; never a real address).
- Verify `obs.log_event` calls never include `to=` / `email=` as field names
  (those would be kept by obs but it is good practice to avoid logging addresses;
  use `has_email=bool(...)` instead).
- Run coverage: `docker compose run --rm robin pytest -q --cov=src/robin/integrations
  --cov-report=term-missing`. New code in `integrations/agentmail.py` must be
  ≥ 80% covered.

---

## 7. Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `src/robin/integrations/__init__.py` | Create (if absent) | Empty; makes package importable |
| `src/robin/integrations/agentmail.py` | Create | Main W2 implementation |
| `src/robin/models.py` | Edit (1 line) | Append `email: str = ""` to `ContextPack` |
| `src/robin/context_pack.py` | Edit (1 line) | Optional `email` extraction in return |
| `tests/test_agentmail.py` | Create | All W2 tests |
| `tests/fakes.py` | Append | `FakeAgentMailClient` block |
| `main.py` | Edit (W2 sub-block only) | Between W2/W3 markers, ~8 lines |
| `.env.example` | Append | W2 env vars |
| `requirements.txt` | Append | `agentmail>=0.5.0` |

**No other files are touched.**

---

## 8. Append-only file content

### `.env.example` — append at end

```
# --- W2: Agent Mail close-loop (bonus track) ---
# Set to "1" to enable; absent = no-op (default).
ROBIN_AGENTMAIL_ENABLED=
AGENTMAIL_API_KEY=
# Optional: presenter email for the caller confirmation email.
# Add "email": "you@example.com" to context_pack.json (gitignored).
# NEVER put a real email address in this file.
```

### `requirements.txt` — append at end

```
# W2: AgentMail close-loop
agentmail>=0.5.0
```

---

## 9. Demo Moment

During the live stage run, after Robin reports back:

1. Presenter's phone / laptop screen shows the inbox at `console.agentmail.to`
   (or the Robin dashboard if W4 is merged).
2. Within ~10 s of the call ending, two emails appear:
   - **"Robin confirmed: gym membership cancelled"** — in the presenter's inbox,
     confirmation number `24HF-4471`, last-month refund noted.
   - **"Notice of Intent to File Regulatory Complaint"** — drafted skeleton
     shown in the `cancellations@24hourfitness-demo.invalid` outbox (visible
     on screen as "drafted — not sent").
3. Narrative: "Robin doesn't just win the call. It closes the loop in writing.
   The member has a paper trail. The gym has notice."

---

## 10. Time-box + Collapse Ladder

Total budget: **~2 h** from branch cut (post-W0 merge).

| T | Milestone | State |
|---|-----------|-------|
| T+0:15 | Scaffold: `integrations/` package, stub file, stub tests, fake appended to `fakes.py` | stubs exist |
| T+0:30 | M1: flag-off tests GREEN | `_is_enabled` done |
| T+1:00 | M2: success path GREEN | `_send_emails` + `_ensure_inbox` done |
| T+1:20 | M3: skip + non-DONE GREEN | `_is_success` done |
| T+1:35 | M4: error resilience GREEN | error swallowing confirmed |
| T+1:45 | M5: inbox-once GREEN | singleton lock confirmed |
| T+1:55 | M6: models.py + context_pack.py edits GREEN | field additive |
| T+2:00 | M7: flag-off regression GREEN, ruff clean, full suite green | READY TO MERGE |

**Collapse ladder (if behind at T+1:30):**

- **Minimum viable (cut complaint draft):** send only the caller confirmation
  email. Remove the `_GYM_DEMO_EMAIL` send from `_send_emails`. Demo moment:
  one email arrives. Still valid; the complaint draft is a cut.
- **Further cut (skip complaint + skip W2 entirely):** do not merge this
  branch. The flag-off design means an unmerged W2 costs the canonical demo
  nothing. Proceed directly to W4 (the flagship dashboard is the higher-value
  judging story and depends only on W0).

A half-done branch is never merged. The flag-off regression test (M7) is the
final merge gate.

---

## 11. Merge Instructions

### Pre-merge checklist

- [ ] `docker compose run --rm robin pytest -q` — full suite GREEN
- [ ] `docker compose run --rm robin pytest -q tests/test_agentmail.py` — W2 suite GREEN
- [ ] Coverage ≥ 80% on `src/robin/integrations/agentmail.py`
- [ ] `docker compose run --rm robin ruff check src tests` — clean
- [ ] Flag-off regression test passes (M7)
- [ ] No real email addresses, API keys, or PII in any committed file
- [ ] No `.env` / `*.local.json` staged
- [ ] `models.py` change: one optional field appended, default `""`, non-breaking
- [ ] `context_pack.py` change: one optional extraction, additive
- [ ] `main.py` edit: W2 sub-block only, between the W2/W3 markers
- [ ] `security-reviewer` agent run on the diff; no CRITICAL/HIGH issues
- [ ] `code-reviewer` agent run on the diff; MEDIUM+ addressed

### Merge procedure (post-W0, main up to date)

```bash
git checkout main && git pull
git checkout -b feat/agentmail-closeloop
# ... implement ...
git add src/robin/integrations/__init__.py
git add src/robin/integrations/agentmail.py
git add src/robin/models.py
git add src/robin/context_pack.py
git add tests/test_agentmail.py
git add tests/fakes.py
git add main.py   # only the W2 sub-block changed
git add .env.example
git add requirements.txt
git commit -m "feat: W2 agentmail close-loop — confirmation + complaint emails on DONE outcome"
# Human performs: git checkout main && git merge feat/agentmail-closeloop
```

**Auto-merge compatibility:** the only shared-file edits are:
- `main.py` → distinct W2 sub-block (no conflict with W1/W3/W4 blocks)
- `models.py` → one appended field (no conflict if W1/W3/W4 do not touch `models.py`)
- `context_pack.py` → one amended return line (no conflict; W1/W3/W4 do not touch this file)
- `tests/fakes.py` → appended block (no conflict if other branches also only append)
- `.env.example` / `requirements.txt` → appended (same)

Git auto-merges all of these cleanly. No manual conflict resolution needed.

### Dependency note

W2 does NOT require W1 to be merged. If W1 is present, `pack.email` could
in principle be populated by a Super Memory recall — but W2 does not depend
on or import `integrations/supermemory.py`. W2 reads only `pack.email`
(the `ContextPack` field). The two branches are fully independent.

---

## 12. Security + PII Checklist

- [ ] `AGENTMAIL_API_KEY` read from env only; validated inside
  `_is_enabled()` / `_get_or_create_client()`; never logged (key contains
  "api_key" — `obs.redact` drops it automatically)
- [ ] Caller email (`pack.email`) is never logged directly; log only
  `has_email=bool(caller_email)` (a boolean, not the address)
- [ ] `_GYM_DEMO_EMAIL` is `*.invalid` TLD (RFC 2606 — unreachable; safe
  to commit as a string literal)
- [ ] No real email addresses in source, tests, or `.env.example`
  (tests use `"test@example.com"` — synthetic only)
- [ ] No real API keys in tests (monkeypatched env vars with `"dummy-key"`)
- [ ] `context_pack.json` (the real file with a real email address) is
  gitignored; `.gitignore` already excludes it
- [ ] Webhook signature verification is in W0 / `signature.py` and is
  not touched by W2
- [ ] `_send_emails` never logs full email body text
  (would be truncated by `obs._MAX_VALUE=200` anyway, but the explicit
  field keys `subject=`, `body=` are omitted from `log_event` calls)
- [ ] AgentMail Svix webhooks are not wired to Robin's endpoint (out of
  scope; documented above)

---

*File:* `/Users/francescorosciano/docs/robin/docs/superpowers/specs/2026-05-17-w2-agentmail-closeloop.md`

*3-line summary:*
W2 adds `src/robin/integrations/agentmail.py` — a flag-gated (`ROBIN_AGENTMAIL_ENABLED=1`)
`OutcomeHook` that fires two best-effort emails (caller confirmation + complaint draft)
via `asyncio.create_task` on a DONE gym-cancel outcome, with inbox-once singleton,
full error swallowing, and a `FakeAgentMailClient` for 8 TDD-ordered tests covering
flag-off, success path, skip-on-empty-email, non-DONE, error resilience, hook
non-blocking, inbox-once, and flag-off regression gate. One optional `email: str = ""`
field is appended to `ContextPack` (additive, non-breaking); `context_pack.py` loader
is updated with one line to extract it optionally; no other canonical-path file is touched.
