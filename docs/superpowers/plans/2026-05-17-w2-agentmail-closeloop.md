# W2 AgentMail Close-Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a successful gym-cancel outcome, Robin sends a real caller confirmation email + a drafted regulator-complaint email via AgentMail (fire-and-forget); byte-identical to today when ROBIN_AGENTMAIL_ENABLED is unset.

**Architecture:** A new `src/robin/integrations/agentmail.py` exposes `make_email_outcome_hook(pack)` returning a W0 `OutcomeHook` that, when `ROBIN_AGENTMAIL_ENABLED=1` and `AGENTMAIL_API_KEY` are set and the outcome is a DONE gym-cancel, fires two best-effort emails via `asyncio.create_task(_send_emails(...))` against an `AsyncAgentMail` client with an inbox-once module-level singleton (guarded by a lazily-created `asyncio.Lock`); the hook returns immediately and swallows every error into a single `obs.log_event`. It is registered through the delimited `# >>> W2 agentmail wiring <<<` sub-block in `main.py` (rebuilding `_hooks` immutably) and reads one new optional `email: str = ""` field appended last on `ContextPack`, populated by a one-line additive change to the `context_pack.py` loader. W2 depends on W0 (`feat/extension-seam`) being merged to `main` first.

**Tech Stack:** Python 3.12, agentmail>=0.5.0 SDK, pytest + pytest-asyncio, Docker (all runs inside the container).

---

## File Structure

```
robin/
  src/robin/
    integrations/
      __init__.py          # CREATE if absent — empty; makes package importable
      agentmail.py          # CREATE — primary W2 deliverable
    models.py               # EDIT (1 line) — append `email: str = ""` to ContextPack
    context_pack.py         # EDIT (1 line) — optional `email` extraction in return
    main.py                 # EDIT — W2 sub-block only, between the W2/W3 markers
  tests/
    test_agentmail.py       # CREATE — all W2 tests
    fakes.py                # APPEND — FakeAgentMailClient block (no existing content modified)
  .env.example              # APPEND — W2 env vars block at end
  requirements.txt          # APPEND — `agentmail>=0.5.0` at end
```

No other files are touched. `loop.py`, `app.py`, `stage.py`, `classifier.py`,
`signature.py`, and every locked prompt fixture are untouched by W2.

---

### Task 1: Branch + scaffold the integrations package and stub test file (RED)

Cut the branch from post-W0 `main` and create the importable test
scaffold so the test runner can see W2's stubs failing. (Spec Milestone 0.)

- [ ] **Step 1:** Create the W2 branch from up-to-date post-W0 `main`:

```bash
git checkout main && git pull
git checkout -b feat/agentmail-closeloop
```

- [ ] **Step 2:** Create `src/robin/integrations/__init__.py` as an empty
  file (skip the create only if W1 already created it — the file is empty
  either way, so creating it idempotently is safe):

```python
```

  (The file is intentionally empty — zero bytes / a single newline — making
  `robin.integrations` an importable package.)

- [ ] **Step 3:** Create the scaffold `tests/test_agentmail.py` with every
  W2 test function present as a failing stub so collection succeeds and the
  suite is RED:

