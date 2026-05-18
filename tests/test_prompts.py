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


# ---------------------------------------------------------------------------
# New gap coverage
# ---------------------------------------------------------------------------

def test_render_outbound_system_prompt_no_unfilled_slots():
    """render_outbound_system_prompt must not leave any {{slot}} in the output (covers line 56)."""
    from robin.prompts import render_outbound_system_prompt
    from robin.context_pack import load_context_pack

    pack = load_context_pack("tests/fixtures/context_pack.valid.json")
    cites = [
        Citation(
            citation="Cal. Civ. Code §1234",
            operative_quote="operative quote here",
            source_url="https://example.test/law",
        )
    ]
    result = render_outbound_system_prompt(pack, cites)

    assert "{{" not in result, f"Unfilled slot found in outbound prompt: {result[:300]}"
    assert "}}" not in result


def test_render_outbound_citation_renders_verbatim():
    """Each citation must appear with exact formatting: index. name — "quote" (url)."""
    from robin.prompts import render_outbound_system_prompt
    from robin.context_pack import load_context_pack

    pack = load_context_pack("tests/fixtures/context_pack.valid.json")
    cites = [
        Citation(
            citation="Cal. Civ. Code §1234",
            operative_quote="operative quote here",
            source_url="https://example.test/law",
        )
    ]
    result = render_outbound_system_prompt(pack, cites)

    expected_line = '1. Cal. Civ. Code §1234 — "operative quote here" (https://example.test/law)'
    assert expected_line in result, (
        f"Citation not rendered verbatim.\nExpected: {expected_line!r}\nGot excerpt: {result[:600]}"
    )


def test_render_outbound_contains_pack_values():
    """The rendered outbound prompt must reflect target name and jurisdiction from the pack."""
    from robin.prompts import render_outbound_system_prompt
    from robin.context_pack import load_context_pack

    pack = load_context_pack("tests/fixtures/context_pack.valid.json")
    cites = [
        Citation(
            citation="FTC Rule",
            operative_quote="Cancellation must be simple.",
            source_url="https://example.test/ftc",
        )
    ]
    result = render_outbound_system_prompt(pack, cites)

    assert pack.target_name in result
    assert pack.caller_name in result


def test_render_outbound_unfilled_slot_raises():
    """If the outbound template somehow still has a slot after substitution, raise PromptRenderError."""
    # Use the lower-level render() with a stray slot to exercise the guard path.
    with pytest.raises(PromptRenderError):
        render("Hello {{caller_name}} — also {{unknown_slot}}", PACK, CITES)
