#!/usr/bin/env python3
"""Validate Robin's .env without exposing secret values.

Run AFTER `cp .env.example .env` and filling it in:

    python scripts/validate_env.py            # validates ./.env
    python scripts/validate_env.py path/to/.env

Exit code 0 = ready to run. Exit code 1 = something missing/malformed.
Secret values are never printed — only var name, status, and a redacted
hint (length / safe prefix).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

PLACEHOLDER_TOKENS = (
    "replace_me",
    "replace",
    "changeme",
    "your_",
    "xxx",
    "<",
    "todo",
)

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


@dataclass(frozen=True)
class Rule:
    name: str
    required: bool
    check: Optional[Callable[[str], Optional[str]]]
    note: str


def _looks_placeholder(value: str) -> bool:
    low = value.strip().lower()
    return any(tok in low for tok in PLACEHOLDER_TOKENS)


def _prefix(value: str, expected: str) -> Optional[str]:
    return None if value.startswith(expected) else f"must start with '{expected}'"


def _e164(value: str) -> Optional[str]:
    return None if E164.match(value) else "must be E.164, e.g. +15551234567"


def _https_no_slash(value: str) -> Optional[str]:
    if not value.startswith("https://"):
        return "must start with https://"
    if "localhost" in value or "127.0.0.1" in value:
        return "must be a PUBLIC https URL, not localhost"
    if value.endswith("/"):
        return "remove the trailing '/' (webhook path is appended)"
    return None


RULES: tuple[Rule, ...] = (
    Rule("AGENTPHONE_API_KEY", True, None, "from agentphone.ai"),
    Rule("ANTHROPIC_API_KEY", True, lambda v: _prefix(v, "sk-ant-"),
         "from console.anthropic.com"),
    Rule("BROWSER_USE_API_KEY", True, None, "from cloud.browser-use.com"),
    Rule("AGENTPHONE_WEBHOOK_SECRET", True, lambda v: _prefix(v, "whsec_"),
         "Signing Secret on the AgentPhone Webhooks page"),
    Rule("PUBLIC_URL", True, _https_no_slash,
         "your tunnel/host base; webhook = PUBLIC_URL + /webhook"),
    Rule("CALLBACK_NUMBER", True, _e164, "press-2 callback destination"),
    Rule("DEMO_TARGET_NUMBER", True, _e164,
         "the SIMULATED receptionist (your 2nd agent) — never the real company"),
    Rule("AGENTPHONE_AGENT_ID", False, lambda v: _prefix(v, "agt_"),
         "blank until the provisioning script runs, then paste agt_…"),
    Rule("AGENTPHONE_FROM_NUMBER_ID", False, lambda v: _prefix(v, "num_"),
         "blank until the provisioning script runs, then paste num_…"),
    Rule("AGENTPHONE_BASE_URL", False, lambda v: _prefix(v, "https://"),
         "optional; defaults to https://api.agentphone.ai/v1"),
    Rule("ANTHROPIC_MODEL", False, None, "optional; defaults to a Sonnet id"),
    Rule("PORT", False,
         lambda v: None if v.isdigit() else "must be an integer",
         "optional; defaults to 8000"),
)


def parse_env(path: Path) -> dict[str, str]:
    """Minimal stdlib .env parser (no dependency needed pre-install)."""
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        out[key.strip()] = val
    return out


def hint(value: str) -> str:
    if value.startswith(("https://", "http://", "agt_", "num_", "+")):
        head = value.split("/")[2] if value.startswith("http") else value[:6]
        return f"({head}…, len={len(value)})"
    return f"(len={len(value)})"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env")
    if not target.exists():
        print(f"FAIL  {target} does not exist — run `cp .env.example .env` first")
        return 1

    values = parse_env(target)
    errors = 0
    warnings = 0

    for rule in RULES:
        present = rule.name in values and values[rule.name].strip() != ""
        if not present:
            if rule.required:
                print(f"FAIL  {rule.name:<26} missing/empty — {rule.note}")
                errors += 1
            else:
                print(f"WARN  {rule.name:<26} empty — {rule.note}")
                warnings += 1
            continue

        value = values[rule.name].strip()

        if _looks_placeholder(value):
            print(f"FAIL  {rule.name:<26} still a placeholder — {rule.note}")
            errors += 1
            continue

        problem = rule.check(value) if rule.check else None
        if problem:
            severity = "FAIL" if rule.required else "WARN"
            print(f"{severity}  {rule.name:<26} {problem}")
            errors += rule.required
            warnings += not rule.required
            continue

        print(f"OK    {rule.name:<26} set {hint(value)}")

    print()
    if errors:
        print(f"NOT READY — {errors} error(s), {warnings} warning(s). "
              "Fix the FAILs and re-run.")
        return 1
    if warnings:
        print(f"READY for first inbound call — {warnings} warning(s). "
              "The two provisioning IDs are filled after the setup script.")
        return 0
    print("READY — all variables present and well-formed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