```python
"""W2 AgentMail close-loop tests (scaffold — RED until implemented)."""
import asyncio
import json

import pytest


def _pack(email: str = "test@example.com"):
    """Build a ContextPack with synthetic data only."""
    from robin.models import ContextPack

    return ContextPack(
        caller_name="Test Caller",
        callback_number="+15550000001",
        target_name="24 Hour Gym",
        target_display_number="415-776-2200",
        receptionist_to_number="+15550000002",
        jurisdiction="US-CA",
        win_goal="cancel",
        fallback_goal="cancel",
        email=email,
    )


_DONE_PAYLOAD = {
    "summary": "Membership cancelled and last-month refund secured.",
    "confirmation": "24HF-4471",
    "channel": "stay_on",
    "out": {"delivered": True},
}


async def _drain():
    """Run every pending task to completion (best-effort)."""
    await asyncio.sleep(0)
    await asyncio.gather(
        *(asyncio.all_tasks() - {asyncio.current_task()}),
        return_exceptions=True,
    )


async def test_hook_noop_when_flag_absent(monkeypatch):
    assert False, "not implemented"


async def test_hook_noop_when_flag_is_zero(monkeypatch):
    assert False, "not implemented"


async def test_done_outcome_sends_caller_email(monkeypatch):
    assert False, "not implemented"


async def test_fallback_confirmation_used_when_absent(monkeypatch):
    assert False, "not implemented"


async def test_missing_email_skips_caller_send(monkeypatch):
    assert False, "not implemented"


async def test_non_done_outcome_no_send(monkeypatch):
    assert False, "not implemented"


async def test_ambiguous_outcome_no_send(monkeypatch):
    assert False, "not implemented"


async def test_send_raises_swallowed_and_logged(monkeypatch):
    assert False, "not implemented"


async def test_hook_returns_before_send_completes(monkeypatch):
    assert False, "not implemented"


async def test_inbox_created_once_across_two_calls(monkeypatch):
    assert False, "not implemented"


def test_context_pack_accepts_email():
    assert False, "not implemented"


def test_context_pack_email_defaults_to_empty():
    assert False, "not implemented"


def test_load_context_pack_passes_email(tmp_path):
    assert False, "not implemented"


def test_load_context_pack_email_absent_defaults_empty(tmp_path):
    assert False, "not implemented"


async def test_flag_off_regression_no_side_effects(monkeypatch):
    assert False, "not implemented"
```

- [ ] **Step 4:** Run the scaffold and confirm the suite is RED (all tests
  collected, all fail — proves the file is importable and the runner sees
  the stubs):

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py
```

  Expected: collection succeeds; every test FAILS with
  `AssertionError: not implemented`. No collection/import error.

- [ ] **Step 5:** Commit the scaffold:

```bash
git add src/robin/integrations/__init__.py tests/test_agentmail.py
git commit -m "test: W2 agentmail scaffold — integrations package + failing stubs"
```

---

### Task 2: Append `FakeAgentMailClient` to `tests/fakes.py`

Append the in-memory fake that mimics `agentmail.AsyncAgentMail` for unit
tests. Append-only; no existing content in `tests/fakes.py` is modified.
(Spec §5.3.)

- [ ] **Step 1:** Read `tests/fakes.py` so the append target (end of file)
  is known and no existing content is altered.

- [ ] **Step 2:** Append the `FakeAgentMailClient` block verbatim at the
  end of `tests/fakes.py`:

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

  Note: `raise_on_send` is stored for future use but `_FakeMessages` above
  does not implement it — tests that need send errors monkeypatch
  `_send_emails` directly (see Task 7).

- [ ] **Step 3:** Confirm `tests/fakes.py` still imports cleanly (no
  behavior change to existing fakes):

```bash
docker compose run --rm robin python -c "import tests.fakes; print(tests.fakes.FakeAgentMailClient)"
```

  Expected: prints `<class 'tests.fakes.FakeAgentMailClient'>`, no error.

- [ ] **Step 4:** Commit the fake:

```bash
git add tests/fakes.py
git commit -m "test: W2 append FakeAgentMailClient to tests/fakes.py"
```

---

### Task 3: Flag-off / no-op regression — `_is_enabled()` (RED → GREEN)

Implement only `_is_enabled()` and the inert hook factory so the two
flag-off no-op tests pass. (Spec Milestone 1.)

- [ ] **Step 1:** Replace the `test_hook_noop_when_flag_absent` stub in
  `tests/test_agentmail.py` with the full failing test:

```python
async def test_hook_noop_when_flag_absent(monkeypatch):
    """With ROBIN_AGENTMAIL_ENABLED unset, the hook returns without side-effects."""
    monkeypatch.delenv("ROBIN_AGENTMAIL_ENABLED", raising=False)
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    from robin.integrations.agentmail import make_email_outcome_hook

    hook = make_email_outcome_hook(_pack("test@example.com"))
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

- [ ] **Step 2:** Replace the `test_hook_noop_when_flag_is_zero` stub with
  the full failing test:

```python
async def test_hook_noop_when_flag_is_zero(monkeypatch):
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "0")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")
    from robin.integrations.agentmail import make_email_outcome_hook

    hook = make_email_outcome_hook(_pack("test@example.com"))
    await hook(call_id="call-002", payload={
        "summary": "done", "confirmation": "X",
        "channel": None, "out": {"delivered": True},
    })
    # No exception, no send
```

