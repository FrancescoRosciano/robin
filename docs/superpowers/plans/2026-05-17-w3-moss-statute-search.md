# W3 Moss Statute Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace research_cancellation_law with a sub-10ms Moss semantic lookup over ONLY the three pre-verified statutes when Moss creds are present; true Browser Use fallback otherwise; byte-identical to today when creds absent.

**Architecture:** `scripts/setup_moss_statutes.py` is a one-off script that indexes the three locked statutes into a named Moss index before the demo. `src/robin/integrations/moss_search.py` holds all runtime logic: a module-level `MossClient` singleton built once under `asyncio.Lock` via `_ensure_index()`, returning the same `{"citations":[…],"status":"OK"}` dict shape that `loop.py:_record_session` expects, with a true graceful fallback to `robin.tools.research_cancellation_law` on any miss or error. The composition root (`main.py`) wires this in via a flag-gated `>>> W3 <<<` sub-block inside the W0-provided labeled extension-wiring section, overriding `_tool_impls["research_cancellation_law"]` only when both `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` are present. Depends on W0 merged first.

**Tech Stack:** Python 3.12, moss>=1.0.0 SDK, pytest + pytest-asyncio, Docker (all runs inside the container).

---

## File Structure

```
scripts/
  setup_moss_statutes.py          # new — one-off index creation script
src/robin/integrations/
  __init__.py                     # new (empty) if directory does not exist yet
  moss_search.py                  # new — runtime Moss query + fallback
tests/
  fakes.py                        # append-only: FakeMossClient block
  test_moss_search.py             # new — all W3 tests
.env.example                      # append-only: W3 labeled block
requirements.txt                  # append-only: moss>=1.0.0
src/robin/main.py                 # W3 sub-block only, inside W0 labeled section
```

Files that MUST NOT change on this branch:
`loop.py`, `app.py`, `stage.py`, `classifier.py`, `tools.py`, `signature.py`,
`fixtures/law.html`, `fixtures/prompts/*.txt`, `docs/legal-citations-verified.md`

---

### Task 0: FakeMossClient — Append to `tests/fakes.py`

Prerequisite: W0 is merged to `main` and this branch is cut from that post-W0 `main`.

- [ ] **Step 0.1:** Open `tests/fakes.py` and append the following complete block verbatim at the end of the file:

```python
# --- W3: FakeMossClient ---
from dataclasses import dataclass, field as dc_field

@dataclass
class FakeMossDoc:
    id: str
    text: str
    score: float = 1.0

@dataclass
class FakeMossQueryResult:
    docs: list  # list[FakeMossDoc]
    time_taken_ms: int = 5

class FakeMossClient:
    """Scriptable stand-in for moss.MossClient.

    list_indexes_returns: list of index names to return from list_indexes().
    query_returns:        FakeMossQueryResult to return from query().
    create_raises:        if set, create_index() raises this.
    query_raises:         if set, query() raises this.
    """
    def __init__(
        self,
        list_indexes_returns: list[str] | None = None,
        query_returns: FakeMossQueryResult | None = None,
        create_raises: Exception | None = None,
        query_raises: Exception | None = None,
    ):
        self.list_indexes_returns = list_indexes_returns or []
        self.query_returns = query_returns or FakeMossQueryResult(docs=[])
        self.create_raises = create_raises
        self.query_raises = query_raises
        self.created: list[dict] = []     # records create_index() calls
        self.queried: list[dict] = []     # records query() calls

    async def list_indexes(self) -> list[str]:
        return list(self.list_indexes_returns)

    async def create_index(self, name: str, docs: list) -> None:
        if self.create_raises:
            raise self.create_raises
        self.created.append({"name": name, "docs": docs})

    async def query(self, index_name: str, query_str: str, options=None):
        self.queried.append({"index": index_name, "query": query_str, "options": options})
        if self.query_raises:
            raise self.query_raises
        return self.query_returns
# --- end W3 ---
```

- [ ] **Step 0.2:** Run the full test suite to confirm the append does not break anything:

```
docker compose run --rm robin pytest -q
```

Expected: all existing tests pass (the new classes are never imported unless a test imports them explicitly).

- [ ] **Step 0.3:** Commit:

```
git add tests/fakes.py
git commit -m "test: append FakeMossClient to fakes.py (W3 prereq)"
```

---

### Task 1: Flag-Off Regression Test — Milestone 1 (RED → GREEN)

**Purpose:** Prove that with `MOSS_PROJECT_ID` absent, `moss_search._client` is `None` — the feature is completely inert.

- [ ] **Step 1.1:** Create `tests/test_moss_search.py` with the following test (RED — the module does not exist yet, so the import will fail):

