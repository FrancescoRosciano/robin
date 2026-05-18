"""tests/test_extensions.py — W0 extension seam unit tests.

Each test is self-contained: no live telephony, no real SDKs, no env vars.
All async tests use pytest-asyncio (already in requirements-dev.txt).
"""
import asyncio
import pytest

# These imports will fail until the seam is implemented (that's the RED step).
from robin.extensions import ExtensionHooks, PromptEnricher, ResearchHook, OutcomeHook
from robin.loop import run_turn, _record_session
from robin.app import build_app
from robin.stage import make_stage_router
from tests.fakes import FakeLLM


def _make_msg(texts: list[str], stop_reason: str):
    class _M:
        content = [{"type": "text", "text": t} for t in texts]
    _M.stop_reason = stop_reason
    return _M()
