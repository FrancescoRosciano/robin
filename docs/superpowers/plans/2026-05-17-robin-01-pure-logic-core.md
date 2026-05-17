# Robin Plan 01 — Pure Logic Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the telephony-independent core — context pack loader
(+guard), prompt renderer (+slot guard), and outcome classifier — fully
unit-tested at ≥80% coverage, with zero network/telephony.

**Architecture:** Pure functions + frozen dataclasses in `src/robin/`.
No I/O except reading a local JSON pack and local template files. This
package is imported by Plans 03 (server) and 04 (outbound); its
interfaces are frozen in `docs/superpowers/plans/2026-05-17-robin-00-execution-sequence.md`
and **must not drift**.

**Tech Stack:** Python 3.11+, `pytest`, `pytest-cov`, `ruff`. No
third-party runtime deps in this plan.

**Ownership note:** This plan **owns and commits first**:
`pyproject.toml` (initial), `src/robin/__init__.py`, `src/robin/models.py`.
Plan 03 appends FastAPI deps later — never edited concurrently.

---

## File Structure

- Create `pyproject.toml` — project metadata, pytest+ruff config, `src` layout.
- Create `src/robin/__init__.py` — empty package marker.
- Create `src/robin/models.py` — `ContextPack`, `Citation`, `OutcomeStatus`, `Outcome` (verbatim from the 00 contract).
- Create `src/robin/context_pack.py` — `load_context_pack`, `ContextPackError`.
- Create `src/robin/prompts.py` — `render`, `render_inbound_system_prompt`, `render_outbound_system_prompt`, `PromptRenderError`.
- Create `src/robin/classifier.py` — `classify_transcript`.
- Create `tests/__init__.py`, `tests/test_models.py`, `tests/test_context_pack.py`, `tests/test_prompts.py`, `tests/test_classifier.py`.
- Create `tests/fixtures/context_pack.valid.json`, `tests/fixtures/context_pack.unfilled.json`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/robin/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 0: Initialize the git repository (if not already one)**

Run: `cd /Users/francescorosciano/docs/robin && (git rev-parse --git-dir >/dev/null 2>&1 || git init)`
Expected: either nothing / silent exit 0 (already a repo) or
`Initialized empty Git repository in /Users/francescorosciano/docs/robin/.git/`.

Note: a hardened `.gitignore` already exists from the project launchpad —
do not overwrite it. This one-time bootstrap is what makes every later
`git add/commit` step across all plans work.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "robin"
version = "0.1.0"
description = "Robin — voice chief-of-staff (AgentPhone + Browser Use)"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-q --cov=robin --cov-report=term-missing"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Create empty package markers**

Create `src/robin/__init__.py` with a single line:

```python
"""Robin core package."""
```

Create `tests/__init__.py` empty (zero bytes).

- [ ] **Step 3: Install dev tooling and verify pytest runs**

Run: `cd /Users/francescorosciano/docs/robin && python3 -m pip install -q pytest pytest-cov ruff && python3 -m pytest -q`
Expected: pytest collects 0 items, exits 0 (`no tests ran`).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/robin/__init__.py tests/__init__.py
git commit -m "chore: project scaffold (pyproject, package markers)"
```

---

### Task 2: Models (frozen contract)

**Files:**
- Create: `src/robin/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
import dataclasses
import pytest
from robin.models import ContextPack, Citation, Outcome, OutcomeStatus


