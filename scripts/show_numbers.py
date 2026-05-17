"""Read-only: print the dialable +E.164 numbers for the provisioned IDs.

The docs do not document a numbers-list endpoint, so this probes the
conventional read routes (all GET — they create nothing) and scans the
JSON for phone-number-looking strings, so it does not depend on knowing
the exact field name. Run via:  ./scripts/provision.sh --numbers
"""
import os
import re
import sys

import httpx

BASE = os.environ.get("AGENTPHONE_BASE_URL", "https://api.agentphone.ai/v1")
KEY = os.environ.get("AGENTPHONE_API_KEY")
TIMEOUT = float(os.environ.get("AGENTPHONE_HTTP_TIMEOUT", "30"))

WANT = {  # env var -> human label
    "FROM_NUMBER_ID": "ROBIN number",
    "RECEPTIONIST_NUMBER_ID": "RECEPTIONIST number",
}
AGENTS = {
    "ROBIN_AGENT_ID": "ROBIN agent",
    "RECEPTIONIST_AGENT_ID": "RECEPTIONIST agent",
}
E164 = re.compile(r"^\+\d{7,15}$")


def _client():
    if not KEY:
        sys.exit("AGENTPHONE_API_KEY not set — run via ./scripts/provision.sh --numbers")
    return httpx.Client(base_url=BASE,
                        headers={"Authorization": f"Bearer {KEY}"},
                        timeout=TIMEOUT)


def _get(c, path):
    try:
        r = c.get(path)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), None
    except ValueError:
        return None, "non-JSON body"


def _find_phone(obj):
    """Recursively return the first E.164-looking string in a JSON blob."""
    if isinstance(obj, str):
        return obj if E164.match(obj.strip()) else None
    if isinstance(obj, dict):
        for v in obj.values():
            hit = _find_phone(v)
            if hit:
                return hit
    if isinstance(obj, list):
        for v in obj:
            hit = _find_phone(v)
            if hit:
                return hit
    return None


def _id_matches(obj, wanted_id):
    return isinstance(obj, dict) and wanted_id in (obj.get("id"), obj.get("numberId"))


def main():
    c = _client()
    found = {}  # label -> phone

    # 1) list endpoint (conventional; read-only — safe even if it 404s)
    listing, err = _get(c, "/numbers")
    items = []
    if isinstance(listing, list):
        items = listing
    elif isinstance(listing, dict):
        items = listing.get("data") or listing.get("numbers") or []
    for env_key, label in WANT.items():
        nid = os.environ.get(env_key)
        if not nid:
            continue
        for it in items:
            if _id_matches(it, nid):
                ph = _find_phone(it)
                if ph:
                    found[label] = ph

    # 2) per-id number fetch, then 3) per-id agent fetch (numbers may nest)
    for env_key, label in WANT.items():
        if label in found:
            continue
        nid = os.environ.get(env_key)
        if not nid:
            continue
        for path in (f"/numbers/{nid}",):
            blob, _ = _get(c, path)
            ph = _find_phone(blob) if blob is not None else None
            if ph:
                found[label] = ph
                break
    for env_key, label in AGENTS.items():
        num_label = label.replace("agent", "number")
        if num_label in found:
            continue
        aid = os.environ.get(env_key)
        if not aid:
            continue
        blob, _ = _get(c, f"/agents/{aid}")
        ph = _find_phone(blob) if blob is not None else None
        if ph:
            found[num_label] = ph

    print()
    if found:
        for label, phone in found.items():
            print(f"{label}: {phone}")
        if "RECEPTIONIST number" in found:
            print()
            print("Set this line in .env (then re-source it):")
            print(f"RECEPTIONIST_TO_NUMBER={found['RECEPTIONIST number']}")
    else:
        print("Could not read the numbers from the API "
              f"(list said: {err}).")
        print("The numbers exist (they were provisioned). Get them from the")
        print("AgentPhone web app: log in at agentphone.ai with the same")
        print("account the API key is from → the Numbers / Phone numbers")
        print("section → copy the +E.164 next to these IDs:")
        for env_key, label in WANT.items():
            print(f"  {label}: id={os.environ.get(env_key, '(missing)')}")


if __name__ == "__main__":
    main()
