from robin.tools import TOOL_SCHEMAS, research_cancellation_law
from tests.fakes import FakeBrowser

LAW_OUTPUT = (
    'citation: FTC Negative Option Rule | quote: Cancellation must be at '
    'least as simple as enrollment. | source: https://h/law.html\n'
    'citation: Cal. Civ. Code 1812.x | quote: The buyer may cancel. | '
    'source: https://h/law.html'
)


def test_tool_schemas_are_the_three_named_tools():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {
        "research_cancellation_law", "place_negotiation_call", "deliver_result"
    }


async def test_research_parses_browser_output_ok():
    fb = FakeBrowser(LAW_OUTPUT)
    res = await research_cancellation_law(
        "US-CA", browser=fb, law_url="https://h/law.html"
    )
    assert res["status"] == "OK"
    assert res["citations"][0]["citation"].startswith("FTC")
    assert "law.html" in fb.calls[0]


async def test_research_timeout_returns_failed_not_raise():
    fb = FakeBrowser("", raise_exc=TimeoutError("slow"))
    res = await research_cancellation_law(
        "US-CA", browser=fb, law_url="https://h/law.html"
    )
    assert res["status"] == "FAILED"
    assert res["citations"] == []


async def test_research_falls_back_to_local_fixture(tmp_path):
    law = tmp_path / "law.html"
    law.write_text('<h2 class="citation">FTC X</h2>'
                   '<p class="operative-quote">Be simple.</p>'
                   '<p class="source">http://h</p>')
    fb = FakeBrowser("", raise_exc=RuntimeError("BU down"))
    res = await research_cancellation_law(
        "US-CA", browser=fb, law_url="http://h/law.html",
        law_html_path=str(law))
    assert res["status"] == "OK"
    assert res["citations"][0]["citation"] == "FTC X"
    assert res.get("source") == "local-fixture-fallback"