def test_contextpack_is_frozen():
    p = ContextPack(
        caller_name="Demo User", callback_number="+15550000001",
        target_name="24 Hour Gym", target_display_number="415-776-2200",
        receptionist_to_number="+15550000002", jurisdiction="US-CA",
        win_goal="cancel + refund", fallback_goal="cancel only",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.caller_name = "x"


def test_outcome_status_values():
    assert OutcomeStatus.DONE == "DONE"
    assert {s.value for s in OutcomeStatus} == {"DONE", "NEEDS_APPROVAL", "BLOCKED"}


def test_outcome_and_citation_construct():
    c = Citation(citation="X", operative_quote="q", source_url="http://h/")
    o = Outcome(status=OutcomeStatus.DONE, confirmation="24HF-4471", detail="ok")
    assert c.citation == "X" and o.confirmation == "24HF-4471"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.models'`.

- [ ] **Step 3: Write `src/robin/models.py`**

Copy the `models.py` block **verbatim** from
`docs/superpowers/plans/2026-05-17-robin-00-execution-sequence.md`
(section "`src/robin/models.py`"). Do not rename a field or change a type.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_models.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/models.py tests/test_models.py
git commit -m "feat: frozen core models (ContextPack, Citation, Outcome)"
```

---

### Task 3: Context pack loader + guard

**Files:**
- Create: `src/robin/context_pack.py`
- Test: `tests/test_context_pack.py`
- Create: `tests/fixtures/context_pack.valid.json`
- Create: `tests/fixtures/context_pack.unfilled.json`

- [ ] **Step 1: Write fixtures**

`tests/fixtures/context_pack.valid.json`:

```json
{
  "caller_name": "Demo User",
  "callback_number": "+15550000001",
  "target_name": "24 Hour Gym",
  "target_display_number": "415-776-2200",
  "receptionist_to_number": "+15550000002",
  "jurisdiction": "US-CA",
  "win_goal": "Cancel the membership and obtain a last-month refund.",
  "fallback_goal": "Cancel the membership; refund optional."
}
```

`tests/fixtures/context_pack.unfilled.json` (same but one slot left
templated):

```json
{
  "caller_name": "{{caller_name}}",
  "callback_number": "+15550000001",
  "target_name": "24 Hour Gym",
  "target_display_number": "415-776-2200",
  "receptionist_to_number": "+15550000002",
  "jurisdiction": "US-CA",
  "win_goal": "Cancel the membership and obtain a last-month refund.",
  "fallback_goal": "Cancel the membership; refund optional."
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_context_pack.py
import json
import pytest
from robin.context_pack import load_context_pack, ContextPackError

VALID = "tests/fixtures/context_pack.valid.json"
UNFILLED = "tests/fixtures/context_pack.unfilled.json"


def test_loads_valid_pack():
    p = load_context_pack(VALID)
    assert p.caller_name == "Demo User"
    assert p.receptionist_to_number == "+15550000002"


def test_missing_file_raises():
    with pytest.raises(ContextPackError, match="not found"):
        load_context_pack("tests/fixtures/nope.json")


def test_unfilled_placeholder_raises():
    with pytest.raises(ContextPackError, match="unfilled placeholder in caller_name"):
        load_context_pack(UNFILLED)


def test_empty_field_raises(tmp_path):
    d = json.load(open(VALID))
    d["win_goal"] = ""
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="empty field: win_goal"):
        load_context_pack(str(f))


def test_bad_e164_raises(tmp_path):
    d = json.load(open(VALID))
    d["callback_number"] = "555-0001"
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="callback_number"):
        load_context_pack(str(f))


def test_missing_key_raises(tmp_path):
    d = json.load(open(VALID))
    del d["jurisdiction"]
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ContextPackError, match="missing field: jurisdiction"):
        load_context_pack(str(f))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_context_pack.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.context_pack'`.

- [ ] **Step 4: Write `src/robin/context_pack.py`**

```python
"""Load and validate the local context pack. Fail fast — never on stage."""
import json
import re
from robin.models import ContextPack

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_PHONE_FIELDS = ("callback_number", "receptionist_to_number")
_FIELDS = (
    "caller_name", "callback_number", "target_name", "target_display_number",
    "receptionist_to_number", "jurisdiction", "win_goal", "fallback_goal",
)


class ContextPackError(ValueError):
    """Raised on a missing/malformed/placeholder-bearing context pack."""


def load_context_pack(path: str) -> ContextPack:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError as e:
        raise ContextPackError(f"context pack not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ContextPackError(f"context pack is not valid JSON: {path}") from e

    for key in _FIELDS:
        if key not in raw:
            raise ContextPackError(f"missing field: {key}")
        val = raw[key]
        if not isinstance(val, str):
            raise ContextPackError(f"field must be a string: {key}")
        if val == "":
            raise ContextPackError(f"empty field: {key}")
        if "{{" in val or "}}" in val:
            raise ContextPackError(f"unfilled placeholder in {key}")

    for key in _PHONE_FIELDS:
        if not _E164.match(raw[key]):
            raise ContextPackError(
                f"{key} must be E.164 (e.g. +15550000001), got: {raw[key]!r}"
            )

    return ContextPack(**{k: raw[k] for k in _FIELDS})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_context_pack.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add src/robin/context_pack.py tests/test_context_pack.py tests/fixtures/context_pack.valid.json tests/fixtures/context_pack.unfilled.json
git commit -m "feat: context pack loader with fail-fast guard"
```

---

### Task 4: Prompt renderer + slot guard

