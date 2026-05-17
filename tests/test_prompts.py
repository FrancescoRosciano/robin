# tests/test_prompts.py
import pytest
from robin.models import ContextPack, Citation
from robin.prompts import render, PromptRenderError

PACK = ContextPack(
    caller_name="Demo User", callback_number="+15550000001",
    target_name="24 Hour Fitness", target_display_number="415-776-2200",
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
    assert "Demo User" in out and "24 Hour Fitness" in out
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
