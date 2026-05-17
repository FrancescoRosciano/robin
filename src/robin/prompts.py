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
