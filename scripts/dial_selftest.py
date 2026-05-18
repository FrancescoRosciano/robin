#!/usr/bin/env python3
"""Outbound-dial selftest — eyeball the EXACT POST /v1/calls payload.

Two modes:

  (default) FAKE:  Build the real place_negotiation_call tool against an
                   in-memory httpx fake (NO network, ever) and print the
                   exact JSON body that WOULD be sent to AgentPhone, with
                   phone numbers redacted to last-4. PASS/FAIL on the
                   request shape vs agentphone/agentphone-notes.md.

  --live-dry-run   Place ONE real outbound call to the receptionist
                   number from the context pack (the briefed teammate).
                   HARD-GUARDED: refuses unless env ROBIN_DIAL_LIVE=1.
                   This actually rings a phone — use only with the
                   teammate ready.

Usage (Docker — ThreatLocker blocks host Python):

  docker compose run --rm -e PYTHONPATH=src robin \
      python scripts/dial_selftest.py

  # real teammate dial (loud guard):
  docker compose run --rm -e PYTHONPATH=src \
      -e ROBIN_DIAL_LIVE=1 robin \
      python scripts/dial_selftest.py --live-dry-run
"""
import argparse
import asyncio
import json
import os
import sys

import httpx

from robin.agentphone_client import AgentPhoneClient
from robin.outbound import CallRegistry, make_place_negotiation_call

_FAKE_CALL_ID = "call_SELFTEST_FAKE"
_REQUIRED_BODY_KEYS = {"agentId", "toNumber", "initialGreeting",
                       "systemPrompt", "fromNumberId"}


