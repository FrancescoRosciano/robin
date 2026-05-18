"""Force the single AgentPhone webhook to point at the current tunnel and
print the canonical signing secret from the API (authoritative — the
dashboard display rotates and cannot be trusted).

Run in Docker (loads .env):
  docker compose run --rm -e PYTHONPATH=src robin python3 scripts/webhook_fix.py

Emits two machine-readable lines at the end:
  FINAL_URL=<url>
  FINAL_SECRET=<whsec_...>
"""
import json
import os
import sys

import httpx

BASE = os.environ.get("AGENTPHONE_BASE_URL", "https://api.agentphone.ai/v1")
KEY = os.environ.get("AGENTPHONE_API_KEY")
PUBLIC = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

if not KEY:
    sys.exit("AGENTPHONE_API_KEY not set")
if not PUBLIC:
    sys.exit("PUBLIC_BASE_URL not set")

WANT = f"{PUBLIC}/webhook"
c = httpx.Client(base_url=BASE,
                 headers={"Authorization": f"Bearer {KEY}"}, timeout=30)


def dump(label, r):
    try:
        body = json.dumps(r.json(), indent=2)
    except Exception:  # noqa: BLE001
        body = r.text
    print(f"\n### {label} -> HTTP {r.status_code}\n{body[:3000]}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


def get_one():
    r = c.get("/webhooks")
    j = dump("GET /webhooks", r)
    return j if isinstance(j, dict) else {}


print(f"WANT endpoint url = {WANT}")
cur = get_one()

if cur.get("url") != WANT:
    print(f"\n... url is {cur.get('url')!r}; forcing to tunnel via POST")
    r = c.post("/webhooks", json={"url": WANT, "timeout": 120})
    dump("POST /webhooks {url:tunnel}", r)
    cur = get_one()

    if cur.get("url") != WANT and cur.get("id"):
        wid = cur["id"]
        print(f"\n... still not tunnel; DELETE /webhooks/{wid} then recreate")
        for path in (f"/webhooks/{wid}", "/webhooks"):
            try:
                dump(f"DELETE {path}", c.delete(path))
            except Exception as exc:  # noqa: BLE001
                print(f"  DELETE {path} EXC {exc!r}")
        r = c.post("/webhooks", json={"url": WANT, "timeout": 120})
        dump("POST /webhooks (recreate)", r)
        cur = get_one()

print("\n================ RESULT ================")
print(f"FINAL_URL={cur.get('url')}")
print(f"FINAL_SECRET={cur.get('secret')}")
ok = cur.get("url") == WANT and str(cur.get("secret", "")).startswith("whsec_")
print(f"FINAL_OK={'yes' if ok else 'NO'}")
sys.exit(0 if ok else 2)
