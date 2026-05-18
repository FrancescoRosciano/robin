from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ContextPack:
    caller_name: str
    callback_number: str          # E.164, synthetic +1555... in tests/demo
    target_name: str              # "24 Hour Gym"
    target_display_number: str    # "415-776-2200" — what Robin SAYS
    receptionist_to_number: str   # E.164 Robin actually DIALS (the simulation)
    jurisdiction: str             # "US-CA"
    win_goal: str
    fallback_goal: str
    email: str = ""          # W2: optional caller email; "" = skip send


@dataclass(frozen=True)
class Citation:
    citation: str                 # e.g. "FTC Negative Option Rule, 16 CFR Part 425"
    operative_quote: str          # one verbatim operative sentence
    source_url: str


class OutcomeStatus(str, Enum):
    DONE = "DONE"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Outcome:
    status: OutcomeStatus
    confirmation: str | None      # "24HF-4471" when DONE, else None
    detail: str                   # human summary / why blocked
