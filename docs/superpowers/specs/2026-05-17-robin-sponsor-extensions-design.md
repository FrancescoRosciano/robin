# Robin Sponsor-Extension Portfolio — Design

**Date:** 2026-05-17 · **Status:** approved (W0-seam-first) · **Horizon:** pre-8PM additive sprint
**Sponsors layered:** Super Memory, Agent Mail, Moss · **Flagship:** live judge-facing dashboard

This is the master design. Each workstream has its own self-contained
spec+plan file (see the index below); each is implementable end-to-end by
one agent on one isolated branch from only that file + the working tree,
then merged. This document defines the **shared contract** every
workstream obeys and the **W0 seam** that makes the four feature branches
merge conflict-free.

---

## 1. Purpose & non-negotiable constraint

Robin's canonical demo (call → discovery → Browser Use legal research →
outbound call to a simulated gym receptionist → escalating negotiation →
two-option ultimatum → capitulation + last-month refund + `24HF-4471` →
report back; recorded in the dashboard) **already works** and is the
submitted artifact. These extensions add sponsor prize-track value and
"wow" **without ever putting that demo at risk**.

**Hard rule:** with every new feature flag absent (the default), the
canonical gym-cancel path is **byte-identical** to `main` today. The
live demo and the recorded backup video always run from `main`.

## 2. The isolation contract (every workstream obeys this)

1. **Flag-off ⇒ no-op, byte-identical.** Each feature is gated by a
   `ROBIN_*_ENABLED` env var, absent by default, read at the composition
   root (`src/robin/main.py`) following the existing
   `ROBIN_SKIP_WEBHOOK_VERIFY` / `CONTEXT_PACK_PATH` pattern. **Never add
   a flag or optional key to `config.py:_REQUIRED` or the `Settings`
   dataclass** — that breaks startup for everyone not running the
   feature. Optional keys go in a separate, flag-guarded check.
2. **Graceful no-op on any failure.** Missing key, missing SDK, timeout,
   or any exception ⇒ behave exactly as today, emit one
   `obs.log_event(...)` correlation breadcrumb, never raise into the call
   turn. Confirmed SDKs: `supermemory`, `agentmail`, `moss` (all PyPI,
   all async-capable).
3. **New code in new files.** Each workstream adds
   `src/robin/integrations/<name>.py` (W4: `src/robin/event_bus.py`)
   plus its own `tests/test_<name>.py` and a `Fake<Name>Client` appended
   to `tests/fakes.py`. No workstream edits canonical-path internals
   (`classifier.py`, `signature.py`, the locked
   `fixtures/prompts/*.txt`, `fixtures/law.html`, `models.py` core
   shapes — W2's optional `email` field is the one allowed, additive
   exception).
4. **Constructor injection + fake**, matching the existing
   `FakeBrowser` / `FakeLLM` / `FakeAgentPhoneClient` pattern. TDD:
   RED → GREEN → REFACTOR, ≥80 % coverage on new code.
5. **Hard time-box + collapse rule** in every plan. A half-done branch
   is never merged. Each plan ends with an explicit "if behind at T, cut
   to here" ladder and a flag-off regression test as the final gate.
6. **Security:** secrets only from env (gitignored `.env`), validated in
   the feature's flag-guarded block, never logged, never in tests
   (synthetic `+1555…` / `test@example.com` only). No real PII or
   transcripts committed. Webhook stays Svix-verified — no workstream
   touches `signature.py`.

## 3. W0 — the shared extension seam (lands on `main` first)

**Problem W0 solves:** W1, W2, W4 all want to react to the same two
moments (`loop.py:_record_session` after an outcome; the system-prompt
assembly in `run_turn`). If each branch edits those lines, the branches
collide there. W0 converts those edits into **injected callback lists**
so the features become purely additive.

### 3.1 New file: `src/robin/extensions.py`

