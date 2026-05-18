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

    client is None or ROBIN_MEMORY_ENABLED != "1" => no-op returning "".
    """
    async def _enricher(call_id: str | None) -> str:
        if client is None or os.environ.get("ROBIN_MEMORY_ENABLED") != "1":
            return ""
        return await _fetch_history(client, tag)

    return _enricher


def make_persist_outcome_hook(client, tag: str) -> OutcomeHook:
    """Return an outcome hook that fire-and-forgets a persist task.

    client is None or ROBIN_MEMORY_ENABLED != "1" => no-op returning None.
    """
    async def _hook(call_id: str | None, payload: dict) -> None:
        if client is None or os.environ.get("ROBIN_MEMORY_ENABLED") != "1":
            return None
        summary = str(payload.get("summary", ""))
        confirmation = payload.get("confirmation")
        asyncio.create_task(_persist(client, tag, summary, confirmation))
        return None

    return _hook