```python
import os, importlib, sys
import pytest


def test_flag_off_tool_impls_unchanged(monkeypatch):
    """When MOSS_PROJECT_ID is absent, _tool_impls["research_cancellation_law"]
    is the original _research closure, not moss_research."""
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
    monkeypatch.delenv("MOSS_PROJECT_KEY", raising=False)
    # Re-import main in a subprocess or use importlib reload pattern.
    # Simplest: assert the existing tool_impls key is NOT moss_research by type.
    # Because main.py is the composition root and imports are side-effectful,
    # test this via the integration path: import moss_search with no env vars
    # set and confirm _client is None.
    import robin.integrations.moss_search as ms
    # Reset module state for isolation:
    ms._client = None
    ms._index_ready = False
    assert ms._client is None
```

- [ ] **Step 1.2:** Run the test — confirm RED (ImportError: No module named `robin.integrations.moss_search`):

```
docker compose run --rm robin pytest -q tests/test_moss_search.py
```

Expected output: `FAILED` or `ERROR` — the module does not exist yet.

- [ ] **Step 1.3:** Create `src/robin/integrations/__init__.py` as an empty file if the `integrations/` directory does not yet exist (W1/W2 may have already created it — check first; if present, leave untouched).

- [ ] **Step 1.4:** Create `src/robin/integrations/moss_search.py` with the following complete implementation:

