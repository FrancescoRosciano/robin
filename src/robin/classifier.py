"""Classify an outbound transcript into exactly DONE/NEEDS_APPROVAL/BLOCKED."""
import re
from robin.models import Outcome, OutcomeStatus

_CONFIRMATION = re.compile(r"\b24HF-\d{4}\b")
_APPROVAL_PHRASES = (
    "one-time code", "verification code", "security question",
    "verify your identity", "text you a code",
)
_OTP_WORD = re.compile(r"\botp\b", re.IGNORECASE)


def _last_non_empty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:200]
    return ""


def classify_transcript(transcript: str) -> Outcome:
    lower = transcript.lower()
    conf = _CONFIRMATION.search(transcript)

    if conf and "refund" in lower:
        return Outcome(status=OutcomeStatus.DONE, confirmation=conf.group(0),
                       detail="cancellation confirmed with last-month refund")

    for phrase in _APPROVAL_PHRASES:
        if phrase in lower:
            return Outcome(status=OutcomeStatus.NEEDS_APPROVAL, confirmation=None,
                           detail=f"verification gate: {phrase}")
    if _OTP_WORD.search(transcript):
        return Outcome(status=OutcomeStatus.NEEDS_APPROVAL, confirmation=None,
                       detail="verification gate: OTP")

    return Outcome(status=OutcomeStatus.BLOCKED, confirmation=None,
                   detail=_last_non_empty_line(transcript) or "no outcome reached")
