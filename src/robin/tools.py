"""Anthropic tool schemas + the Browser Use research tool."""
import asyncio
import os
import re

RESEARCH_TIMEOUT_S = 60

TOOL_SCHEMAS = [
    {
        "name": "research_cancellation_law",
        "description": "Fetch the pre-vetted cancellation-law page and "
                       "extract the governing citations for a jurisdiction.",
        "input_schema": {
            "type": "object",
            "properties": {"jurisdiction": {"type": "string"}},
            "required": ["jurisdiction"],
        },
    },
    {
        "name": "place_negotiation_call",
        "description": "Call the gym to cancel, using the cited laws.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "member_name": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["phone", "member_name", "citations"],
        },
    },
    {
        "name": "deliver_result",
        "description": "Deliver the outcome to the caller (callback or stay-on).",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": ["callback", "stay_on"]},
                "summary": {"type": "string"},
                "confirmation": {"type": ["string", "null"]},
            },
            "required": ["channel", "summary"],
        },
    },
]


def _parse_law(output: str) -> list[dict]:
    cites: list[dict] = []
    for line in output.splitlines():
        if "citation:" not in line:
            continue
        parts = {}
        for seg in line.split("|"):
            if ":" in seg:
                k, _, v = seg.partition(":")
                parts[k.strip().lower()] = v.strip()
        if parts.get("citation") and parts.get("quote"):
            cites.append({
                "citation": parts["citation"],
                "operative_quote": parts["quote"],
                "source_url": parts.get("source", ""),
            })
    return cites


def _parse_law_html(html: str) -> list[dict]:
    cites = re.findall(r'class="citation"[^>]*>(.*?)<', html, re.S)
    quotes = re.findall(r'class="operative-quote"[^>]*>(.*?)<', html, re.S)
    srcs = re.findall(r'class="source"[^>]*>(.*?)<', html, re.S)
    out = []
    for i, c in enumerate(cites):
        out.append({"citation": c.strip(),
                    "operative_quote": quotes[i].strip() if i < len(quotes) else "",
                    "source_url": srcs[i].strip() if i < len(srcs) else ""})
    return out


async def research_cancellation_law(jurisdiction: str, *, browser,
                                    law_url: str,
                                    law_html_path: str | None = None) -> dict:
    task = (
        f"Go to {law_url}. It lists cancellation-law citations for "
        f"jurisdiction {jurisdiction}. For each citation block return one "
        f"line: 'citation: <h2 text> | quote: <operative sentence> | "
        f"source: <source url>'. Return only those lines."
    )
    try:
        result = await asyncio.wait_for(browser.run(task),
                                        timeout=RESEARCH_TIMEOUT_S)
    except (asyncio.TimeoutError, TimeoutError, Exception) as exc:  # noqa: BLE001
        # Browser Use failed/timed out. Deterministic safety net: parse the
        # SELF-HOSTED, pre-vetted fixture (identical statute text → integrity
        # preserved). Live-stage net only — never the recorded-backup path.
        if law_html_path and os.path.exists(law_html_path):
            with open(law_html_path, encoding="utf-8") as fh:
                cites = _parse_law_html(fh.read())
            if cites:
                return {"citations": cites, "status": "OK",
                        "source": "local-fixture-fallback"}
        return {"citations": [], "status": "FAILED", "error": str(exc)[:200]}
    cites = _parse_law(getattr(result, "output", "") or "")
    return {"citations": cites, "status": "OK" if cites else "FAILED"}