```python
"""Extension seam: inert injected hooks. Empty == today's behavior."""
from dataclasses import dataclass
from typing import Awaitable, Callable

# call_id -> extra system-prompt text ("" = contribute nothing)
PromptEnricher = Callable[[str | None], Awaitable[str]]
# (call_id, payload) -> None ; best-effort, must return fast, must not raise
ResearchHook = Callable[[str | None, dict], Awaitable[None]]
OutcomeHook = Callable[[str | None, dict], Awaitable[None]]


@dataclass(frozen=True)
class ExtensionHooks:
    prompt_enrichers: tuple[PromptEnricher, ...] = ()
    on_research: tuple[ResearchHook, ...] = ()
    on_outcome: tuple[OutcomeHook, ...] = ()
    event_bus: object | None = None  # opaque; W4 supplies; None == inert
```

`ExtensionHooks()` (all empty) is the default everywhere ⇒ zero
behavior change when no feature is enabled.

### 3.2 Exact edits W0 makes (these are the ONLY edits to these files in the whole portfolio)

- **`src/robin/loop.py`**
  - `_record_session` becomes `async def`, gains a final
    `hooks: ExtensionHooks` parameter. After its existing
    `session.*` calls it dispatches, best-effort, each
    `hooks.on_research` (when `name == "research_cancellation_law"` and
    `out["status"] == "OK"`, payload = the full `out` dict) and each
    `hooks.on_outcome` (when `name == "deliver_result"` and
    `out["delivered"]`, payload =
    `{"summary": str(tool_input.get("summary","")),
    "confirmation": tool_input.get("confirmation"),
    "channel": tool_input.get("channel"), "out": out}`). Each hook is
    wrapped in try/except → `obs.log_event("extension_hook_error", …)`;
    one bad hook never kills the turn. Call site (loop.py:140) becomes
    `await _record_session(call_id, name, tool_input, out, hooks)`.
  - `run_turn` gains `hooks: ExtensionHooks = ExtensionHooks()`
    (keyword, default empty). After `effective_system` is built
    (loop.py:105–106), each `hooks.prompt_enrichers` is awaited
    (best-effort, same try/except) and any non-empty return is appended:
    `effective_system = effective_system + "\n\n" + "\n\n".join(extra)`.
    Enricher ordering = registration order (deterministic for tests).
  - **Contract for hook authors:** a hook must return quickly
    (< ~200 ms) and must not raise. Long work (network persist, email
    send) must be self-scheduled inside the hook via
    `asyncio.create_task(...)` and the hook returns immediately.
- **`src/robin/app.py`**
  - `build_app(...)` gains `hooks: ExtensionHooks = ExtensionHooks()`;
    threads it into the `run_turn(...)` call in the webhook route.
  - `make_stage_router(...)` is **parametrized** (behavior identical on
    defaults): optional `event_bus=None` (when provided, its
    `subscribe()/unsubscribe(q)` queue of `{"event": str, "data": dict}`
    items is drained into the same SSE response alongside `turn`
    events) and an optional stage-HTML source (default = current
    `_STAGE_HTML`; lets a richer projector page be supplied purely from
    the composition root). W0 must read `app.py` first and keep the
    no-arg behavior exactly as today (tests pin this).
- **`src/robin/main.py`**
  - Adds a clearly-delimited section, empty by default:
    ```python
    # --- sponsor extension wiring (one delimited sub-block per branch) ---
    _hooks = ExtensionHooks()
    # >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
    # >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
    # >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
    # >>> W4 dashboard wiring   <<<   (added on feat/dashboard-flagship)
    # --- end sponsor extension wiring ---
    ```
    and passes `hooks=_hooks` to `build_app(...)`. Each feature branch
    inserts **only its own** `>>> Wn … <<<` sub-block (rebuilding
    `_hooks` immutably with its callback appended) and, if it needs a
    stage page or event bus, passes those to `build_app`. Distinct
    insertion points ⇒ git auto-merges; the labeled markers guarantee
    no two branches touch the same lines.

### 3.3 W0 tests (`tests/test_extensions.py`)