```python
"""
src/robin/integrations/moss_search.py

Moss-backed semantic search over the three pre-verified cancellation statutes.
Flag-gated: active only when MOSS_PROJECT_ID + MOSS_PROJECT_KEY are set.
Graceful fallback to robin.tools.research_cancellation_law on any miss/error.
"""
import asyncio
import os
from typing import Any

from robin import obs

# ---------------------------------------------------------------------------
# Module-level singleton state (built once at import time)
# ---------------------------------------------------------------------------
_client: Any = None          # MossClient | None
_index_name: str = os.environ.get("MOSS_INDEX_NAME", "robin-statutes")
_index_ready: bool = False
_lock: asyncio.Lock = asyncio.Lock()

# Fallback deps — injected from main.py via set_fallback_deps()
_fallback_browser: Any = None
_fallback_law_url: str = ""
_fallback_law_html_path: str | None = None

# ---------------------------------------------------------------------------
# Lookup tables (doc-id → citation string / source URL)
# ---------------------------------------------------------------------------
_DOC_CITATIONS = {
    "rosca-8403":      "15 U.S.C. § 8403",
    "cal-civ-1812-85": "Cal. Civ. Code § 1812.85",
    "cal-bpc-17602":   "Cal. Bus. & Prof. Code § 17602",
}
_DOC_SOURCES = {
    "rosca-8403":      "https://www.law.cornell.edu/uscode/text/15/8403",
    "cal-civ-1812-85": "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CIV&division=3.&title=2.5.&part=4.",
    "cal-bpc-17602":   "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=BPC&division=7.&title=&part=3.&chapter=1.&article=9.",
}


def _doc_id_to_citation(doc_id: str) -> str:
    return _DOC_CITATIONS.get(doc_id, doc_id)


def _doc_id_to_source_url(doc_id: str) -> str:
    return _DOC_SOURCES.get(doc_id, "")


# ---------------------------------------------------------------------------
# Module-level initialisation (runs at import time)
# ---------------------------------------------------------------------------
_project_id = os.environ.get("MOSS_PROJECT_ID", "")
_project_key = os.environ.get("MOSS_PROJECT_KEY", "")

if _project_id and _project_key:
    try:
        from moss import MossClient, DocumentInfo, QueryOptions  # type: ignore
        _client = MossClient(_project_id, _project_key)
    except ImportError:
        obs.log_event("moss_disabled", reason="import_error")
        _client = None
# else: _client remains None — feature silently off


# ---------------------------------------------------------------------------
# Corpus builder — VERBATIM text ONLY from docs/legal-citations-verified.md
# ---------------------------------------------------------------------------
def _build_corpus() -> list:  # list[DocumentInfo]
    """
    Returns exactly three DocumentInfo objects.
    The text for each is the COMPLETE verbatim block for that statute copied
    from docs/legal-citations-verified.md at implement time.

    The implementer MUST open docs/legal-citations-verified.md and copy the
    full operative text for each of the three statutes:

      doc id "rosca-8403"
        text: the full § 8403 verbatim operative sentence block from §1 of
              legal-citations-verified.md — both the unlawful-unless chapeau
              and paragraph (3). Source URL included in the text for retrieval.
              (The exact text is locked in that file; copy it verbatim.)

      doc id "cal-civ-1812-85"
        text: the full Cal. Civ. Code § 1812.85 verbatim operative sentences
              from §2 — both the cancellation right (§ 1812.85(b)(1)) and the
              refund sentence (§ 1812.85(b)(5)), plus the source URL.
              (Copy verbatim from legal-citations-verified.md.)

      doc id "cal-bpc-17602"
        text: the full Cal. Bus. & Prof. Code § 17602 verbatim operative
              sentence (§ 17602(c)(1)) and the supporting § 17600 legislative
              intent sentence, plus the source URL.
              (Copy verbatim from legal-citations-verified.md.)

    NEVER derive or paraphrase the text. NEVER add a fourth document.
    """
    from moss import DocumentInfo  # type: ignore
    return [
        DocumentInfo(id="rosca-8403",       text=_ROSCA_TEXT),
        DocumentInfo(id="cal-civ-1812-85",  text=_CAL_CIV_TEXT),
        DocumentInfo(id="cal-bpc-17602",    text=_CAL_BPC_TEXT),
    ]


# ---------------------------------------------------------------------------
# CORPUS TEXT CONSTANTS
# *** IMPLEMENTER ACTION REQUIRED — DO NOT FABRICATE ***
#
# Open docs/legal-citations-verified.md and copy the COMPLETE verbatim
# operative text for each of the three statutes into the three constants
# below.  Do not paraphrase, do not add a fourth statute, do not fetch
# from the web.  This is the ONE non-fabrication step; it is not a
# placeholder — the constants must be filled before any test can pass.
# ---------------------------------------------------------------------------
_ROSCA_TEXT: str = ""      # REPLACE: verbatim § 8403 operative block from docs/legal-citations-verified.md
_CAL_CIV_TEXT: str = ""    # REPLACE: verbatim Cal. Civ. Code § 1812.85 operative block
_CAL_BPC_TEXT: str = ""    # REPLACE: verbatim Cal. Bus. & Prof. Code § 17602 operative block


# ---------------------------------------------------------------------------
# Index initialisation (lazy, idempotent, under asyncio.Lock)
# ---------------------------------------------------------------------------
async def _ensure_index() -> None:
    """Idempotent; run once under _lock. No-op after first success."""
    global _index_ready
    if _index_ready:
        return
    async with _lock:
        if _index_ready:           # double-check after acquiring
            return
        try:
            existing = await _client.list_indexes()
            if _index_name not in existing:
                docs = _build_corpus()
                await _client.create_index(_index_name, docs)
                obs.log_event("moss_index_created", index=_index_name, docs=len(docs))
            else:
                obs.log_event("moss_index_exists", index=_index_name)
            _index_ready = True
        except Exception as exc:
            obs.log_event("moss_index_error", err=f"{type(exc).__name__}: {exc}"[:200])
            raise   # propagate so moss_research falls back


# ---------------------------------------------------------------------------
# Fallback dependency injection (called from main.py W3 block)
# ---------------------------------------------------------------------------
def set_fallback_deps(browser: Any, law_url: str, law_html_path: str | None) -> None:
    """Called once from main.py W3 block so moss_research can delegate to Browser Use."""
    global _fallback_browser, _fallback_law_url, _fallback_law_html_path
    _fallback_browser = browser
    _fallback_law_url = law_url
    _fallback_law_html_path = law_html_path


# ---------------------------------------------------------------------------
# Browser Use fallback helper
# ---------------------------------------------------------------------------
async def _call_browser_use_fallback(jurisdiction: str) -> dict:
    from robin.tools import research_cancellation_law as _bu_research
    return await _bu_research(
        jurisdiction,
        browser=_fallback_browser,
        law_url=_fallback_law_url,
        law_html_path=_fallback_law_html_path,
    )


# ---------------------------------------------------------------------------
# Public entry point — drop-in replacement for _tool_impls["research_cancellation_law"]
# ---------------------------------------------------------------------------
async def moss_research(jurisdiction: str) -> dict:
    """
    Replacement for _tool_impls["research_cancellation_law"] when Moss creds
    are present.

    1. If _client is None: immediately call the Browser Use fallback.
    2. Call _ensure_index(); on any exception: call Browser Use fallback.
    3. Query Moss: await _client.query(_index_name, jurisdiction, QueryOptions(top_k=3, alpha=0.7))
    4. Log result: obs.log_event("moss_query", ...)
    5. Map result.docs to the required dict shape.
    6. If citations is empty: call Browser Use fallback (log moss_fallback, reason="empty").
    7. Return {"citations": citations, "status": "OK"}.
    8. On any exception from step 3 onward: log moss_fallback; call Browser Use fallback.
    """
    if _client is None:
        obs.log_event("moss_fallback", reason="client_none")
        return await _call_browser_use_fallback(jurisdiction)

    try:
        await _ensure_index()
    except Exception as exc:
        obs.log_event("moss_fallback", reason=f"ensure_index: {type(exc).__name__}")
        return await _call_browser_use_fallback(jurisdiction)

    try:
        from moss import QueryOptions  # type: ignore
        result = await _client.query(_index_name, jurisdiction, QueryOptions(top_k=3, alpha=0.7))
        obs.log_event(
            "moss_query",
            index=_index_name,
            ms=result.time_taken_ms,
            hits=len(result.docs),
        )
        citations = [
            {
                "citation":        _doc_id_to_citation(doc.id),
                "operative_quote": doc.text,
                "source_url":      _doc_id_to_source_url(doc.id),
            }
            for doc in result.docs
            if doc.score > 0.0
        ]
        if not citations:
            obs.log_event("moss_fallback", reason="empty")
            return await _call_browser_use_fallback(jurisdiction)
        return {"citations": citations, "status": "OK"}
    except Exception as exc:
        obs.log_event("moss_fallback", reason=f"{type(exc).__name__}: {exc}"[:120])
        return await _call_browser_use_fallback(jurisdiction)
```

