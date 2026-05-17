"""Idempotent AgentPhone provisioning for Robin + the simulated rep.

Run AFTER the tunnel is up and AGENTPHONE_API_KEY is exported. Endpoints
per agentphone/agentphone-notes.md. Prints the IDs to paste into .env.
Re-running with *_AGENT_ID / *_NUMBER_ID already set skips creation.
"""
import os
import sys

import httpx

BASE = os.environ.get("AGENTPHONE_BASE_URL", "https://api.agentphone.ai/v1")
KEY = os.environ.get("AGENTPHONE_API_KEY")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
RECEPTIONIST_PROMPT_PATH = "src/robin/fixtures/prompts/receptionist.txt"


def _client() -> httpx.Client:
    if not KEY:
        sys.exit("AGENTPHONE_API_KEY not set — export it before running.")
    return httpx.Client(base_url=BASE,
                        headers={"Authorization": f"Bearer {KEY}"},
                        timeout=30.0)


def _post(c: httpx.Client, path: str, body: dict) -> dict:
    r = c.post(path, json=body)
    r.raise_for_status()
    return r.json()


def _create_agent(c, name, system_prompt=None):
    body = {"name": name}
    if system_prompt is not None:
        body["systemPrompt"] = system_prompt
    a = _post(c, "/agents", body)
    return a.get("id") or a.get("agentId")


def _provision_number(c):
    n = _post(c, "/numbers", {})
    return n.get("id") or n.get("numberId")


def _bind(c, agent_id, number_id):
    _post(c, f"/agents/{agent_id}/numbers", {"numberId": number_id})


def main() -> None:
    if not PUBLIC_BASE_URL:
        sys.exit("PUBLIC_BASE_URL not set — bring up the tunnel first "
                 "(see scripts/tunnel.md).")
    c = _client()

    robin_agent = os.environ.get("ROBIN_AGENT_ID") or _create_agent(c, "Robin")
    robin_number = os.environ.get("FROM_NUMBER_ID") or _provision_number(c)
    _bind(c, robin_agent, robin_number)
    # agentphone-notes: webhook timeout is configurable 5–120s (default 30s).
    # Robin's Browser Use research turn can take ~60s, so 30s would time the
    # turn out mid-research. 120s plus the loop's keepalive interims (Plan 03)
    # keeps the turn alive. Cross-reference Plan 03's keepalive implementation.
    _post(c, "/webhooks", {"url": f"{PUBLIC_BASE_URL}/webhook", "timeout": 120})

    rep_prompt = open(RECEPTIONIST_PROMPT_PATH, encoding="utf-8").read()
    rep_agent = os.environ.get("RECEPTIONIST_AGENT_ID") or _create_agent(
        c, "24HF Receptionist (AI simulation)", system_prompt=rep_prompt)
    rep_number = os.environ.get("RECEPTIONIST_NUMBER_ID") or _provision_number(c)
    _bind(c, rep_agent, rep_number)

    print("\n# paste into .env  (gitignored — never commit)")
    print(f"ROBIN_AGENT_ID={robin_agent}")
    print(f"FROM_NUMBER_ID={robin_number}")
    print(f"RECEPTIONIST_AGENT_ID={rep_agent}")
    print(f"RECEPTIONIST_NUMBER_ID={rep_number}")
    print("# Also set RECEPTIONIST_TO_NUMBER to the E.164 of the rep "
          "number above (from the AgentPhone dashboard).")


if __name__ == "__main__":
    main()