Empty hooks ⇒ `run_turn` / `_record_session` outputs identical to a
captured pre-W0 baseline; enrichers append in registration order;
`on_research`/`on_outcome` fire with the exact payload shapes above; a
raising hook is swallowed + logged and the turn still completes;
`make_stage_router` with no `event_bus` and default HTML is byte-identical
to today (existing `test_stage.py` stays green unchanged).

W0 is itself flag-free and inert — it ships dormant capability only.
Size: **S, ~0.5–0.75 h.**

## 4. The four feature workstreams

Each is purely additive **on top of W0**: a new integration file +
register callback(s) + one delimited `main.py` sub-block + one flag +
tests + a `Fake*` + append-only lines in `.env.example` /
`requirements.txt`. None edits `loop.py`, `stage.py`, or `app.py`.

### W1 — `feat/supermemory-recall`  (Super Memory)
Robin remembers callers across calls. New
`src/robin/integrations/supermemory.py`: `AsyncSupermemory`
(`SUPERMEMORY_API_KEY`), `container_tag` = caller E.164 with `+`→`p`,
800 ms read timeout, `max_retries=0`, fire-and-forget write. Registers a
**prompt_enricher** (fetch prior outcomes/tactics → a `[CALLER HISTORY]`
block) and an **on_outcome** hook (persist outcome+winning tactic via
`asyncio.create_task`). Flag `ROBIN_MEMORY_ENABLED`. Demo moment: a
second call opens "Welcome back — last time we cancelled your 24 Hour
Gym membership; what's next?" No-op: no key ⇒ no enrichment, no error.
Size **M ~2 h**. Touches: new file, `main.py` W1 sub-block,
`.env.example`, `requirements.txt`, tests, `fakes.py`.

### W2 — `feat/agentmail-closeloop`  (Agent Mail)
Robin closes the loop in writing. New
`src/robin/integrations/agentmail.py`: `AsyncAgentMail`
(`AGENTMAIL_API_KEY`), ensure-inbox-once, `messages.send`, 5–10 s
timeout, fire-and-forget via `asyncio.create_task`. Registers an
**on_outcome** hook: on DONE send the caller a confirmation
(cancellation + last-month refund + `24HF-4471`) and a drafted
regulator/"certified-letter" complaint to a synthetic gym address.
`models.py` gains one **optional** `email: str = ""` field on
`ContextPack` (additive, defaulted; canonical path unaffected; the
gitignored `context_pack.json` may carry it). W2 does **not** edit the
locked discovery prompt — it reads `pack.email`, else a W1 lookup if
present, else skips. Flag `ROBIN_AGENTMAIL_ENABLED`. Demo moment: the
real confirmation email visibly arrives; the complaint draft is shown.
Size **M ~2 h**. Touches: new file, `models.py` (one optional `email`
field), `context_pack.py` (one additive line so the loader passes an
optional `email` through), `main.py` W2 sub-block, `.env.example`,
`requirements.txt`, tests, `fakes.py`.

### W3 — `feat/moss-statute-search`  (Moss)
Instant (<10 ms) semantic lookup over the **pre-verified** statute
corpus. New `scripts/setup_moss_statutes.py` (one-off, indexes **only**
the three locked statutes sourced verbatim from
`docs/legal-citations-verified.md` — never web text) + new
`src/robin/integrations/moss_search.py` (`MossClient`,
`MOSS_PROJECT_ID`/`MOSS_PROJECT_KEY`, lazy module-level
load-index-once under an `asyncio.Lock`, `query` at call time, fallback
to the existing static fixture on any miss/error). W3's `main.py`
sub-block overrides `_tool_impls["research_cancellation_law"]` with the
Moss-backed research closure **only when** `MOSS_PROJECT_ID` is set —
otherwise the current Browser Use `_research` is untouched. The Moss
cookbook is literally Robin's structural reference; integrity bright
line preserved (corpus-only). Flag = presence of Moss creds. No app.py
edit (lazy load, not lifespan). Size **M ~2 h**. Track: up to $10K.
Touches: 2 new files, `main.py` W3 sub-block, `.env.example`,
`requirements.txt`, tests, `fakes.py`.

