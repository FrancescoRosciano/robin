"""Load and validate the local context pack. Fail fast — never on stage."""
import json
import re
from robin.models import ContextPack

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_PHONE_FIELDS = ("callback_number", "receptionist_to_number")
_FIELDS = (
    "caller_name", "callback_number", "target_name", "target_display_number",
    "receptionist_to_number", "jurisdiction", "win_goal", "fallback_goal",
)


class ContextPackError(ValueError):
    """Raised on a missing/malformed/placeholder-bearing context pack."""


def load_context_pack(path: str) -> ContextPack:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError as e:
        raise ContextPackError(f"context pack not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ContextPackError(f"context pack is not valid JSON: {path}") from e

    if not isinstance(raw, dict):
        raise ContextPackError(f"context pack must be a JSON object: {path}")

    for key in _FIELDS:
        if key not in raw:
            raise ContextPackError(f"missing field: {key}")
        val = raw[key]
        if not isinstance(val, str):
            raise ContextPackError(f"field must be a string: {key}")
        if val == "":
            raise ContextPackError(f"empty field: {key}")
        if "{{" in val or "}}" in val:
            raise ContextPackError(f"unfilled placeholder in {key}")

    for key in _PHONE_FIELDS:
        if not _E164.match(raw[key]):
            raise ContextPackError(
                f"{key} must be E.164 (e.g. +15550000001), got: {raw[key]!r}"
            )

    return ContextPack(**{k: raw[k] for k in _FIELDS})