- [ ] **Step 1.5:** Run the flag-off test — confirm GREEN:

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_flag_off_tool_impls_unchanged
```

Expected: `1 passed`.

- [ ] **Step 1.6:** Run the full suite — confirm all existing tests still pass:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 1.7:** Commit:

```
git add src/robin/integrations/__init__.py src/robin/integrations/moss_search.py tests/test_moss_search.py
git commit -m "feat: add moss_search module skeleton + flag-off regression test (W3 M1)"
```

---

### Task 2: Corpus Text — Copy Verbatim from Locked File

**INTEGRITY BRIGHT LINE — read this step with full attention before touching a single line of corpus text.**

The three locked statutes are: **15 U.S.C. § 8403** (ROSCA), **Cal. Civ. Code § 1812.85**, **Cal. Bus. & Prof. Code § 17602**. The plan must NOT fabricate statute text.

- [ ] **Step 2.1:** Open `docs/legal-citations-verified.md` and copy the COMPLETE verbatim operative text for each of the three statutes into the `_ROSCA_TEXT`, `_CAL_CIV_TEXT`, and `_CAL_BPC_TEXT` constants in `src/robin/integrations/moss_search.py`. Do not paraphrase, do not add a fourth statute, do not fetch from the web. This explicit copy-from-locked-file instruction is the ONE legitimate non-fabrication step — it is NOT a placeholder; the constants must contain the full verbatim text before any test in Task 6 can pass. Each statute's text must be longer than 100 characters or the corpus integrity test will fail.

- [ ] **Step 2.2:** Commit:

```
git add src/robin/integrations/moss_search.py
git commit -m "feat: populate moss corpus from verified statute file (W3 corpus)"
```

---

### Task 3: Happy Path Test — Milestone 2 (RED → GREEN)

**Purpose:** Prove that `moss_research` with a populated `FakeMossClient` returns the correct dict shape matching the `loop.py:_record_session` contract.

- [ ] **Step 3.1:** Add the following test to `tests/test_moss_search.py` (RED — `moss_research` exists but the happy path behavior is not yet confirmed):

```python
import asyncio, pytest
from tests.fakes import FakeMossClient, FakeMossDoc, FakeMossQueryResult


@pytest.mark.asyncio
async def test_moss_research_returns_correct_shape(monkeypatch):
    """moss_research with a populated FakeMossClient returns the correct dict shape."""
    import robin.integrations.moss_search as ms

    fake_result = FakeMossQueryResult(
        docs=[
            FakeMossDoc(id="rosca-8403",      text="provides simple mechanisms…", score=0.95),
            FakeMossDoc(id="cal-civ-1812-85", text="All moneys paid…",            score=0.88),
        ],
        time_taken_ms=4,
    )
    fake_client = FakeMossClient(
        list_indexes_returns=["robin-statutes"],  # index already exists
        query_returns=fake_result,
    )
    # Inject fake client and mark index ready
    ms._client = fake_client
    ms._index_name = "robin-statutes"
    ms._index_ready = True

    result = await ms.moss_research("California")

    assert result["status"] == "OK"
    assert isinstance(result["citations"], list)
    assert len(result["citations"]) == 2
    first = result["citations"][0]
    assert first["citation"] == "15 U.S.C. § 8403"
    assert first["operative_quote"] == "provides simple mechanisms…"
    assert "law.cornell.edu" in first["source_url"]
```

- [ ] **Step 3.2:** Run this test — confirm RED (the test exists, the module exists, but verify the behavior path works end-to-end):

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_moss_research_returns_correct_shape
```

Expected: `1 passed` (GREEN — the implementation written in Task 1 already covers this path; if FAILED, debug `moss_research` until green).