### W4 — `feat/dashboard-flagship`  (the flagship; depends on W0 only)
Live judge-facing dashboard: one projector page where the transcript,
the Moss citation, the Super Memory recall, and the Agent Mail artifact
fill in **in real time** as the negotiation runs — all three sponsors
legible in one screen. New `src/robin/event_bus.py` (an `EventBus`
duck-typed to W0's `subscribe()/unsubscribe()/{"event","data"}`
contract) + `src/robin/fixtures/stage_dashboard.html` (self-contained,
preserves the disclosure banner verbatim, four panels, degrades each
panel to a designed placeholder if its sponsor SDK is absent).
Registers **on_research** + **on_outcome** hooks that publish to its
bus. W4's `main.py` sub-block (under `ROBIN_DASHBOARD_ENHANCED`)
constructs the `EventBus`, puts it on `ExtensionHooks(event_bus=…)`, and
passes the dashboard HTML to the W0-parametrized stage router. No edits
to `loop.py`/`stage.py`/`app.py` (W0 already parametrized them).
Size **M ~3 h**. Touches: 2 new files, `main.py` W4 sub-block, tests.

## 5. Merge model & independence

```
main ──● W0 (extension-seam)  ← lands first, inert, fully tested
        ├── W3 feat/moss-statute-search   ┐
        ├── W4 feat/dashboard-flagship    │  cut from post-W0 main,
        ├── W1 feat/supermemory-recall    │  mutually conflict-free,
        └── W2 feat/agentmail-closeloop   ┘  merge in ANY order
```

After W0 is on `main`, the only file multiple feature branches touch is
`main.py`, and only via **distinct labeled `>>> Wn <<<` sub-blocks** →
git auto-merges; `.env.example` / `requirements.txt` / `tests/fakes.py`
are append-only with per-branch labeled blocks. Everything else is
disjoint new files. **Independence matrix:**

| Branch | New files | Shared-file edits | Conflicts with |
|---|---|---|---|
| W0 | `extensions.py` (+test) | `loop.py`, `app.py`, `main.py` (seam) | — (lands first) |
| W1 | `integrations/supermemory.py` (+test, fake) | `main.py` W1 block only | none |
| W2 | `integrations/agentmail.py` (+test, fake) | `main.py` W2 block, `models.py` +1 optional field, `context_pack.py` +1 additive line (loader extracts optional `email`) | none |
| W3 | `integrations/moss_search.py`, `scripts/setup_moss_statutes.py` (+test, fake) | `main.py` W3 block only | none |
| W4 | `event_bus.py`, `fixtures/stage_dashboard.html` (+tests) | `main.py` W4 block only | none |

## 6. Deadline-collapse priority

If the clock runs out, build/merge in this order; stop anywhere — every
prefix is shippable and the canonical demo is never touched:

**W0 → W3 → W4 → W1 → W2.**
Rationale: W0 unblocks all. W3 = the $10K track and the cookbook is the
reference. W4 = the judging story and reuses the most existing infra.
W1/W2 are clean but each depends on a key that may not arrive; their
no-op design means an unmerged or key-less branch costs nothing.

## 7. Spec + plan index (each self-contained, one branch each)

- `2026-05-17-w0-extension-seam.md`
- `2026-05-17-w1-supermemory-recall.md`
- `2026-05-17-w2-agentmail-closeloop.md`
- `2026-05-17-w3-moss-statute-search.md`
- `2026-05-17-w4-dashboard-flagship.md`

## 8. Acceptance (whole portfolio)

- Each branch: its `pytest` green, ≥80 % on new code, `ruff` clean, and
  a **flag-off regression test** proving the canonical path unchanged.
- `git merge` of W1–W4 (post-W0) requires no manual conflict resolution
  beyond the documented `main.py` labeled blocks.
- With all flags off, the full existing suite is green and the gym-cancel
  demo is byte-identical to pre-portfolio `main`.
- Secrets/PII clean; no `.env` / recordings / real numbers staged.