- [ ] **Step 3:** Run the two tests and confirm they FAIL (module
  `robin.integrations.agentmail` does not exist yet):

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_hook_noop_when_flag_absent tests/test_agentmail.py::test_hook_noop_when_flag_is_zero
```

  Expected: both FAIL with `ModuleNotFoundError: No module named 'robin.integrations.agentmail'`.

- [ ] **Step 4:** Create `src/robin/integrations/agentmail.py` with the
  full module — docstring, imports, module-level singletons, constants,
  `_is_enabled`, `_get_or_create_client`, `_get_lock`, `_ensure_inbox`,
  `_is_success`, `_send_emails`, and `make_email_outcome_hook` — exactly
  as specified (this is the complete final file; later tasks only add
  tests against it, not re-edit it):

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

- [ ] **Step 5:** Run the two flag-off tests and confirm GREEN:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_hook_noop_when_flag_absent tests/test_agentmail.py::test_hook_noop_when_flag_is_zero
```

  Expected: both PASS.

- [ ] **Step 6:** Run the full suite and ruff to confirm no regression and
  clean lint:

```bash
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

  Expected: full suite GREEN; ruff reports no issues.

- [ ] **Step 7:** Commit:

```bash
git add src/robin/integrations/agentmail.py tests/test_agentmail.py
git commit -m "feat: W2 agentmail _is_enabled + inert hook factory (flag-off no-op GREEN)"
```

---

### Task 4: Success path — send called with correct args (RED → GREEN)

Add the two success-path tests that exercise the already-implemented
`_send_emails` / `_ensure_inbox` / `make_email_outcome_hook` via the fake.
(Spec Milestone 2.)

- [ ] **Step 1:** Replace the `test_done_outcome_sends_caller_email` stub
  with the full test:

```python
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

    pack = _pack("test@example.com")
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
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
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

- [ ] **Step 2:** Replace the `test_fallback_confirmation_used_when_absent`
  stub with the full test:

```python
async def test_fallback_confirmation_used_when_absent(monkeypatch):
    """When payload has no confirmation, uses _FALLBACK_CONFIRMATION."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "Cancelled.",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": True},
    }
    await hook(call_id="call-004", payload=payload)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    assert any("24HF-4471" in m["text"] for m in fake.sent)
```

- [ ] **Step 3:** Run both success-path tests and confirm GREEN (the
  implementation from Task 3 already supports them):

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_done_outcome_sends_caller_email tests/test_agentmail.py::test_fallback_confirmation_used_when_absent
```

  Expected: both PASS.

- [ ] **Step 4:** Commit:

```bash
git add tests/test_agentmail.py
git commit -m "test: W2 success-path tests — caller email + fallback confirmation GREEN"
```

---

### Task 5: Skip and non-DONE cases — `_is_success` behavior (RED → GREEN)

Add the three tests pinning skip-on-empty-email, non-DONE, and ambiguous
outcomes. (Spec Milestone 3.)

- [ ] **Step 1:** Replace the `test_missing_email_skips_caller_send` stub
  with the full test:

```python
async def test_missing_email_skips_caller_send(monkeypatch):
    """pack.email == "" → caller email is skipped; complaint draft still sent."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack(""))
    await hook(call_id="call-005", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    # Caller email NOT in sent (no empty-to send)
    assert not any(m["to"] == "" for m in fake.sent)
    # Complaint draft still attempted
    assert any("24hourfitness-demo.invalid" in m["to"] for m in fake.sent)
```

- [ ] **Step 2:** Replace the `test_non_done_outcome_no_send` stub with the
  full test:

```python
async def test_non_done_outcome_no_send(monkeypatch):
    """When out['delivered'] is False, no email is sent."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "Blocked.",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": False},
    }
    await hook(call_id="call-006", payload=payload)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    assert fake.sent == []