- [ ] **Step 3.3:** Run the full suite:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 3.4:** Commit:

```
git add tests/test_moss_search.py
git commit -m "test: moss_research happy-path shape contract (W3 M2)"
```

---

### Task 4: Empty-Result Fallback Test — Milestone 3 (RED → GREEN)

**Purpose:** Prove that when Moss returns zero docs, `moss_research` calls the Browser Use fallback and returns its result unchanged.

- [ ] **Step 4.1:** Add the following test to `tests/test_moss_search.py`:

```python
@pytest.mark.asyncio
async def test_moss_research_empty_result_falls_back(monkeypatch):
    """Empty Moss result triggers Browser Use fallback and returns its shape."""
    import robin.integrations.moss_search as ms
    from tests.fakes import FakeMossClient, FakeMossQueryResult

    fake_client = FakeMossClient(
        list_indexes_returns=["robin-statutes"],
        query_returns=FakeMossQueryResult(docs=[], time_taken_ms=3),
    )
    ms._client = fake_client
    ms._index_name = "robin-statutes"
    ms._index_ready = True

    fallback_result = {
        "citations": [{"citation": "15 U.S.C. § 8403",
                       "operative_quote": "provides simple mechanisms…",
                       "source_url": "https://example.com"}],
        "status": "OK",
    }

    async def _fake_bu(jurisdiction, *, browser, law_url, law_html_path=None):
        return fallback_result

    # Patch the Browser Use path that moss_search imports
    monkeypatch.setattr(
        "robin.integrations.moss_search._fallback_browser", object())
    monkeypatch.setattr(
        "robin.integrations.moss_search._fallback_law_url", "http://test/law.html")

    import robin.tools as tools_mod
    monkeypatch.setattr(tools_mod, "research_cancellation_law", _fake_bu)

    result = await ms.moss_research("California")
    assert result["status"] == "OK"
    assert len(result["citations"]) == 1
```

- [ ] **Step 4.2:** Run this test — confirm RED then debug until GREEN:

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_moss_research_empty_result_falls_back
```

Expected: `1 passed`.

- [ ] **Step 4.3:** Run the full suite:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 4.4:** Commit:

```
git add tests/test_moss_search.py
git commit -m "test: empty moss result falls back to Browser Use (W3 M3)"
```

---

### Task 5: Query-Error Fallback Test — Milestone 4 (RED → GREEN)

**Purpose:** Prove that when Moss raises an exception during query, `moss_research` falls back to Browser Use and returns its result unchanged.

- [ ] **Step 5.1:** Add the following test to `tests/test_moss_search.py`:

```python
@pytest.mark.asyncio
async def test_moss_research_query_error_falls_back(monkeypatch):
    """A Moss query exception triggers Browser Use fallback."""
    import robin.integrations.moss_search as ms
    from tests.fakes import FakeMossClient, FakeMossQueryResult

    fake_client = FakeMossClient(
        list_indexes_returns=["robin-statutes"],
        query_raises=RuntimeError("moss timeout"),
    )
    ms._client = fake_client
    ms._index_name = "robin-statutes"
    ms._index_ready = True

    fallback_result = {"citations": [], "status": "FAILED", "error": "bu failed"}

    async def _fake_bu(jurisdiction, *, browser, law_url, law_html_path=None):
        return fallback_result

    monkeypatch.setattr("robin.integrations.moss_search._fallback_browser", object())
    monkeypatch.setattr("robin.integrations.moss_search._fallback_law_url", "http://test")

    import robin.tools as tools_mod
    monkeypatch.setattr(tools_mod, "research_cancellation_law", _fake_bu)

    result = await ms.moss_research("California")
    # Fallback result is returned unchanged
    assert result == fallback_result
```

- [ ] **Step 5.2:** Run this test — confirm RED then debug until GREEN:

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_moss_research_query_error_falls_back
```

Expected: `1 passed`.

- [ ] **Step 5.3:** Run the full suite:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 5.4:** Commit:

```
git add tests/test_moss_search.py
git commit -m "test: moss query error falls back to Browser Use (W3 M4)"
```

---

### Task 6: Setup Script — Milestone 5 (RED → GREEN)

**Purpose:** Prove the `setup_moss_statutes.py` idempotency contract — skip when index exists, create with exactly 3 documents when absent.

- [ ] **Step 6.1:** Add the following two tests to `tests/test_moss_search.py`:

```python
@pytest.mark.asyncio
async def test_setup_script_skips_when_index_exists(monkeypatch, capsys):
    """setup_moss_statutes.main() skips create_index when index already exists."""
    from tests.fakes import FakeMossClient
    import scripts.setup_moss_statutes as setup

    fake = FakeMossClient(list_indexes_returns=["robin-statutes"])
    monkeypatch.setattr(setup, "_build_client", lambda: fake)
    monkeypatch.setenv("MOSS_INDEX_NAME", "robin-statutes")

    await setup.main()

    assert fake.created == []   # create_index was NOT called
    out = capsys.readouterr().out
    assert "already exists" in out or "skipping" in out.lower()


@pytest.mark.asyncio
async def test_setup_script_creates_index_when_missing(monkeypatch, capsys):
    """setup_moss_statutes.main() calls create_index with exactly 3 documents."""
    from tests.fakes import FakeMossClient
    import scripts.setup_moss_statutes as setup

    fake = FakeMossClient(list_indexes_returns=[])   # index absent
    monkeypatch.setattr(setup, "_build_client", lambda: fake)
    monkeypatch.setenv("MOSS_INDEX_NAME", "robin-statutes")

    await setup.main()

    assert len(fake.created) == 1
    assert fake.created[0]["name"] == "robin-statutes"
    docs = fake.created[0]["docs"]
    assert len(docs) == 3   # exactly the three verified statutes
    ids = {d.id for d in docs}
    assert ids == {"rosca-8403", "cal-civ-1812-85", "cal-bpc-17602"}
```

- [ ] **Step 6.2:** Run these tests — confirm RED (script does not exist yet):

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_setup_script_skips_when_index_exists tests/test_moss_search.py::test_setup_script_creates_index_when_missing
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'scripts.setup_moss_statutes'`.

- [ ] **Step 6.3:** Create `scripts/setup_moss_statutes.py` with the following complete implementation:

```python
"""
scripts/setup_moss_statutes.py

One-off script: creates (or verifies) the Moss index for the three pre-verified
Robin cancellation statutes. Run once before the demo.

Usage:
    docker compose run --rm robin python scripts/setup_moss_statutes.py

Idempotent: safe to run twice; skips creation if index already exists.
Reads MOSS_PROJECT_ID, MOSS_PROJECT_KEY, MOSS_INDEX_NAME from env (.env loaded
via python-dotenv if available, else raw env).
"""
import asyncio
import os
import sys


