"""Structured single-line event logging for Robin.

The tool-call loop and the demo-critical outbound dial must be *visible*
in the running server log: which tool fired, with what (redacted) args,
success/failure, and latency. This module emits exactly ONE greppable
line per event to ``logging.getLogger("uvicorn.error")`` — the same
logger ``app.py`` uses, so events land in the live uvicorn server log.

Line format (chosen over JSON): ``EVENT <event> key=value key=value``.
Rationale: a human watching the stage run greps ``EVENT`` and reads it
at a glance with no tooling; values needing spaces are shell-style
quoted. It is always one physical line and never the full payload.

Security (robin-agentphone-security.md, MANDATORY): every value is run
through :func:`redact` before it is logged —

* phone numbers (E.164 or any run of 10+ digits) keep only the last 4
  (``+14155776200`` -> ``+*******6200`` — leading ``+`` preserved, all
  other digits incl. country code masked);
* any field whose key matches (case-insensitive) a secret name
  (api_key, token, secret, authorization, password) is dropped
  entirely — never blanked-in-place, never logged;
* every string value is truncated to ``_MAX_VALUE`` chars with an
  ellipsis, so a full page DOM or transcript can never reach the log.

No external deps, no async. ``timed`` re-raises — it never swallows;
the caller decides what to do with the failure.
"""
from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator

__all__ = ["log_event", "redact", "timed"]

_log = logging.getLogger("uvicorn.error")

_MAX_VALUE = 200  # truncate any rendered string field to this many chars.

# Substring match (case-insensitive): drop the whole field if its key
# contains any of these. Substrings catch client_secret, access_token,
# AGENTPHONE_TOKEN, x-api-key, etc. without an exhaustive list.
_SECRET_KEY_PARTS = (
    "api_key", "apikey", "token", "secret", "authorization", "password",
)

# A run of 10+ digits, optionally a leading "+", is treated as a phone
# number. 10 is the shortest real dialable length (NANP) — short codes
# like a 4-digit confirmation number stay intact.
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
_KEEP_LAST = 4


def _redact_phones(text: str) -> str:
    """Replace every phone-like run with a last-4-only mask."""

    def _mask(m: re.Match[str]) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            return raw
        plus = "+" if raw.lstrip().startswith("+") else ""
        last4 = digits[-_KEEP_LAST:]
        stars = "*" * (len(digits) - _KEEP_LAST)
        return f"{plus}{stars}{last4}"

    return _PHONE_RE.sub(_mask, text)


def redact(value: Any) -> str:
    """Render ``value`` to a single-line, PII-safe, length-capped string.

    Phone numbers are reduced to their last 4 digits and the result is
    truncated to ``_MAX_VALUE`` characters. Newlines/tabs are collapsed
    so the value can never break the one-line invariant.
    """
    text = str(value)
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = _redact_phones(text)
    if len(text) > _MAX_VALUE:
        text = text[:_MAX_VALUE] + "…"
    return text


def _is_secret_key(key: str) -> bool:
    low = key.lower()
    return any(part in low for part in _SECRET_KEY_PARTS)


def _render_value(value: Any) -> str:
    """Redact, then shell-style quote if the token would contain spaces."""
    rendered = redact(value)
    if rendered == "" or any(c in rendered for c in (" ", '"', "=")):
        escaped = rendered.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return rendered


def _format(event: str, fields: dict[str, Any]) -> str:
    parts = [f"EVENT {event}"]
    for key, value in fields.items():
        if value is None or _is_secret_key(key):
            continue
        parts.append(f"{key}={_render_value(value)}")
    return " ".join(parts)


def log_event(event: str, **fields: Any) -> None:
    """Emit exactly one redacted, single-line event to the server log.

    ``event`` is a short stable verb (``dial_start``, ``tool_ok`` …).
    ``fields`` are arbitrary key/values; secret-named keys are dropped,
    ``None`` values omitted, strings capped, phone numbers masked.
    Logging never raises out of here — observability must not break the
    call turn.
    """
    try:
        _log.info(_format(event, fields))
    except Exception:  # noqa: BLE001 - logging must never break the caller
        _log.exception("obs.log_event failed for event=%s", event)


@contextmanager
def timed(event: str, **fields: Any) -> Iterator[None]:
    """Time a block; log ``event`` once with an integer ``ms`` field.

    On success: ``EVENT <event> <fields> ms=<int>``.
    On exception: ``EVENT <event> <fields> ms=<int> status=error
    err=<Type: msg>`` (truncated), then the exception is **re-raised** —
    this context manager never swallows; the caller decides.
    """
    start = time.monotonic()
    try:
        yield
    except BaseException as exc:  # noqa: BLE001 - log then re-raise, never swallow
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log_event(event, **fields, ms=elapsed_ms, status="error",
                  err=f"{type(exc).__name__}: {exc}")
        raise
    else:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log_event(event, **fields, ms=elapsed_ms)