def _redact_phone(value: str) -> str:
    """+15551230099 -> '***0099' (never print full numbers / PII)."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def _redact_body(body: dict) -> dict:
    out = dict(body)
    if "toNumber" in out:
        out["toNumber"] = _redact_phone(out["toNumber"])
    return out


# --------------------------------------------------------------------------
# FAKE mode
# --------------------------------------------------------------------------
class _CaptureTransport:
    def __init__(self) -> None:
        self.captured: httpx.Request | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calls" and request.method == "POST":
            self.captured = request
            return httpx.Response(200, json={"id": _FAKE_CALL_ID})
        if request.url.path.endswith("/transcript/stream"):
            return httpx.Response(
                200, text='event: ended\ndata: {"status":"completed"}\n\n',
                headers={"content-type": "text/event-stream"})
        return httpx.Response(404)


async def _run_fake() -> int:
    cap = _CaptureTransport()
    client = AgentPhoneClient(api_key="FAKE-KEY-NOT-REAL")
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(cap.handler),
        base_url="https://api.agentphone.ai/v1",
        headers={"Authorization": "Bearer FAKE-KEY-NOT-REAL"})

    tool = make_place_negotiation_call(
        client=client, registry=CallRegistry(),
        agent_id="agt_selftest",
        from_number_id="num_selftest",
        receptionist_to_number="+15550000002",
        outbound_system_prompt="OUTBOUND-PERSONA-AND-GOAL (selftest)")

    res = await tool(
        phone="415-776-2200", member_name="Demo User",
        citations=[{"citation": "FTC Negative Option Rule, 16 CFR 425",
                    "operative_quote": "Simple cancellation required.",
                    "source_url": "https://example.test/ftc"}])
    await asyncio.sleep(0.05)  # let the spawned capture task settle

    if cap.captured is None:
        print("FAIL: tool returned but NO POST /v1/calls was issued.")
        print("       -> this is the 'never actually dials' symptom.")
        return 1

    req = cap.captured
    body = json.loads(req.content)

    print("=== EXACT outbound request Robin produces (PII redacted) ===")
    print(f"  {req.method} {req.url}")
    auth = req.headers.get("authorization", "")
    print(f"  Authorization: {'Bearer <present>' if auth.startswith('Bearer ') else '<MISSING>'}")
    print("  body:")
    print(json.dumps(_redact_body(body), indent=2))
    print(f"  tool return: {res}")
    print()

    checks: list[tuple[str, bool]] = [
        ("method is POST", req.method == "POST"),
        ("path is /v1/calls", req.url.path == "/v1/calls"),
        ("url is api.agentphone.ai",
         req.url.host == "api.agentphone.ai"),
        ("Authorization: Bearer present",
         auth.startswith("Bearer ") and len(auth) > 7),
        ("body keys match agentphone-notes.md",
         set(body) == _REQUIRED_BODY_KEYS),
        ("dials receptionist sim (+1555…), not the displayed company #",
         body.get("toNumber") == "+15550000002"),
        ("systemPrompt is non-empty", bool(body.get("systemPrompt"))),
        ("initialGreeting names the member",
         "Demo User" in body.get("initialGreeting", "")),
        ("tool returns a call_id", res.get("call_id") == _FAKE_CALL_ID),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    print()
    print("RESULT:", "PASS — request shape matches agentphone-notes.md"
          if ok else "FAIL — see failed checks above")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# LIVE dry-run mode (real teammate dial) — hard guarded
# --------------------------------------------------------------------------
async def _run_live() -> int:
    if os.environ.get("ROBIN_DIAL_LIVE") != "1":
        print("REFUSING --live-dry-run.")
        print("This places a REAL phone call to the receptionist number")
        print("in the context pack (the briefed teammate). To proceed you")
        print("must explicitly set:  ROBIN_DIAL_LIVE=1")
        print("Default (no flag) runs the in-memory fake and never dials.")
        return 2

    # Imported lazily so FAKE mode never requires real settings/keys.
    from robin.config import load_settings
    from robin.context_pack import load_context_pack
    from robin.prompts import render_outbound_system_prompt

    settings = load_settings()
    pack_path = os.environ.get("CONTEXT_PACK_PATH", "context_pack.json")
    pack = load_context_pack(pack_path)

    print("*** LIVE DRY-RUN — this RINGS A REAL PHONE ***")
    print(f"  agent:    {settings.robin_agent_id}")
    print(f"  from:     {settings.from_number_id}")
    print(f"  dialing:  {_redact_phone(pack.receptionist_to_number)} "
          f"(receptionist teammate; NOT the real company)")
    print(f"  says #:   {_redact_phone(pack.target_display_number)} "
          f"(spoken only, never dialled)")
    print("  Ctrl-C now to abort. Continuing in ~3s...")
    await asyncio.sleep(3)

    client = AgentPhoneClient(api_key=settings.agentphone_api_key)
    tool = make_place_negotiation_call(
        client=client, registry=CallRegistry(),
        agent_id=settings.robin_agent_id,
        from_number_id=settings.from_number_id,
        receptionist_to_number=pack.receptionist_to_number,
        outbound_system_prompt=render_outbound_system_prompt(pack, []))
    try:
        res = await tool(phone=pack.target_display_number,
                         member_name=pack.caller_name, citations=[])
    except httpx.HTTPStatusError as exc:
        print(f"LIVE FAIL: AgentPhone returned HTTP "
              f"{exc.response.status_code}")
        print(f"  body: {exc.response.text[:300]}")
        return 1
    except (httpx.HTTPError, ValueError) as exc:
        print(f"LIVE FAIL: {type(exc).__name__}: {exc}")
        return 1

    print(f"LIVE OK: outbound call placed. call_id={res.get('call_id')}")
    print("  -> phone should be ringing the teammate now.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-dry-run", action="store_true",
        help="Place ONE real call to the receptionist teammate "
             "(requires env ROBIN_DIAL_LIVE=1).")
    args = parser.parse_args()
    if args.live_dry_run:
        return asyncio.run(_run_live())
    return asyncio.run(_run_fake())


if __name__ == "__main__":
    sys.exit(main())
