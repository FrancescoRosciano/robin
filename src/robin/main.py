"""Composition root. Builds real adapters from validated settings and
exposes `app` for uvicorn. Fails fast if any secret is missing."""
import os

from browser_use_sdk.v3 import AsyncBrowserUse

from robin.agentphone_client import AgentPhoneClient
from robin.anthropic_adapter import AnthropicLLM
from robin.app import build_app
from robin.config import load_settings
from robin.context_pack import load_context_pack
from robin.extensions import ExtensionHooks
from robin.models import Citation
from robin.outbound import (CallRegistry, make_deliver_result,
                            make_place_negotiation_call)
from robin.prompts import (render_inbound_system_prompt,
                           render_outbound_system_prompt)

CONTEXT_PACK_PATH = os.environ.get("CONTEXT_PACK_PATH", "context_pack.json")
LAW_HTML_PATH = "src/robin/fixtures/law.html"

_settings = load_settings()                       # fail-fast on missing env
_pack = load_context_pack(CONTEXT_PACK_PATH)      # fail-fast on placeholders

_ap = AgentPhoneClient(api_key=_settings.agentphone_api_key)
# Default Haiku for voice latency (platform author's reference choice).
# ROBIN_MODEL overrides for rehearsal — fall back to Sonnet in one env
# var if Haiku underperforms the discovery/tool reasoning.
_llm = AnthropicLLM(
    api_key=_settings.anthropic_api_key,
    model=os.environ.get("ROBIN_MODEL", "claude-haiku-4-5-20251001"))
_browser = AsyncBrowserUse()                      # reads BROWSER_USE_API_KEY
_registry = CallRegistry()


async def _research(jurisdiction: str) -> dict:
    from robin.tools import research_cancellation_law
    return await research_cancellation_law(
        jurisdiction, browser=_browser,
        law_url=f"{_settings.public_base_url}/fixture/law.html",
        law_html_path=LAW_HTML_PATH)


def _authoritative_citations(model_citations: list[dict]) -> list[Citation]:
    """Integrity guard. The cited statutes MUST be the pre-vetted
    verbatim text, NEVER whatever the model echoed back through the tool
    arg — it drops the operative quote / source (renders as `"" ()`),
    and a wrong or empty statute at YC is fatal. Source them server-side
    from the pre-vetted fixture; only fall back to the model's arg if
    the fixture is unreadable."""
    from robin.tools import _parse_law_html
    parsed: list[dict] = []
    try:
        with open(LAW_HTML_PATH, encoding="utf-8") as fh:
            parsed = _parse_law_html(fh.read())
    except OSError:
        parsed = []
    source = parsed or model_citations or []
    return [Citation(c.get("citation", ""), c.get("operative_quote", ""),
                     c.get("source_url", "")) for c in source]


async def _place(phone: str, member_name: str, citations: list[dict]) -> dict:
    cites = _authoritative_citations(citations)
    impl = make_place_negotiation_call(
        client=_ap, registry=_registry, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        receptionist_to_number=_settings.receptionist_to_number,
        outbound_system_prompt=render_outbound_system_prompt(_pack, cites))
    return await impl(phone=phone, member_name=member_name,
                      citations=citations)


_tool_impls = {
    "research_cancellation_law": _research,
    "place_negotiation_call": _place,
    "deliver_result": make_deliver_result(
        client=_ap, agent_id=_settings.robin_agent_id,
        from_number_id=_settings.from_number_id,
        callback_number=_pack.callback_number),
}

# --- sponsor extension wiring (one delimited sub-block per branch) ---
_hooks = ExtensionHooks()
# >>> W1 supermemory wiring <<<   (added on feat/supermemory-recall)
# >>> W2 agentmail wiring   <<<   (added on feat/agentmail-closeloop)
# >>> W3 moss wiring        <<<   (added on feat/moss-statute-search)
# >>> W4 dashboard wiring <<<
if os.environ.get("ROBIN_DASHBOARD_ENHANCED") == "1":
    import pathlib as _pathlib

    from robin.broadcast import TurnBroadcaster
    from robin.event_bus import EventBus

    _bus = EventBus()
    _broadcaster = TurnBroadcaster()           # transcript fan-out target
    _dashboard_html = _pathlib.Path(
        "src/robin/fixtures/stage_dashboard.html").read_text(encoding="utf-8")

    async def _citation_pub(call_id, out_dict):      # on_research hook
        try:
            await _bus.publish_event("citation", {
                "call_id": call_id,
                "citations": out_dict.get("citations", []),
            })
        except Exception:
            pass  # hook must never raise

    async def _mail_pub(call_id, payload):           # on_outcome hook
        try:
            await _bus.publish_event("mail_draft", {
                "call_id": call_id,
                "summary": payload.get("summary", ""),
                "confirmation": payload.get("confirmation"),
                "channel": payload.get("channel"),
            })
        except Exception:
            pass  # hook must never raise

    _hooks = ExtensionHooks(
        prompt_enrichers=_hooks.prompt_enrichers,
        on_research=_hooks.on_research + (_citation_pub,),
        on_outcome=_hooks.on_outcome + (_mail_pub,),
        event_bus=_bus,
    )

    # --- OPTIONAL transcript-feed tier (collapse-cut #1; see collapse ladder) ---
    # The citation + mail panels above are pure-W0-event_bus and need NO
    # broadcaster. The TRANSCRIPT panel needs TurnBroadcaster fed by the
    # outbound call's on_turn. main.py:_place builds make_place_negotiation_call
    # WITHOUT on_turn, so feed it by overriding the place tool impl here —
    # same pattern as W3's research override.
    # make_place_negotiation_call already accepts on_turn (outbound.py:59-63).
    from robin.outbound import make_place_negotiation_call as _mk_place
    from robin.prompts import render_outbound_system_prompt as _ros

    async def _place_with_turns(phone, member_name, citations):
        _cites = _authoritative_citations(citations)
        _impl = _mk_place(
            client=_ap, registry=_registry,
            agent_id=_settings.robin_agent_id,
            from_number_id=_settings.from_number_id,
            receptionist_to_number=_settings.receptionist_to_number,
            outbound_system_prompt=_ros(_pack, _cites),
            on_turn=_broadcaster.publish)
        return await _impl(phone=phone, member_name=member_name,
                           citations=citations)

    _tool_impls["place_negotiation_call"] = _place_with_turns
    # --- end optional transcript-feed tier ---
# >>> end W4 dashboard wiring <<<
# --- end sponsor extension wiring ---

app = build_app(
    secret=_settings.agentphone_webhook_secret,
    law_html_path=LAW_HTML_PATH, llm=_llm, tool_impls=_tool_impls,
    system_prompt=render_inbound_system_prompt(_pack),
    hooks=_hooks)

# >>> W4 stage mount <<<
if os.environ.get("ROBIN_DASHBOARD_ENHANCED") == "1":
    from robin.stage import make_stage_router
    app.include_router(make_stage_router(
        _broadcaster, event_bus=_bus, stage_html=_dashboard_html))
# >>> end W4 stage mount <<<
