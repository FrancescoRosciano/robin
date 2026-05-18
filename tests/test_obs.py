"""Unit tests for robin.obs — structured single-line event logging.

Isolation: each test installs its own handler on the "uvicorn.error"
logger and removes it in a finally, so tests never leak handlers or
depend on pytest's root-logger propagation config.
"""
import logging

import pytest

from robin.obs import log_event, redact, timed

_LOGGER_NAME = "uvicorn.error"


class _Capture:
    """Context manager: capture records emitted on the obs logger."""

    def __init__(self) -> None:
        self.records: list[logging.LogRecord] = []
        self._logger = logging.getLogger(_LOGGER_NAME)
        self._handler = logging.Handler()
        self._handler.emit = self.records.append  # type: ignore[method-assign]
        self._prev_level = self._logger.level

    def __enter__(self) -> "_Capture":
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.INFO)
        return self

    def __exit__(self, *exc) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prev_level)

    @property
    def lines(self) -> list[str]:
        return [r.getMessage() for r in self.records]


# --------------------------------------------------------------------------
# log_event: line shape
# --------------------------------------------------------------------------


def test_emits_exactly_one_line_with_event_prefix():
    with _Capture() as cap:
        log_event("dial_start", call_id="c_123", tool="place_call")
    assert len(cap.lines) == 1
    line = cap.lines[0]
    assert "\n" not in line
    assert line.startswith("EVENT dial_start ")
    assert "call_id=c_123" in line
    assert "tool=place_call" in line


def test_event_with_no_fields_is_just_the_prefix():
    with _Capture() as cap:
        log_event("loop_enter")
    assert cap.lines == ["EVENT loop_enter"]


def test_values_with_spaces_are_quoted_and_stay_single_line():
    with _Capture() as cap:
        log_event("note", msg="hello there world")
    line = cap.lines[0]
    assert "\n" not in line
    assert 'msg="hello there world"' in line


def test_logs_at_info_level():
    with _Capture() as cap:
        log_event("ping")
    assert cap.records[0].levelno == logging.INFO


# --------------------------------------------------------------------------
# redaction: phone numbers
# --------------------------------------------------------------------------


def test_phone_e164_redacted_to_last4():
    full = "+14155776200"
    out = redact(full)
    assert full not in out
    assert out.endswith("6200")
    # Contract: keep ONLY the last 4 digits; a leading "+" is preserved
    # but every other digit (incl. country code) is masked.
    assert out.startswith("+")
    assert out == "+*******6200"
    assert "415577" not in out


def test_phone_redacted_inside_a_field_value():
    with _Capture() as cap:
        log_event("dial", to="+14155776200")
    line = cap.lines[0]
    assert "+14155776200" not in line
    assert "6200" in line


def test_ten_plus_digit_run_redacted():
    out = redact("call 4155776200 now")
    assert "4155776200" not in out
    assert "6200" in out


def test_short_number_not_treated_as_phone():
    # 4 digits (e.g. a confirmation code length) must survive intact.
    assert redact("code 4124 ok") == "code 4124 ok"


def test_separator_run_with_fewer_than_10_digits_is_left_intact():
    # The phone regex can match a long separator run (e.g. "1-2-3-4-5-6":
    # 11 chars, 6 digits). Such a match has <10 real digits and must be
    # returned unchanged — not masked.
    assert redact("ref 1-2-3-4-5-6 end") == "ref 1-2-3-4-5-6 end"


# --------------------------------------------------------------------------
# redaction: secret-keyed fields are dropped
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["api_key", "API_KEY", "token", "Authorization", "secret",
     "client_secret", "password", "AGENTPHONE_TOKEN"],
)
def test_secret_keyed_fields_are_dropped(key):
    with _Capture() as cap:
        log_event("auth", **{key: "supersecret-value", "call_id": "c_1"})
    line = cap.lines[0]
    assert "supersecret-value" not in line
    assert key not in line
    assert "call_id=c_1" in line


def test_non_secret_keys_are_kept():
    with _Capture() as cap:
        log_event("ok", status="done", count=3)
    line = cap.lines[0]
    assert "status=done" in line
    assert "count=3" in line


# --------------------------------------------------------------------------
# redaction: long strings truncated
# --------------------------------------------------------------------------


def test_long_string_field_is_truncated_with_ellipsis():
    blob = "x" * 5000
    with _Capture() as cap:
        log_event("page", dom=blob)
    line = cap.lines[0]
    assert "\n" not in line
    assert len(line) < 500
    assert "…" in line
    assert blob not in line


def test_short_string_not_truncated():
    with _Capture() as cap:
        log_event("page", note="fine")
    assert "note=fine" in cap.lines[0]
    assert "…" not in cap.lines[0]


# --------------------------------------------------------------------------
# timed: success path emits ms
# --------------------------------------------------------------------------


def test_timed_emits_ms_field_on_success():
    with _Capture() as cap:
        with timed("dial", call_id="c_9"):
            pass
    assert len(cap.lines) == 1
    line = cap.lines[0]
    assert line.startswith("EVENT dial ")
    assert "call_id=c_9" in line
    assert "ms=" in line
    # ms value is an int.
    ms_token = next(t for t in line.split() if t.startswith("ms="))
    int(ms_token.split("=", 1)[1])


def test_timed_reraises_and_logs_error_without_swallowing():
    with _Capture() as cap:
        with pytest.raises(ValueError, match="boom"):
            with timed("dial", call_id="c_err"):
                raise ValueError("boom")
    assert len(cap.lines) == 1
    line = cap.lines[0]
    assert "status=error" in line
    assert "call_id=c_err" in line
    assert "ms=" in line
    assert "ValueError" in line
    assert "boom" in line


def test_timed_error_message_is_truncated():
    long_msg = "z" * 5000
    with _Capture() as cap:
        with pytest.raises(RuntimeError):
            with timed("dial"):
                raise RuntimeError(long_msg)
    line = cap.lines[0]
    assert "\n" not in line
    assert len(line) < 500
    assert long_msg not in line


def test_timed_does_not_emit_a_second_line_for_success():
    with _Capture() as cap:
        with timed("op"):
            log_event("inner")
    # one inner + one timed = exactly two, no duplicate timed line.
    assert len(cap.lines) == 2
    assert sum(1 for line in cap.lines if line.startswith("EVENT op ")) == 1


# --------------------------------------------------------------------------
# log_event: observability must never break the caller
# --------------------------------------------------------------------------


def test_log_event_swallows_logging_layer_failure(monkeypatch):
    import robin.obs as obs

    def _boom(*_a, **_k):
        raise RuntimeError("logger exploded")

    # First .info() (the event) raises; the defensive except must catch
    # it and not propagate — a broken log line cannot kill a call turn.
    monkeypatch.setattr(obs._log, "info", _boom)
    monkeypatch.setattr(obs._log, "exception", lambda *a, **k: None)
    obs.log_event("dial_start", call_id="c_1")  # must not raise
