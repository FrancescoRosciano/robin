# tests/test_classifier.py
from robin.classifier import classify_transcript
from robin.models import OutcomeStatus

DONE_TX = ("agent: Fine — I'll cancel your subscription and refund your "
           "last month. Your confirmation number is 24HF-4471.")
OTP_TX = ("agent: To proceed I need to verify your identity — I'll text "
          "you a code now.")
BLOCKED_TX = ("agent: You can only cancel in person at your home club. "
              "I cannot help further.")


def test_done_requires_confirmation_and_refund():
    o = classify_transcript(DONE_TX)
    assert o.status == OutcomeStatus.DONE
    assert o.confirmation == "24HF-4471"


def test_confirmation_without_refund_is_not_done():
    o = classify_transcript("agent: Cancelled. Confirmation 24HF-4471.")
    assert o.status == OutcomeStatus.BLOCKED


def test_needs_approval_on_otp_gate():
    o = classify_transcript(OTP_TX)
    assert o.status == OutcomeStatus.NEEDS_APPROVAL
    assert "verify your identity" in o.detail or "text you a code" in o.detail


def test_blocked_default_with_last_line_detail():
    o = classify_transcript(BLOCKED_TX)
    assert o.status == OutcomeStatus.BLOCKED
    assert "cannot help further" in o.detail


def test_done_wins_even_if_otp_mentioned_earlier():
    tx = OTP_TX + "\n" + DONE_TX
    assert classify_transcript(tx).status == OutcomeStatus.DONE


def test_empty_transcript_is_blocked():
    o = classify_transcript("")
    assert o.status == OutcomeStatus.BLOCKED