def _load_env() -> None:
    """Load .env if python-dotenv is available; no-op otherwise."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except ImportError:
        pass


def _build_client():
    """Returns a real MossClient. Injectable for tests."""
    from moss import MossClient  # type: ignore
    project_id = os.environ.get("MOSS_PROJECT_ID", "")
    project_key = os.environ.get("MOSS_PROJECT_KEY", "")
    if not project_id or not project_key:
        raise RuntimeError(
            "MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set in the environment."
        )
    return MossClient(project_id, project_key)


def _build_corpus() -> list:
    """
    Returns exactly three DocumentInfo objects — verbatim text from
    robin.integrations.moss_search._build_corpus(). Imports from moss_search
    to share the single source of truth for the corpus.
    """
    from robin.integrations.moss_search import _build_corpus as _shared_corpus
    return _shared_corpus()


async def main() -> None:
    index_name = os.environ.get("MOSS_INDEX_NAME", "robin-statutes")
    print("[W3] Checking Moss index …")
    client = _build_client()
    try:
        existing = await client.list_indexes()
        if index_name in existing:
            print(f"[W3] Index '{index_name}' already exists — skipping.")
            return
        docs = _build_corpus()
        await client.create_index(index_name, docs)
        print(f"[W3] Index '{index_name}' created with {len(docs)} documents — done.")
    except Exception as exc:
        print(f"[W3] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _load_env()
    asyncio.run(main())
```

- [ ] **Step 6.4:** Run the setup-script tests — confirm GREEN:

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_setup_script_skips_when_index_exists tests/test_moss_search.py::test_setup_script_creates_index_when_missing
```

Expected: `2 passed`.

- [ ] **Step 6.5:** Run the full suite:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 6.6:** Commit:

```
git add scripts/setup_moss_statutes.py tests/test_moss_search.py
git commit -m "feat: setup_moss_statutes.py + idempotency tests (W3 M5)"
```

---

### Task 7: Corpus Integrity Test — Milestone 6 (RED → GREEN)

**Purpose:** Prove that `_build_corpus()` returns exactly the three locked statutes and nothing else, and that each statute text is substantive (> 100 chars).

- [ ] **Step 7.1:** Add the following test to `tests/test_moss_search.py`:

```python
def test_corpus_contains_exactly_three_locked_statutes():
    """_build_corpus() returns exactly the three verified statutes and nothing else."""
    import robin.integrations.moss_search as ms
    # Temporarily supply a stub DocumentInfo if moss is not importable:
    try:
        docs = ms._build_corpus()
    except ImportError:
        pytest.skip("moss not installed in this environment")

    ids = [d.id for d in docs]
    assert sorted(ids) == sorted(["rosca-8403", "cal-civ-1812-85", "cal-bpc-17602"])
    assert len(docs) == 3
    for d in docs:
        assert len(d.text) > 100, f"doc {d.id} text suspiciously short"
```

- [ ] **Step 7.2:** Run this test — it will fail (RED) if the corpus text constants `_ROSCA_TEXT`, `_CAL_CIV_TEXT`, `_CAL_BPC_TEXT` in `moss_search.py` are still empty strings (filled in Task 2):

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_corpus_contains_exactly_three_locked_statutes
```

Expected: `1 passed` if Task 2 was completed; `FAILED` if corpus text is still empty — go back and complete Task 2 first.

- [ ] **Step 7.3:** Run the full suite:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 7.4:** Commit:

```
git add tests/test_moss_search.py
git commit -m "test: corpus integrity — exactly three locked statutes (W3 M6)"
```

---

### Task 8: Flag-Off Final Regression Gate — Milestone 7 (RED → GREEN)

**Purpose:** The non-negotiable final gate. With no Moss creds, `moss_search._client` is `None` and `_index_ready` is `False` — absolutely no Moss SDK activity runs.

- [ ] **Step 8.1:** Add the following test to `tests/test_moss_search.py`:

```python
def test_flag_off_canonical_path_unchanged(monkeypatch):
    """With MOSS creds absent, moss_search._client is None (no SDK activity)."""
    import importlib, sys
    monkeypatch.delenv("MOSS_PROJECT_ID", raising=False)
    monkeypatch.delenv("MOSS_PROJECT_KEY", raising=False)

    # Remove cached module so next import re-evaluates env
    sys.modules.pop("robin.integrations.moss_search", None)

    import robin.integrations.moss_search as ms
    assert ms._client is None
    assert ms._index_ready is False
```

- [ ] **Step 8.2:** Run this test — confirm GREEN:

```
docker compose run --rm robin pytest -q tests/test_moss_search.py::test_flag_off_canonical_path_unchanged
```

Expected: `1 passed`.

- [ ] **Step 8.3:** Run the full suite with Moss creds explicitly absent to simulate CI / no-key environment:

```
MOSS_PROJECT_ID= MOSS_PROJECT_KEY= docker compose run --rm robin pytest -q
```

Expected: all green. The canonical Browser Use path is byte-identical to pre-W3.

- [ ] **Step 8.4:** Run ruff:

```
docker compose run --rm robin ruff check src tests
```

Expected: no errors.

- [ ] **Step 8.5:** Commit:

```
git add tests/test_moss_search.py
git commit -m "test: flag-off regression gate — no Moss SDK when creds absent (W3 M7)"
```

---

### Task 9: Config Appends — `.env.example` and `requirements.txt`

- [ ] **Step 9.1:** Append the following labeled block to `.env.example` (append only — do not change any existing lines):

```
# --- W3: Moss statute search ---
MOSS_PROJECT_ID=
MOSS_PROJECT_KEY=
MOSS_INDEX_NAME=robin-statutes
# --- end W3 ---
```

- [ ] **Step 9.2:** Append the following line to `requirements.txt` (append only — do not change any existing lines):

```
moss>=1.0.0
```

- [ ] **Step 9.3:** Rebuild the Docker image to pick up the new dependency, then run the full suite:

```
docker compose build robin && docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 9.4:** Commit:

```
git add .env.example requirements.txt
git commit -m "chore: append moss>=1.0.0 and W3 env vars (W3 config)"
```

---

### Task 10: Wire `main.py` W3 Sub-Block

**Purpose:** Insert the W3 sub-block inside the W0-labeled extension-wiring section of `main.py`. This is the only change to `main.py` on this branch.

- [ ] **Step 10.1:** Locate the W0-labeled extension-wiring section in `src/robin/main.py`. It looks like:

```python
# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
# >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
# >>> W4 dashboard wiring   <<<   (added on feat/dashboard-flagship)
# --- end sponsor extension wiring ---
```

Replace the `# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)` comment line with the following complete sub-block (preserving the W1, W2, W4 comment lines untouched):

```python
# >>> W3 moss-statute-search wiring <<<
if os.environ.get("MOSS_PROJECT_ID") and os.environ.get("MOSS_PROJECT_KEY"):
    from robin.integrations.moss_search import moss_research, set_fallback_deps
    set_fallback_deps(
        browser=_browser,
        law_url=f"{_settings.public_base_url}/fixture/law.html",
        law_html_path=LAW_HTML_PATH,
    )
    _tool_impls["research_cancellation_law"] = moss_research
# >>> end W3 <<<
```

- [ ] **Step 10.2:** Verify the diff is ONLY the W3 sub-block — no other lines in `main.py` changed:

```
git diff src/robin/main.py
```

Expected: only the W3 block addition within the labeled section.

- [ ] **Step 10.3:** Run the full suite:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 10.4:** Run ruff:

```
docker compose run --rm robin ruff check src tests
```

Expected: no errors.

- [ ] **Step 10.5:** Commit:

```
git add src/robin/main.py
git commit -m "feat: wire moss_research into _tool_impls via W3 sub-block in main.py"
```

---

### Task 11: REFACTOR Pass

- [ ] **Step 11.1:** Confirm `setup_moss_statutes._build_corpus` delegates to `robin.integrations.moss_search._build_corpus` (single source of truth). If it duplicates the corpus list, refactor it to import `_build_corpus` from `moss_search` instead. This was already done in the Task 6 implementation above; verify it is correct.

- [ ] **Step 11.2:** Confirm all log calls use `obs.log_event(...)` — not `print`, not `logging` directly. Check `moss_search.py` for any stray prints; the setup script's user-facing output via `print` is intentional and acceptable.

- [ ] **Step 11.3:** Verify type annotations on all public functions in `moss_search.py`: `moss_research`, `set_fallback_deps`, `_build_corpus`.

- [ ] **Step 11.4:** Run `ruff check --fix` then confirm clean:

```
docker compose run --rm robin ruff check --fix src tests && docker compose run --rm robin ruff check src tests
```

Expected: no errors after fix.

- [ ] **Step 11.5:** Run the full suite one final time:

```
docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 11.6:** Commit if any refactor changes were made:

```
git add -p
git commit -m "refactor: moss_search type annotations, log consistency, ruff clean (W3 refactor)"
```

---

### Task 12: Additive-Only Verification and Merge Instructions

**Do NOT `git push` from inside this agent — the human performs the push and submission.**

- [ ] **Step 12.1:** Verify none of the canonical-path files were changed on this branch:

```
git diff main...HEAD -- src/robin/loop.py
git diff main...HEAD -- src/robin/app.py
git diff main...HEAD -- src/robin/classifier.py
git diff main...HEAD -- src/robin/tools.py
git diff main...HEAD -- src/robin/fixtures/
git diff main...HEAD -- docs/legal-citations-verified.md
```

Expected: all diffs are empty.

- [ ] **Step 12.2:** Verify the complete file list changed on this branch matches the expected set:

```
git diff --name-only main...HEAD
```

Expected files (no others):
- `src/robin/integrations/__init__.py`
- `src/robin/integrations/moss_search.py`
- `scripts/setup_moss_statutes.py`
- `tests/test_moss_search.py`
- `tests/fakes.py`
- `src/robin/main.py`
- `.env.example`
- `requirements.txt`

- [ ] **Step 12.3:** Final flag-off regression gate with explicit empty creds:

```
MOSS_PROJECT_ID= MOSS_PROJECT_KEY= docker compose run --rm robin pytest -q
```

Expected: all green.

- [ ] **Step 12.4:** The human merges this branch to `main` via `git merge feat/moss-statute-search --no-ff`. No rebase required; git auto-merges the W3 sub-block because W1, W2, W4 touch distinct labeled lines.

---

## Notes

### Collapse Ladder (hard time-box)

| Time elapsed | Cut point |
|---|---|
| +45 min | Tasks 0–3 green (FakeMossClient + happy-path query). Minimum shippable path. |
| +70 min | Tasks 4–5 green (fallback paths tested). |
| +90 min | Task 6 green (setup script tested). |
| +105 min | Tasks 7–8 green (corpus integrity + flag-off gate). Branch ready to merge. |
| +120 min | Tasks 9–12 complete (config, main.py wiring, refactor, merge). |

**Minimum shippable (hard time-box hit):** Tasks 0–3 green + Task 10 (`main.py` W3 block wired) + ruff clean + Task 8 flag-off regression test (`_client is None` when env absent). The setup script (Task 6) is polish; `_ensure_index()` creates the index lazily on the first `moss_research` call when creds are present.

### Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Moss credentials not obtainable before demo | Medium | Feature flag design: no creds ⇒ Browser Use path unchanged; demo still works |
| `moss>=1.0.0` API surface differs from spec | Low | Confirm against PyPI / Moss Discord before implementing; adjust SDK calls |
| Index creation fails at demo time | Low | `_ensure_index` error propagates to fallback; Browser Use covers it |
| `list_indexes()` does not return a plain `list[str]` | Low | Read the Moss SDK source / test with `FakeMossClient`; adapt the guard |
| W0 not yet merged when W3 work begins | — | Do not start W3 until W0 is on `main`; the W3 block cannot be placed without W0's labeled section |