```

- [ ] **Step 3:** Replace the `test_ambiguous_outcome_no_send` stub with the
  full test:

```python
async def test_ambiguous_outcome_no_send(monkeypatch):
    """delivered=True but no confirmation and no success keywords → no send."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    fake = FakeAgentMailClient()
    monkeypatch.setattr(am_mod, "_client", fake)
    monkeypatch.setattr(am_mod, "_inbox_id", "inbox-test-01")
    monkeypatch.setattr(am_mod, "_inbox_email", "robin-confirms@agentmail.to")

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    payload = {
        "summary": "something happened",
        "confirmation": None,
        "channel": None,
        "out": {"delivered": True},
    }
    await hook(call_id="call-006b", payload=payload)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    assert fake.sent == []
```

- [ ] **Step 4:** Run the three tests and confirm GREEN:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_missing_email_skips_caller_send tests/test_agentmail.py::test_non_done_outcome_no_send tests/test_agentmail.py::test_ambiguous_outcome_no_send
```

  Expected: all three PASS.

- [ ] **Step 5:** Commit:

```bash
git add tests/test_agentmail.py
git commit -m "test: W2 skip + non-DONE + ambiguous outcome tests GREEN"
```

---

### Task 6: Error resilience — swallow + non-blocking (RED → GREEN)

Add the two resilience tests proving `_send_emails` errors are swallowed
and logged, and that the hook returns before the send completes.
(Spec Milestone 4.)

- [ ] **Step 1:** Replace the `test_send_raises_swallowed_and_logged` stub
  with the full test:

```python
async def test_send_raises_swallowed_and_logged(monkeypatch):
    """An exception inside _send_emails is swallowed; obs.log_event called."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

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

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    await hook(call_id="call-007", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)

    assert any("agentmail" in e for e in logged)
    # Hook itself did not raise — test reaching here proves it
```

- [ ] **Step 2:** Replace the `test_hook_returns_before_send_completes`
  stub with the full test:

```python
async def test_hook_returns_before_send_completes(monkeypatch):
    """Hook must return without blocking on the send task."""
    import time

    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod

    send_started = asyncio.Event()
    send_done = asyncio.Event()

    async def _slow_send(**kw):
        send_started.set()
        await asyncio.sleep(0.1)   # simulate 100 ms network
        send_done.set()

    monkeypatch.setattr(am_mod, "_send_emails", _slow_send)

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    t0 = time.monotonic()
    await hook(call_id="call-008", payload=_DONE_PAYLOAD)
    elapsed = time.monotonic() - t0

    # Hook returned before the 100 ms sleep finished
    assert elapsed < 0.05, f"hook blocked for {elapsed:.3f}s"
    assert not send_done.is_set(), "send completed before hook returned"

    # Clean up the background task
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
```

- [ ] **Step 3:** Run both resilience tests and confirm GREEN:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_send_raises_swallowed_and_logged tests/test_agentmail.py::test_hook_returns_before_send_completes
```

  Expected: both PASS.

- [ ] **Step 4:** Commit:

```bash
git add tests/test_agentmail.py
git commit -m "test: W2 error-resilience tests — swallow + non-blocking GREEN"
```

---

### Task 7: Inbox-once singleton (RED → GREEN)

Add the test proving `inboxes.create` is called exactly once across two
hook invocations even when the singletons start unset. (Spec Milestone 5.)

- [ ] **Step 1:** Replace the `test_inbox_created_once_across_two_calls`
  stub with the full test:

```python
async def test_inbox_created_once_across_two_calls(monkeypatch):
    """_ensure_inbox must call inboxes.create exactly once even for two hook calls."""
    monkeypatch.setenv("ROBIN_AGENTMAIL_ENABLED", "1")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "dummy-key")

    import robin.integrations.agentmail as am_mod
    from tests.fakes import FakeAgentMailClient

    # Reset singletons so _ensure_inbox actually creates
    monkeypatch.setattr(am_mod, "_client", None)
    monkeypatch.setattr(am_mod, "_inbox_id", None)
    monkeypatch.setattr(am_mod, "_inbox_email", None)
    monkeypatch.setattr(am_mod, "_inbox_lock", None)

    fake = FakeAgentMailClient()
    # Monkeypatch AsyncAgentMail constructor so _get_or_create_client returns the fake
    monkeypatch.setattr("agentmail.AsyncAgentMail", lambda **kw: fake)

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))

    # Two hook calls
    await hook(call_id="call-009", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)
    await hook(call_id="call-010", payload=_DONE_PAYLOAD)
    await asyncio.gather(*(asyncio.all_tasks() - {asyncio.current_task()}),
                         return_exceptions=True)

    assert len(fake.created) == 1, (
        f"Expected inbox.create called once, got {len(fake.created)}"
    )
```

