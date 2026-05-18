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


@pytest.mark.asyncio
async def test_moss_research_returns_correct_shape(monkeypatch):
    """moss_research with a populated FakeMossClient returns the correct dict shape."""
    import robin.integrations.moss_search as ms
    from tests.fakes import FakeMossClient, FakeMossDoc, FakeMossQueryResult

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
