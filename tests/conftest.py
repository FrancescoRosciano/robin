"""Shared pytest fixtures.

Robin's per-call session memory (``robin.session``) is a single-process,
module-level singleton by design. Many tests exercise the webhook/loop
path that now reads and writes it, so without isolation one test's
recorded research/approval/dial state leaks into the next (e.g. a
non-empty ``summary_for_prompt`` getting injected into a later test's
system prompt). Reset it around every test.
"""
import pytest

from robin import session


@pytest.fixture(autouse=True)
def _reset_session() -> None:
    session.reset()
    yield
    session.reset()
