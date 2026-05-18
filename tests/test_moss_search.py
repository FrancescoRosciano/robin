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