**Files:**
- Create: `src/robin/prompts.py`
- Test: `tests/test_prompts.py`

> Real prompt templates are Plan 02's content. This task tests the pure
> `render()` + guard with **inline** templates so Plan 01 stays
> independent of Plan 02. The file-backed wrappers are smoke-checked in
> Plan 03 once Plan 02's templates exist.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompts.py
import pytest
from robin.models import ContextPack, Citation
from robin.prompts import render, PromptRenderError

PACK = ContextPack(
    caller_name="Demo User", callback_number="+15550000001",
    target_name="24 Hour Gym", target_display_number="415-776-2200",
    receptionist_to_number="+15550000002", jurisdiction="US-CA",
    win_goal="Cancel + last-month refund.", fallback_goal="Cancel only.",
)
CITES = [
    Citation(citation="FTC Rule", operative_quote="Cancellation must be simple.",
             source_url="http://h/law.html"),
    Citation(citation="CA Law", operative_quote="You may cancel.",
             source_url="http://h/law.html"),
]


def test_render_substitutes_all_pack_slots():
    tpl = ("Caller {{caller_name}} target {{target_name}} num "
           "{{target_display_number}} cb {{callback_number}} "
           "juris {{jurisdiction}} win {{win_goal}} fb {{fallback_goal}}")
    out = render(tpl, PACK)
    assert "Demo User" in out and "24 Hour Gym" in out
    assert "{{" not in out


def test_render_citations_block():
    out = render("Laws:\n{{citations}}", PACK, CITES)
    assert "FTC Rule" in out and "You may cancel." in out
    assert "{{citations}}" not in out


def test_unfilled_slot_raises():
    with pytest.raises(PromptRenderError, match=r"unfilled slot: \{\{mystery\}\}"):
        render("hello {{mystery}}", PACK)


