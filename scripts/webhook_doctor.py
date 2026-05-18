"""Read-only webhook diagnostic. Lists AgentPhone webhook endpoints and
any signing secret the API exposes. No mutation. Run in Docker (loads
.env): docker compose run --rm -e PYTHONPATH=src robin python3 scripts/webhook_doctor.py
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

c = httpx.Client(base_url=BASE,
                 headers={"Authorization": f"Bearer {KEY}"}, timeout=30)


def show(label: str, method: str, path: str) -> None:
    try:
        r = c.request(method, path)
    except Exception as exc:  # noqa: BLE001 - diagnostic, surface everything
        print(f"\n### {label} {method} {path}\n  EXC: {exc!r}")
        return
    print(f"\n### {label}  {method} {path}  -> HTTP {r.status_code}")
    body = r.text
    try:
        body = json.dumps(r.json(), indent=2)
    except Exception:  # noqa: BLE001
        pass
    print(body[:4000])


print(f"BASE={BASE}")
print(f"PUBLIC_BASE_URL={PUBLIC}  (want endpoint url == {PUBLIC}/webhook)")
show("list-webhooks", "GET", "/webhooks")
show("list-webhook", "GET", "/webhook")