- [ ] **Step 2:** Run the inbox-once test and confirm GREEN:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_inbox_created_once_across_two_calls
```

  Expected: PASS (`fake.created` length is exactly 1).

- [ ] **Step 3:** Commit:

```bash
git add tests/test_agentmail.py
git commit -m "test: W2 inbox-once singleton test GREEN"
```

---

### Task 8: `models.py` field + `context_pack.py` loader (RED → GREEN)

Apply the one-line `models.py` field append and the one-line
`context_pack.py` loader change, pinned by four tests. This is the one
allowed canonical-path edit for the whole portfolio (additive, defaulted,
non-breaking). (Spec Milestone 6, §3.1, §3.2.)

- [ ] **Step 1:** Add `import json` to the top of `tests/test_agentmail.py`
  if not already present (the scaffold in Task 1 already imports it — if
  Task 1's scaffold was followed verbatim, `json` is present and this step
  is a no-op verification).

- [ ] **Step 2:** Replace the `test_context_pack_accepts_email` stub with
  the full test:

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
```

- [ ] **Step 3:** Replace the `test_context_pack_email_defaults_to_empty`
  stub with the full test:

```python
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

- [ ] **Step 4:** Replace the `test_load_context_pack_passes_email` stub
  with the full test:

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
```

- [ ] **Step 5:** Replace the
  `test_load_context_pack_email_absent_defaults_empty` stub with the full
  test:

```python
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

- [ ] **Step 6:** Run the four tests and confirm they FAIL (no `email`
  field / loader extraction yet):

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_context_pack_accepts_email tests/test_agentmail.py::test_context_pack_email_defaults_to_empty tests/test_agentmail.py::test_load_context_pack_passes_email tests/test_agentmail.py::test_load_context_pack_email_absent_defaults_empty
```

  Expected: `test_context_pack_accepts_email` and
  `test_load_context_pack_passes_email` FAIL (unexpected `email` kwarg /
  missing attribute); the two defaults tests FAIL on the missing `.email`
  attribute.

- [ ] **Step 7:** Read `src/robin/models.py`, then append `email: str = ""`
  as the **last** field of the `ContextPack` frozen dataclass, immediately
  after `fallback_goal: str`, so the dataclass reads exactly:

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

  (Because it has a default and is last, every existing positional or
  keyword instantiation of the original 8 fields remains valid —
  fully backward-compatible.)

- [ ] **Step 8:** Read `src/robin/context_pack.py`, then replace the final
  `return ContextPack(**{k: raw[k] for k in _FIELDS})` line at the end of
  `load_context_pack` with the additive optional-`email` extraction
  (do NOT modify `_FIELDS` — adding `email` there would make it required
  and break existing packs):

```python
return ContextPack(
    **{k: raw[k] for k in _FIELDS},
    email=raw.get("email", ""),          # W2: optional, default ""
)
```

- [ ] **Step 9:** Run the four tests and confirm GREEN:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_context_pack_accepts_email tests/test_agentmail.py::test_context_pack_email_defaults_to_empty tests/test_agentmail.py::test_load_context_pack_passes_email tests/test_agentmail.py::test_load_context_pack_email_absent_defaults_empty
```

  Expected: all four PASS.

- [ ] **Step 10:** Run the full suite to confirm the additive field/loader
  change did not regress any existing test:

```bash
docker compose run --rm robin pytest -q
```

  Expected: full suite GREEN.

- [ ] **Step 11:** Commit:

```bash
git add src/robin/models.py src/robin/context_pack.py tests/test_agentmail.py
git commit -m "feat: W2 ContextPack.email optional field + context_pack loader extraction"
```

---

### Task 9: `main.py` W2 wiring sub-block + append-only config files

Insert ONLY the W2 sub-block between the W2 and W3 markers in `main.py`,
and append the W2 blocks to `.env.example` and `requirements.txt`.
(Spec §5.2, §8.)

- [ ] **Step 1:** Read `src/robin/main.py` and locate the W0 seam markers:

```python
# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
# >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
# >>> W4 dashboard wiring   <<<   (added on feat/dashboard-flagship)
# --- end sponsor extension wiring ---
```

- [ ] **Step 2:** Insert ONLY the W2 sub-block between the
  `# >>> W2 agentmail wiring   <<<` line and the
  `# >>> W3 moss wiring        <<<` line — touch no other line in
  `main.py`:

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

  (This rebuilds `_hooks` immutably, appending only the `on_outcome` hook;
  all other slots pass through unchanged. The `_os` alias avoids shadowing
  the top-level `os` import. `_pack` is the already-constructed
  `ContextPack` at the composition root.)