def test_citations_slot_without_citations_raises():
    with pytest.raises(PromptRenderError, match=r"unfilled slot: \{\{citations\}\}"):
        render("Laws:\n{{citations}}", PACK, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_prompts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.prompts'`.

- [ ] **Step 3: Write `src/robin/prompts.py`**

```python
"""Render system prompts from a ContextPack. No unfilled slot ever ships."""
import re
from robin.models import Citation, ContextPack

INBOUND_TEMPLATE_PATH = "src/robin/fixtures/prompts/inbound_discovery.txt"
OUTBOUND_TEMPLATE_PATH = "src/robin/fixtures/prompts/outbound_negotiation.txt"

_SLOT = re.compile(r"\{\{.*?\}\}")


class PromptRenderError(ValueError):
    """Raised when a template still has an unfilled {{slot}} after render."""


def _citations_block(citations: list[Citation]) -> str:
    lines = []
    for i, c in enumerate(citations, 1):
        lines.append(f"{i}. {c.citation} — \"{c.operative_quote}\" ({c.source_url})")
    return "\n".join(lines)


def render(template: str, pack: ContextPack,
           citations: list[Citation] | None = None) -> str:
    out = template
    mapping = {
        "caller_name": pack.caller_name,
        "callback_number": pack.callback_number,
        "target_name": pack.target_name,
        "target_display_number": pack.target_display_number,
        "jurisdiction": pack.jurisdiction,
        "win_goal": pack.win_goal,
        "fallback_goal": pack.fallback_goal,
    }
    for key, val in mapping.items():
        out = out.replace("{{" + key + "}}", val)
    if citations:
        out = out.replace("{{citations}}", _citations_block(citations))
    leftover = _SLOT.search(out)
    if leftover:
        raise PromptRenderError(f"unfilled slot: {leftover.group(0)}")
    return out


def _render_from_path(path: str, pack: ContextPack,
                      citations: list[Citation] | None = None) -> str:
    with open(path, encoding="utf-8") as fh:
        return render(fh.read(), pack, citations)


def render_inbound_system_prompt(pack: ContextPack) -> str:
    return _render_from_path(INBOUND_TEMPLATE_PATH, pack)


def render_outbound_system_prompt(pack: ContextPack,
                                  citations: list[Citation]) -> str:
    return _render_from_path(OUTBOUND_TEMPLATE_PATH, pack, citations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_prompts.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/prompts.py tests/test_prompts.py
git commit -m "feat: prompt renderer with unfilled-slot guard"
```

---

### Task 5: Outcome classifier

**Files:**
- Create: `src/robin/classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classifier.py
from robin.classifier import classify_transcript
from robin.models import OutcomeStatus

DONE_TX = ("agent: Fine — I'll cancel your subscription and refund your "
           "last month. Your confirmation number is 24HF-4471.")
OTP_TX = ("agent: To proceed I need to verify your identity — I'll text "
          "you a code now.")
BLOCKED_TX = ("agent: You can only cancel in person at your home club. "
              "I cannot help further.")


def test_done_requires_confirmation_and_refund():
    o = classify_transcript(DONE_TX)
    assert o.status == OutcomeStatus.DONE
    assert o.confirmation == "24HF-4471"


def test_confirmation_without_refund_is_not_done():
    o = classify_transcript("agent: Cancelled. Confirmation 24HF-4471.")
    assert o.status == OutcomeStatus.BLOCKED


def test_needs_approval_on_otp_gate():
    o = classify_transcript(OTP_TX)
    assert o.status == OutcomeStatus.NEEDS_APPROVAL
    assert "verify your identity" in o.detail or "text you a code" in o.detail


def test_blocked_default_with_last_line_detail():
    o = classify_transcript(BLOCKED_TX)
    assert o.status == OutcomeStatus.BLOCKED
    assert "cannot help further" in o.detail


def test_done_wins_even_if_otp_mentioned_earlier():
    tx = OTP_TX + "\n" + DONE_TX
    assert classify_transcript(tx).status == OutcomeStatus.DONE


def test_empty_transcript_is_blocked():
    o = classify_transcript("")
    assert o.status == OutcomeStatus.BLOCKED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_classifier.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'robin.classifier'`.

- [ ] **Step 3: Write `src/robin/classifier.py`**

```python
"""Classify an outbound transcript into exactly DONE/NEEDS_APPROVAL/BLOCKED."""
import re
from robin.models import Outcome, OutcomeStatus

_CONFIRMATION = re.compile(r"\b24HF-\d{4}\b")
_APPROVAL_PHRASES = (
    "one-time code", "verification code", "security question",
    "verify your identity", "text you a code",
)
_OTP_WORD = re.compile(r"\botp\b", re.IGNORECASE)


def _last_non_empty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:200]
    return ""


def classify_transcript(transcript: str) -> Outcome:
    lower = transcript.lower()
    conf = _CONFIRMATION.search(transcript)

    if conf and "refund" in lower:
        return Outcome(status=OutcomeStatus.DONE, confirmation=conf.group(0),
                       detail="cancellation confirmed with last-month refund")

    for phrase in _APPROVAL_PHRASES:
        if phrase in lower:
            return Outcome(status=OutcomeStatus.NEEDS_APPROVAL, confirmation=None,
                           detail=f"verification gate: {phrase}")
    if _OTP_WORD.search(transcript):
        return Outcome(status=OutcomeStatus.NEEDS_APPROVAL, confirmation=None,
                       detail="verification gate: OTP")

    return Outcome(status=OutcomeStatus.BLOCKED, confirmation=None,
                   detail=_last_non_empty_line(transcript) or "no outcome reached")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_classifier.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robin/classifier.py tests/test_classifier.py
git commit -m "feat: outcome classifier (DONE/NEEDS_APPROVAL/BLOCKED)"
```

---

### Task 6: Coverage gate

- [ ] **Step 1: Run the full suite with coverage**

Run: `python3 -m pytest -q`
Expected: all tests pass; `robin` total coverage **≥ 80%** in the
`term-missing` table (target ~100% for this pure core).

- [ ] **Step 2: Lint**

Run: `python3 -m ruff check src tests`
Expected: `All checks passed!` (fix any finding before proceeding).

- [ ] **Step 3: Commit (only if lint fixes were applied)**

```bash
git add -A
git commit -m "chore: ruff clean for pure-logic core"
```

---

## Self-Review

- **Spec coverage:** context pack guard, prompt slot guard, classifier
  three-way (24HF-#### + refund ⇒ DONE) — all from SPEC "Technical
  shape" + design-doc classifier rule. Covered.
- **Git-init bootstrap:** Task 1 Step 0 runs
  `git rev-parse --git-dir || git init` before any file is created.
  Robin is not yet a git repository; this step makes it one (idempotently)
  so every subsequent `git add/commit` across all plans succeeds. The
  existing hardened `.gitignore` is preserved.
- **Placeholder scan:** every code/test step has literal content; no
  TBD/TODO.
- **Type consistency:** `models.py` copied verbatim from the 00 contract;
  `classify_transcript` returns `Outcome`; `load_context_pack` returns
  `ContextPack`; names match what Plans 03/04 import.
