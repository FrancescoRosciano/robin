# tests/test_models.py
import dataclasses
import pytest
from robin.models import ContextPack, Citation, Outcome, OutcomeStatus


def test_contextpack_is_frozen():
    p = ContextPack(
        caller_name="Demo User", callback_number="+15550000001",
        target_name="24 Hour Gym", target_display_number="415-776-2200",
        receptionist_to_number="+15550000002", jurisdiction="US-CA",
        win_goal="cancel + refund", fallback_goal="cancel only",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.caller_name = "x"


def test_outcome_status_values():
    assert OutcomeStatus.DONE == "DONE"
    assert {s.value for s in OutcomeStatus} == {"DONE", "NEEDS_APPROVAL", "BLOCKED"}


def test_outcome_and_citation_construct():
    c = Citation(citation="X", operative_quote="q", source_url="http://h/")
    o = Outcome(status=OutcomeStatus.DONE, confirmation="24HF-4471", detail="ok")
    assert c.citation == "X" and o.confirmation == "24HF-4471"
