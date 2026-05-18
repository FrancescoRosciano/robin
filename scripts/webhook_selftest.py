"""Deterministic inbound proof — no phone needed. Svix-signs a synthetic
agent.message with the canonical secret and POSTs it through the public
tunnel, exactly as AgentPhone would. Expect HTTP 200 + NDJSON.

  docker compose run --rm -e PYTHONPATH=src \
    -e WH_SECRET=whsec_... robin python3 scripts/webhook_selftest.py
"""
import datetime
import json
import os
import sys

import httpx
from svix.webhooks import Webhook

secret = os.environ.get("WH_SECRET") or os.environ["AGENTPHONE_WEBHOOK_SECRET"]
public = os.environ["PUBLIC_BASE_URL"].rstrip("/")
url = f"{public}/webhook"

payload = json.dumps({
    "event": "agent.message",
    "channel": "voice",
    "data": {"transcript": "I need to cancel my gym membership"},
    "recentHistory": [],
})
msg_id = "msg_selftest_robin_1"
ts = datetime.datetime.now(tz=datetime.timezone.utc)
sig = Webhook(secret).sign(msg_id, ts, payload)
headers = {
    "svix-id": msg_id,
    "svix-timestamp": str(int(ts.timestamp())),
    "svix-signature": sig,
    "content-type": "application/json",
}

print(f"POST {url}")
print(f"secret head: {secret[:14]}…  payload: {payload}")
try:
    r = httpx.post(url, content=payload, headers=headers, timeout=90)
except Exception as exc:  # noqa: BLE001
    print(f"REQUEST EXC: {exc!r}")
    sys.exit(3)

print(f"\nHTTP {r.status_code}")
print("--- body (first 2000 chars) ---")
print(r.text[:2000])
if r.status_code == 200 and r.text.strip():
    print("\nRESULT=PASS (signature verified, loop produced output)")
    sys.exit(0)
if r.status_code == 401:
    print("\nRESULT=FAIL-401 (secret still mismatched)")
    sys.exit(2)
print(f"\nRESULT=FAIL-{r.status_code} (signature OK if not 401; inspect body/log)")
sys.exit(2)
