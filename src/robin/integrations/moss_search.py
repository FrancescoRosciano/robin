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
# Lookup tables (doc-id -> citation string / source URL)
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
# CORPUS TEXT CONSTANTS
#
# These three constants hold the COMPLETE verbatim operative text for each
# of the three locked statutes, copied directly from
# docs/legal-citations-verified.md (retrieved + user-signed-off 2026-05-17).
# NEVER paraphrase, NEVER add a fourth statute, NEVER fetch from the web.
# Each ends with its source URL so a Moss retrieval surfaces it verbatim.
# ---------------------------------------------------------------------------
_ROSCA_TEXT: str = (
    "15 U.S.C. § 8403 — Negative option marketing on the Internet "
    "(Section 4 of ROSCA). Operative sentence (verbatim, § 8403(3) — the "
    "unlawful-unless clause): \"It shall be unlawful for any person to "
    "charge or attempt to charge any consumer for any goods or services "
    "sold in a transaction effected on the Internet through a negative "
    "option feature … unless the person … provides simple mechanisms for "
    "a consumer to stop recurring charges from being placed on the "
    "consumer's credit card, debit card, bank account, or other financial "
    "account.\" The standalone verbatim text of paragraph (3) is: "
    "\"provides simple mechanisms for a consumer to stop recurring charges "
    "from being placed on the consumer's credit card, debit card, bank "
    "account, or other financial account.\" Source: "
    "https://www.law.cornell.edu/uscode/text/15/8403"
)
_CAL_CIV_TEXT: str = (
    "Cal. Civ. Code § 1812.85 (Title 2.5, Contracts for Health Studio "
    "Services). Operative sentence — cancellation right (verbatim, "
    "§ 1812.85(b)(1)): \"You, the buyer, may choose to cancel this "
    "agreement at any time prior to midnight of the fifth business day of "
    "the health studio after the date of this agreement, excluding Sundays "
    "and holidays.\" Operative sentence — refund (verbatim, "
    "§ 1812.85(b)(5)): \"All moneys paid pursuant to a contract for health "
    "studio services shall be refunded within 10 days after receipt of the "
    "notice of cancellation, except that payment shall be made for any "
    "health studio services received prior to cancellation.\" Source: "
    "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CIV&division=3.&title=2.5.&part=4."
)
_CAL_BPC_TEXT: str = (
    "Cal. Bus. & Prof. Code § 17602 (Article 9, Automatic Renewals, "
    "§ 17600 et seq.). Operative sentence (verbatim, § 17602(c)(1) — "
    "cancellation mechanism): \"A business that makes an automatic renewal "
    "offer or continuous service offer shall provide a toll-free telephone "
    "number, email address, a postal address if the seller directly bills "
    "the consumer, or it shall provide another cost-effective, timely, and "
    "easy-to-use mechanism for cancellation that shall be described in the "
    "acknowledgment specified in paragraph (3) of subdivision (a).\" "
    "Supporting (verbatim, § 17600 — legislative intent): \"It is the "
    "intent of the Legislature to end the practice of ongoing charging of "
    "consumer credit or debit cards or third party payment accounts "
    "without the consumers' explicit consent for ongoing shipments of a "
    "product or ongoing deliveries of service.\" Source: "
    "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=BPC&division=7.&title=&part=3.&chapter=1.&article=9."
)


# ---------------------------------------------------------------------------
# Corpus builder — VERBATIM text ONLY from docs/legal-citations-verified.md
# ---------------------------------------------------------------------------
def _build_corpus() -> list:  # list[DocumentInfo]
    """
    Returns exactly three DocumentInfo objects, one per locked statute.

    The text for each is the COMPLETE verbatim operative block for that
    statute copied from docs/legal-citations-verified.md (user-signed-off
    2026-05-17). The three locked statutes are:

      doc id "rosca-8403"       -> 15 U.S.C. § 8403 (ROSCA § 4)
      doc id "cal-civ-1812-85"  -> Cal. Civ. Code § 1812.85
      doc id "cal-bpc-17602"    -> Cal. Bus. & Prof. Code § 17602

    NEVER derive or paraphrase the text. NEVER add a fourth document.
    """
    from moss import DocumentInfo  # type: ignore
    return [
        DocumentInfo(id="rosca-8403",       text=_ROSCA_TEXT),
        DocumentInfo(id="cal-civ-1812-85",  text=_CAL_CIV_TEXT),
        DocumentInfo(id="cal-bpc-17602",    text=_CAL_BPC_TEXT),
    ]


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
    3. Query Moss; map result.docs to the required dict shape.
    4. If citations is empty: call Browser Use fallback (reason="empty").
    5. Return {"citations": citations, "status": "OK"}.
    6. On any exception from step 3 onward: fall back to Browser Use.
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