- [ ] **Step 3:** Read `.env.example`, then append the W2 block at the end
  (after the existing `--- Optional sponsor hooks ---` section if W1 has
  already extended it; otherwise simply at end of file):

```
# --- W2: Agent Mail close-loop (bonus track) ---
# Set to "1" to enable; absent = no-op (default).
ROBIN_AGENTMAIL_ENABLED=
AGENTMAIL_API_KEY=
# Optional: presenter email for the caller confirmation email.
# Add "email": "you@example.com" to context_pack.json (gitignored).
# NEVER put a real email address in this file.
```

- [ ] **Step 4:** Read `requirements.txt`, then append the W2 dependency
  line at the end:

```
# W2: AgentMail close-loop
agentmail>=0.5.0
```

- [ ] **Step 5:** Rebuild the container so the new `agentmail` dependency
  is installed (requirements changed):

```bash
docker compose build robin
```

  Expected: build succeeds; `agentmail>=0.5.0` resolves and installs.

- [ ] **Step 6:** Run the full suite and ruff with the wiring + dependency
  in place:

```bash
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

  Expected: full suite GREEN (flag absent in the test env ⇒ the W2
  sub-block is inert); ruff clean.

- [ ] **Step 7:** Commit:

```bash
git add src/robin/main.py .env.example requirements.txt
git commit -m "feat: W2 wire agentmail on_outcome hook in main.py + env/deps appends"
```

---

### Task 10: Flag-off regression gate + REFACTOR pass (final merge gate)

Add the flag-off regression test (no tasks spawned with the flag absent),
run the REFACTOR/coverage checks, then run the full pre-merge gate.
(Spec Milestone 7, §6 REFACTOR, §11.)

- [ ] **Step 1:** Replace the `test_flag_off_regression_no_side_effects`
  stub with the full test:

```python
async def test_flag_off_regression_no_side_effects(monkeypatch):
    """With flag absent, the hook is a pure no-op: no tasks, no logs from W2."""
    monkeypatch.delenv("ROBIN_AGENTMAIL_ENABLED", raising=False)
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)

    import robin.integrations.agentmail as am_mod

    hook = am_mod.make_email_outcome_hook(_pack("test@example.com"))
    tasks_before = set(asyncio.all_tasks())
    await hook(call_id="call-flag", payload=_DONE_PAYLOAD)
    tasks_after = set(asyncio.all_tasks())

    assert tasks_before == tasks_after, "flag-off hook spawned tasks"
```

- [ ] **Step 2:** Run the flag-off regression test and confirm GREEN:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py::test_flag_off_regression_no_side_effects
```

  Expected: PASS (no tasks spawned when the flag is absent).

- [ ] **Step 3:** REFACTOR review (no behavior change — verify only):
  - `_FALLBACK_CONFIRMATION` is a named constant (not duplicated as a
    literal between `agentmail.py` and tests).
  - `_GYM_DEMO_EMAIL` uses the `.invalid` TLD (RFC 2606 — unreachable by
    design; safe to commit as a string literal; never a real address).
  - `obs.log_event` calls never pass `to=` / `email=` / `subject=` /
    `body=` field names — only `confirmation=` and `has_email=bool(...)`
    (a boolean, not the address) appear, so no email address or body text
    is logged.

- [ ] **Step 4:** Run coverage on the new integration module and confirm
  ≥ 80%:

```bash
docker compose run --rm robin pytest -q --cov=src/robin/integrations --cov-report=term-missing
```

  Expected: `src/robin/integrations/agentmail.py` coverage ≥ 80%.

- [ ] **Step 5:** Run the full pre-merge gate:

```bash
docker compose run --rm robin pytest -q tests/test_agentmail.py
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

  Expected: W2 suite GREEN; full suite GREEN; ruff clean. This is the
  merge gate — if any command is not green, do NOT proceed to merge.

- [ ] **Step 6:** Run the review agents on the diff and address findings:
  - `security-reviewer` on the W2 diff — confirm no CRITICAL/HIGH (no
    secret literal; `AGENTMAIL_API_KEY` from env only; no real PII; no
    email address logged; AgentMail Svix webhooks NOT wired to Robin's
    endpoint — out of scope).
  - `code-reviewer` on the W2 diff — address MEDIUM+ issues.

- [ ] **Step 7:** Commit the regression test (final W2 commit):

```bash
git add tests/test_agentmail.py
git commit -m "test: W2 flag-off regression gate — no side-effects when flag absent"
```

- [ ] **Step 8:** Stage the complete W2 changeset for the human's merge
  (do NOT `git push`; the human performs the merge/push/submission):

```bash
git add src/robin/integrations/__init__.py
git add src/robin/integrations/agentmail.py
git add src/robin/models.py
git add src/robin/context_pack.py
git add tests/test_agentmail.py
git add tests/fakes.py
git add src/robin/main.py   # only the W2 sub-block changed
git add .env.example
git add requirements.txt
git status   # confirm: ONLY the files above are staged; no .env / *.local.json / PII
```

  Then STOP. The human performs:
  `git checkout main && git merge feat/agentmail-closeloop`.

**Pre-merge checklist (verify every box before handing off):**

- [ ] `docker compose run --rm robin pytest -q` — full suite GREEN
- [ ] `docker compose run --rm robin pytest -q tests/test_agentmail.py` — W2 suite GREEN
- [ ] Coverage ≥ 80% on `src/robin/integrations/agentmail.py`
- [ ] `docker compose run --rm robin ruff check src tests` — clean
- [ ] Flag-off regression test passes
- [ ] No real email addresses, API keys, or PII in any committed file
  (tests use `test@example.com`; gym address is `*.invalid`)
- [ ] No `.env` / `*.local.json` staged
- [ ] `models.py` change: one optional field appended, default `""`, non-breaking
- [ ] `context_pack.py` change: one optional extraction line, additive
- [ ] `main.py` edit: W2 sub-block only, between the W2/W3 markers
- [ ] `security-reviewer` + `code-reviewer` run; CRITICAL/HIGH fixed

**Auto-merge compatibility (informational):** the only shared-file edits
are `main.py` (distinct W2 sub-block), `models.py` (one appended field),
`context_pack.py` (one amended return line), `tests/fakes.py` (appended
block), and `.env.example` / `requirements.txt` (appended). W1/W3/W4 do
not touch `models.py` or `context_pack.py`; git auto-merges all of these
cleanly with no manual conflict resolution. W2 does NOT require W1 — it
reads only the `ContextPack.email` field and never imports
`integrations/supermemory.py`.

> **Collapse ladder (note — only if behind at ~T+1:30):**
> 1. **Minimum viable (cut complaint draft):** in `_send_emails`, remove
>    the `_GYM_DEMO_EMAIL` send (the second
>    `await client.inboxes.messages.send(...)` block and its
>    `agentmail_complaint_drafted` log) so only the caller confirmation
>    email is sent. Update the affected success-path assertions
>    accordingly. Still valid — the complaint draft is the cut.
> 2. **Further cut (skip W2 entirely):** do NOT merge this branch. The
>    flag-off design means an unmerged W2 costs the canonical demo
>    nothing; proceed directly to W4 (higher-value judging story,
>    depends only on W0). A half-done branch is never merged — the
>    flag-off regression test is the final merge gate.

---

**File:** `/Users/francescorosciano/docs/robin/docs/superpowers/plans/2026-05-17-w2-agentmail-closeloop.md`

**3-line summary:** 10 tasks convert the spec's Milestones 0–7 plus the
models.py/context_pack.py edits and main.py/config wiring into bite-sized
TDD steps (RED test → exact Docker command → full implementation copied
verbatim from the spec → GREEN command → conventional commit). Every spec
milestone maps to a task: M0→Task 1 (scaffold), the `FakeAgentMailClient`
append→Task 2, M1→Task 3 (`_is_enabled` + full module), M2→Task 4
(success path), M3→Task 5 (skip/non-DONE), M4→Task 6 (error resilience),
M5→Task 7 (inbox-once), M6→Task 8 (models.py field + context_pack.py
loader), W2 wiring (§5.2/§8)→Task 9 (main.py sub-block + .env.example +
requirements.txt), and M7→Task 10 (flag-off regression gate + REFACTOR +
pre-merge gate + merge handoff, with the collapse ladder kept as a note).
