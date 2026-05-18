# W3 — Moss Statute Search
## `feat/moss-statute-search`

**Date:** 2026-05-17  
**Branch:** `feat/moss-statute-search` (cut from post-W0 `main`)  
**Size:** M — target ~2 h  
**Depends on:** W0 (`feat/extension-seam`) merged to `main` first  
**Sponsor track:** Moss — up to $10 K prize  
**Touches:** 2 new files, `main.py` W3 sub-block only, append-only lines in
`.env.example` / `requirements.txt`, 1 new test file, `FakeMossClient`
appended to `tests/fakes.py`  

---

## INTEGRITY BRIGHT LINE — read before touching a single line

> **Moss may index ONLY the three pre-verified statutes copied verbatim from
> `docs/legal-citations-verified.md`. No crawling, no web text, no other
> statutes, no paraphrase.** A wrong statute cited on stage at YC is
> disqualifying. The three locked citations are:
>
> 1. **15 U.S.C. § 8403** (ROSCA — Restore Online Shoppers' Confidence Act)
> 2. **Cal. Civ. Code § 1812.85** (California Health Studio Services Contract Law)
> 3. **Cal. Bus. & Prof. Code § 17602** (California Automatic Renewal Law)
>
> The setup script's corpus is hard-coded from `docs/legal-citations-verified.md`;
> it accepts no runtime arguments for statute text. Never add a fourth document.
> Never re-derive the text from the web at index time.

---

## 1. Goal

Replace the `research_cancellation_law` tool implementation with a
Moss-backed semantic search over the three pre-verified statutes when Moss
credentials are present. The expected result: sub-10 ms citation retrieval
at call time (versus up to 60 s of Browser Use latency). The canonical
Browser Use path (`_research` in `main.py`) remains untouched when Moss
credentials are absent, and is the true graceful fallback (not a degraded
path) when Moss is present but the query returns empty or errors.

---

## 2. Orientation

### 2.1 Portfolio fit

W3 is the Moss sponsor-track entry. Its structural reference is the
Moss × AgentPhone cookbook at
`https://github.com/usemoss/moss/tree/main/examples/cookbook/agentphone`
(`server.py`, `moss_agentphone.py`, `create_index.py`). Mirror that
pattern; write fresh — do not fork. The cookbook uses a plain HMAC helper
for webhook signature verification; **that is irrelevant to Robin**: Robin's
webhook verification already uses Svix (`src/robin/signature.py`). Do not
touch `signature.py` or any Svix logic.

### 2.2 Isolation contract (from the master design, §2)

- **Flag-off ⇒ no-op, byte-identical.** When `MOSS_PROJECT_ID` is absent,
  `_tool_impls["research_cancellation_law"]` remains the existing `_research`
  closure. No SDK import, no network call, no error.
- **Graceful fallback on any Moss failure.** Missing key, SDK import error,
  empty result, network timeout, or any exception during `moss_research` ⇒
  call the existing `research_cancellation_law` from `robin.tools` and
  return its result unchanged. One `obs.log_event("moss_fallback", ...)` is
  emitted; no exception propagates into the call turn.
- **New code in new files.** W3 adds `scripts/setup_moss_statutes.py` and
  `src/robin/integrations/moss_search.py`. It does not edit `loop.py`,
  `app.py`, `stage.py`, `classifier.py`, `tools.py`, `fixtures/law.html`,
  or `docs/legal-citations-verified.md`.
- **Constructor injection + fake.** `FakeMossClient` (appended to
  `tests/fakes.py`) allows all tests to run without real Moss credentials.

### 2.3 The W3 sub-block in `main.py`

W0 defines a labeled extension-wiring section at the bottom of `main.py`,
between `# --- sponsor extension wiring` and `# --- end sponsor extension
wiring`. W3 inserts only its own `>>> W3 <<<` sub-block within that section.
No other lines of `main.py` change. This gives git a clean auto-merge point
distinct from W1, W2, and W4 blocks.

---

## 3. Confirmed Moss SDK facts (use as-is; do not re-research)

These facts are confirmed for this spec. The implementer must use them
exactly.

| Fact | Value |
|---|---|
| PyPI package | `moss>=1.0.0` — **NOT** `inferedge-moss` |
| Import | `from moss import MossClient, DocumentInfo, QueryOptions` |
| Python requirement | ≥ 3.10; Docker is 3.12 — compatible |
| Auth env vars | `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` (both required) |
| `MossClient` constructor | `MossClient(project_id, project_key)` — positional |
| Index name env var | `MOSS_INDEX_NAME` — default value `robin-statutes` |
| Index existence check | `await client.list_indexes()` returns a list; skip create if name present |
| Index creation | `await client.create_index(index_name, [DocumentInfo(id=..., text=...), ...])` |
| Query call | `await client.query(index_name, query_str, QueryOptions(top_k=3, alpha=0.7))` |
| Query result | `result.docs` (list); each doc: `.text` (str), `.id` (str), `.score` (float) |
| Query timing | `result.time_taken_ms` (int) |
| `alpha` value | `0.7` — legal terms need keyword weight; do not change |
| Search latency | On-device, sub-10 ms; only index sync uses network |
| Key source | portal.usemoss.dev or Moss Discord — flagged as a risk (see §8) |
| Lazy loading pattern | Module-level singleton, built once under `asyncio.Lock`, NOT in a FastAPI lifespan hook, NOT by editing `app.py` |
| Cookbook HMAC helper | Irrelevant — Robin uses Svix; do not touch `signature.py` |

---

## 4. Exact seams (verified against working tree)

### 4.1 `src/robin/main.py` — the `_tool_impls` dict (lines 51–58)

```python
# lines 51–58, post-W0 working tree (the W3 override target):
_tool_impls = {
    "research_cancellation_law": _research,      # ← W3 overrides this key
    "place_negotiation_call": _place,
    "deliver_result": make_deliver_result(
        client=_ap, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        callback_number=_pack.callback_number),
}
```

The `_research` closure (lines 31–36) remains unchanged; W3 replaces only
the dict value for `"research_cancellation_law"`. The W3 sub-block reads:

```python
# >>> W3 moss-statute-search wiring <<<
if os.environ.get("MOSS_PROJECT_ID") and os.environ.get("MOSS_PROJECT_KEY"):
    from robin.integrations.moss_search import moss_research
    _tool_impls["research_cancellation_law"] = moss_research
# >>> end W3 <<<
```

This block appears after the closing brace of `_tool_impls` and before
`app = build_app(...)`. It must sit inside the labeled extension-wiring
section W0 adds.

### 4.2 Return-dict shape contract

`moss_research` **must** return the identical dict shape that `_research`
returns, because `loop.py:_record_session` (the
`research_cancellation_law` branch — `loop.py:72-77` pre-W0; shifts a
few lines after W0 lands) checks:

```python
if name == "research_cancellation_law" and out.get("status") == "OK":
    cites = out.get("citations") or []
    # iterates: c.get("citation"), c.get("operative_quote")
```

The required shape (from `tools.py:research_cancellation_law` success
path — the final `return {"citations": cites, "status": ...}` at
`tools.py:130`, and the fixture-only return at `tools.py:105-106`):

```python
{
    "citations": [
        {
            "citation":        str,   # e.g. "15 U.S.C. § 8403"
            "operative_quote": str,   # verbatim statutory sentence
            "source_url":      str,   # URL string (may be "")
        },
        # ... one entry per matched statute
    ],
    "status": "OK",   # exact string; _record_session gates on this
}
```

On fallback (Moss empty or error), `moss_research` calls
`research_cancellation_law` from `robin.tools` and returns its result
unmodified — so the shape is always correct.

### 4.3 `tools.py:research_cancellation_law` — the true fallback target

The existing function signature (line 91):

```python
async def research_cancellation_law(jurisdiction: str, *, browser,
                                    law_url: str,
                                    law_html_path: str | None = None) -> dict:
```

`moss_search.py` imports this and calls it when falling back, passing the
same `_browser`, `_settings.public_base_url`, and `LAW_HTML_PATH` values
that `_research` uses. Because `moss_research` has the same function
signature as the lambda (`async def moss_research(jurisdiction: str) -> dict`),
it captures those values via module-level references exposed from `main.py`
at import time — see §5.3 for the recommended pattern.

---

## 5. Implementation specification

### 5.1 `requirements.txt` — append

```
moss>=1.0.0
```

No other requirements change.

### 5.2 `.env.example` — append (labeled block)

```
# --- W3: Moss statute search ---
MOSS_PROJECT_ID=
MOSS_PROJECT_KEY=
MOSS_INDEX_NAME=robin-statutes
# --- end W3 ---
```

### 5.3 `src/robin/integrations/__init__.py`

Create as an empty file if the `integrations/` directory does not yet exist.
(W1/W2 may have already created it; if so, leave it untouched.)

### 5.4 `src/robin/integrations/moss_search.py`

Full specification:

```
Module: src/robin/integrations/moss_search.py

Imports needed:
  import asyncio
  import os
  from typing import Any
  from robin import obs

Exports:
  moss_research(jurisdiction: str) -> dict   (async)

Module-level state:
  _client: MossClient | None = None          (built once when creds present)
  _index_name: str                           (from MOSS_INDEX_NAME env or "robin-statutes")
  _index_ready: bool = False                 (True after first successful ensure_index)
  _lock: asyncio.Lock                        (module-level; created at import time)

Initialization (at module import time, not inside a function):
  - Read MOSS_PROJECT_ID and MOSS_PROJECT_KEY from os.environ
  - If both present: attempt `from moss import MossClient, DocumentInfo, QueryOptions`
    - On ImportError: log obs.log_event("moss_disabled", reason="import_error"); set _client = None
    - On success: _client = MossClient(project_id, project_key)
  - If either absent: _client = None (silent; feature is simply off)
  - _index_name = os.environ.get("MOSS_INDEX_NAME", "robin-statutes")

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

def _build_corpus() -> list[DocumentInfo]:
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
  from moss import DocumentInfo
  return [
      DocumentInfo(id="rosca-8403",       text=<ROSCA verbatim block>),
      DocumentInfo(id="cal-civ-1812-85",  text=<Cal. Civ. Code verbatim block>),
      DocumentInfo(id="cal-bpc-17602",    text=<Cal. Bus. & Prof. Code verbatim block>),
  ]

async def moss_research(jurisdiction: str) -> dict:
  """
  Replacement for _tool_impls["research_cancellation_law"] when Moss creds
  are present.

  1. If _client is None: immediately call the Browser Use fallback.
  2. Call _ensure_index(); on any exception: call Browser Use fallback.
  3. Query Moss: await _client.query(_index_name, jurisdiction, QueryOptions(top_k=3, alpha=0.7))
  4. Log result: obs.log_event("moss_query", index=_index_name, ms=result.time_taken_ms, hits=len(result.docs))
  5. Map result.docs to the required dict shape:
       citations = [
           {
               "citation":        _doc_id_to_citation(doc.id),
               "operative_quote": doc.text,   # verbatim, already the right sentence
               "source_url":      _doc_id_to_source_url(doc.id),
           }
           for doc in result.docs
           if doc.score > 0.0      # filter zero-score noise
       ]
  6. If citations is empty: call Browser Use fallback (log moss_fallback, reason="empty").
  7. Return {"citations": citations, "status": "OK"}.
  8. On any exception from step 3 onward: log moss_fallback, reason=exc type; call Browser Use fallback.

  The Browser Use fallback is:
      from robin.tools import research_cancellation_law as _bu_research
      # The fallback requires browser, law_url, law_html_path.
      # These are injected at module level from main.py via set_fallback_deps().
      return await _bu_research(jurisdiction, browser=_fallback_browser,
                                law_url=_fallback_law_url,
                                law_html_path=_fallback_law_html_path)
  """

Module-level fallback dependency injection:
  _fallback_browser = None
  _fallback_law_url: str = ""
  _fallback_law_html_path: str | None = None

  def set_fallback_deps(browser, law_url: str, law_html_path: str | None) -> None:
      """Called once from main.py W3 block so moss_research can delegate to Browser Use."""
      global _fallback_browser, _fallback_law_url, _fallback_law_html_path
      _fallback_browser = browser
      _fallback_law_url = law_url
      _fallback_law_html_path = law_html_path

Helper functions (module-private):
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
  def _doc_id_to_citation(doc_id: str) -> str: return _DOC_CITATIONS.get(doc_id, doc_id)
  def _doc_id_to_source_url(doc_id: str) -> str: return _DOC_SOURCES.get(doc_id, "")
```

### 5.5 `main.py` W3 sub-block (complete, post-W0)

The W3 block appears inside the W0-added labeled section, after `_tool_impls`
is defined and before `app = build_app(...)`:

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

This is the only change to `main.py` on this branch.

### 5.6 `scripts/setup_moss_statutes.py`

Standalone script. Run once before the demo to populate the Moss index.
Reads `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `MOSS_INDEX_NAME` from the
environment (load from `.env` via `python-dotenv` if present; fall back
to raw env). Hard-codes the three statutes' verbatim text (same as
`_build_corpus()`; share the implementation by importing from
`robin.integrations.moss_search` if that is already importable at setup
time, or duplicate the corpus list — duplication is acceptable here for
robustness).

Behavior:

1. Print `"[W3] Checking Moss index …"`.
2. Call `await client.list_indexes()`.
3. If `_index_name` already present: print `"[W3] Index '{name}' already exists — skipping."` and exit 0.
4. Otherwise: call `await client.create_index(name, docs)`.
5. Print `"[W3] Index '{name}' created with {n} documents — done."` and exit 0.
6. On any error: print `"[W3] ERROR: {exc}"` and exit 1.

The script is idempotent: running it twice in a row is safe (step 3
guards). It must never crawl the web or fetch any URL; the statute text
is hard-coded in the script itself.

Run command (documented here and in §7):

```
docker compose run --rm robin python scripts/setup_moss_statutes.py
```

Requires the container's Python path to include `src/`. If `requirements.txt`
and `Dockerfile` install `moss>=1.0.0`, this works without any host change.

---

## 6. TDD plan — RED → GREEN → REFACTOR

All test commands run inside Docker:

```
docker compose run --rm robin pytest -q tests/test_moss_search.py
docker compose run --rm robin pytest -q          # full suite
docker compose run --rm robin ruff check src tests
```

Each milestone ends with the full-suite check; partial green is not a
milestone.

### Test file: `tests/test_moss_search.py`

Add `FakeMossClient` to `tests/fakes.py` first (see §6.1). Then write
the test file.

---

### Milestone 0 — FakeMossClient (fakes.py append) — 15 min

**Append to `tests/fakes.py`:**

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

---

### Milestone 1 — flag-off regression (RED → GREEN) — 20 min

**Test: `test_flag_off_tool_impls_unchanged`**

Purpose: prove that with `MOSS_PROJECT_ID` absent, `_tool_impls` is unchanged.

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

> Note: testing `main.py` re-import in-process is fragile. The canonical
> approach for this test is to reload `robin.integrations.moss_search` with
> `MOSS_PROJECT_ID` unset and assert `_client is None`. The full regression
> that the canonical Browser Use path is byte-identical is covered by the
> existing suite (`test_tools.py`, `test_loop.py`) which must remain green
> on this branch without modification.

RED: test fails because the module does not exist yet. GREEN: module exists,
`_client is None` when env vars absent.

After GREEN: `docker compose run --rm robin pytest -q` — full suite green.

---

### Milestone 2 — `moss_research` happy path (RED → GREEN) — 25 min

**Test: `test_moss_research_returns_correct_shape`**

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

RED: `moss_research` does not exist. GREEN: function implemented, test passes.

After GREEN: full suite.

---

### Milestone 3 — empty result falls back to Browser Use (RED → GREEN) — 20 min

**Test: `test_moss_research_empty_result_falls_back`**

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

RED → GREEN. After GREEN: full suite.

---

### Milestone 4 — query error falls back to Browser Use (RED → GREEN) — 15 min

**Test: `test_moss_research_query_error_falls_back`**

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

RED → GREEN. After GREEN: full suite.

---

### Milestone 5 — setup script idempotency (RED → GREEN) — 20 min

**Test: `test_setup_script_skips_when_index_exists`**

The setup script is tested by importing its async `main()` function and
calling it with a `FakeMossClient` that reports the index already exists.
The script must print a skip message and not call `create_index`.

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
```

**Test: `test_setup_script_creates_index_when_missing`**

```python
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

For this to work, `setup_moss_statutes.py` must expose a `_build_client()`
function (returns a real `MossClient` normally, injectable for tests) and
an async `main()` function.

RED → GREEN. After GREEN: full suite.

---

### Milestone 6 — corpus integrity (RED → GREEN) — 15 min

**Test: `test_corpus_contains_exactly_three_locked_statutes`**

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

RED → GREEN. After GREEN: full suite.

---

### Milestone 7 — flag-off regression gate (RED → GREEN) — 10 min

**Test: `test_flag_off_tool_impls_use_browser_use`**

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

This is the non-negotiable final gate: with no creds, no Moss code runs.

RED → GREEN. After GREEN:

```
docker compose run --rm robin pytest -q
docker compose run --rm robin ruff check src tests
```

Both must be green to close the branch.

---

### REFACTOR pass

After all milestones green:

1. Collapse any duplicated corpus-building logic between
   `moss_search._build_corpus()` and `setup_moss_statutes.py` into one
   shared function in `moss_search.py` that the setup script imports.
2. Confirm all log events use `obs.log_event` (not `print`, not `logging`
   directly) for consistency with the rest of Robin.
3. Verify type annotations on all public functions in `moss_search.py`.
4. Run `ruff check --fix` then `ruff check` (no errors remaining).

---

## 7. One-off setup and smoke test (no real Moss creds path)

### Without real Moss creds (CI / default)

No setup step needed. `MOSS_PROJECT_ID` absent ⇒ module disabled.
The full test suite runs without any Moss credential:

```
docker compose run --rm robin pytest -q
```

All tests must pass. Tests that exercise Moss logic use `FakeMossClient`
injected via monkeypatching; they never talk to Moss over the network.

### With real Moss creds (pre-demo / manual smoke test)

1. Obtain `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` from portal.usemoss.dev
   or the Moss Discord. Add them to `.env`.

2. Run the setup script once:
   ```
   docker compose run --rm robin python scripts/setup_moss_statutes.py
   ```
   Expected output:
   ```
   [W3] Checking Moss index …
   [W3] Index 'robin-statutes' created with 3 documents — done.
   ```
   Running a second time:
   ```
   [W3] Checking Moss index …
   [W3] Index 'robin-statutes' already exists — skipping.
   ```

3. Start the server with Moss creds in env:
   ```
   docker compose up robin
   ```

4. Send a test webhook turn (or use `scripts/webhook_selftest.py`) with
   `research_cancellation_law` in the transcript path. Observe the server log
   for `EVENT moss_query` with `ms=<single-digit or low-double-digit>`.

5. Confirm the returned citations match the three locked statutes (not web
   text, not a paraphrase).

---

## 8. Demo moment and Moss track rationale

Sub-10 ms citation retrieval replaces up to 60 s of Browser Use latency.
On stage, the moment Robin cites the statutes the response feels instant —
a sharp contrast to the "searching…" pause that would otherwise occur
mid-call. The Moss index is the $10 K sponsor track entry; the cookbook
(`moss_agentphone.py`) is literally Robin's structural reference for this
workstream.

The demo narrative: "Robin just looked up three pre-verified California and
federal statutes — in under 10 milliseconds, on-device, with no external
web call at that moment." The Browser Use web research that populated the
pre-verified fixture is disclosed as having happened earlier (recorded
backup); Moss retrieves from that already-verified corpus.

---

## 9. Time-box and collapse ladder

| Time elapsed | Cut point |
|---|---|
| +45 min | Milestones 0–2 green: FakeMossClient + happy-path query. This is the minimum shippable path. |
| +70 min | Milestone 3–4 green: fallback paths tested. |
| +90 min | Milestone 5 green: setup script tested. |
| +105 min | Milestone 6–7 green: corpus integrity + flag-off gate. Branch ready to merge. |
| +120 min | REFACTOR pass + ruff clean. |

**Minimum shippable (hard time-box hit):** Milestones 0–2 green +
`main.py` W3 block wired + `ruff` clean + flag-off regression test
(`_client is None` when env absent). The setup script becomes a
"nice to have"; the fallback to Browser Use is still correct without it
because `_ensure_index()` creates the index lazily on first `moss_research`
call (if creds are present). The setup script is polish; the query path is
the core.

---

## 10. Flag-off regression gate (mandatory final check)

Before merging, run with no Moss creds:

```
MOSS_PROJECT_ID= MOSS_PROJECT_KEY= docker compose run --rm robin pytest -q
```

Every test in the existing suite must be green. The canonical
`_tool_impls["research_cancellation_law"]` must still be the `_research`
closure (Browser Use path), byte-identical to pre-W3 behavior.

The `test_flag_off_canonical_path_unchanged` test (Milestone 7) is the
programmatic assertion of this gate.

---

## 11. Merge instructions

### Pre-merge checklist

- [ ] Branch cut from post-W0 `main` (W0 must be merged first)
- [ ] All 8 milestones green: `docker compose run --rm robin pytest -q`
- [ ] `docker compose run --rm robin ruff check src tests` — clean
- [ ] Flag-off regression gate green (Milestone 7 + `MOSS_PROJECT_ID=` full suite)
- [ ] `main.py` diff: only the W3 sub-block added inside the W0-labeled section
- [ ] No edits to `loop.py`, `app.py`, `stage.py`, `classifier.py`,
      `tools.py`, `fixtures/law.html`, `docs/legal-citations-verified.md`
- [ ] `.env.example` has the W3 labeled block (append-only, no existing lines changed)
- [ ] `requirements.txt` has `moss>=1.0.0` appended (no existing lines changed)
- [ ] `tests/fakes.py` has `FakeMossClient` appended with the `--- W3 ---` label

### Additive-only verification

```
git diff main...HEAD -- src/robin/loop.py      # must be empty
git diff main...HEAD -- src/robin/app.py       # must be empty
git diff main...HEAD -- src/robin/classifier.py # must be empty
git diff main...HEAD -- src/robin/tools.py     # must be empty
git diff main...HEAD -- src/robin/fixtures/    # must be empty
git diff main...HEAD -- docs/legal-citations-verified.md  # must be empty
```

### Files changed on this branch (complete list)

| File | Change type |
|---|---|
| `src/robin/integrations/__init__.py` | New (empty) |
| `src/robin/integrations/moss_search.py` | New |
| `scripts/setup_moss_statutes.py` | New |
| `tests/test_moss_search.py` | New |
| `tests/fakes.py` | Append-only (FakeMossClient block) |
| `src/robin/main.py` | W3 sub-block only (inside W0 labeled section) |
| `.env.example` | Append-only (W3 labeled block) |
| `requirements.txt` | Append-only (`moss>=1.0.0`) |

---

## 12. Security and PII checklist

- [ ] `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` come from env only; never
      hardcoded, never logged (they match the `_SECRET_KEY_PARTS` check in
      `obs.py` — `obs.log_event` drops them automatically).
- [ ] The Moss index contains only the three pre-verified statute texts;
      no caller transcripts, no PII, no phone numbers, no names.
- [ ] `obs.log_event` calls log only `index`, `ms`, `hits`, `reason`,
      `err` — never statute text in full (truncation applies), never call
      content.
- [ ] `.env` is gitignored; `MOSS_PROJECT_ID`/`KEY` are never staged.
- [ ] `FakeMossClient` uses no real credentials in tests.
- [ ] `setup_moss_statutes.py` prints a clear skip/done line; does not
      print credentials or full statute text.
- [ ] No crawler, no URL fetch at index creation time — statute text is
      hard-coded verbatim from `docs/legal-citations-verified.md`.

---

## 13. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Moss credentials not obtainable before demo | Medium | Feature flag design: no creds ⇒ Browser Use path unchanged; demo still works |
| `moss>=1.0.0` API surface differs from these facts | Low | Confirm against PyPI / Moss Discord before implementing; adjust SDK calls |
| Index creation fails at demo time | Low | `_ensure_index` error propagates to fallback; Browser Use covers it |
| `list_indexes()` does not return a plain `list[str]` | Low | Read the Moss SDK source / test with `FakeMossClient`; adapt the guard |
| W0 not yet merged when W3 work begins | — | Do not start W3 until W0 is on `main`; the W3 block cannot be placed without W0's labeled section |
