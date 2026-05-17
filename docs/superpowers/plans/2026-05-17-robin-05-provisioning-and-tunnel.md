# Robin Plan 05 — Provisioning & Tunnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans. This is an **operational** plan (live API
> calls + a tunnel), not TDD. The *script code* (Task 1) is
> key-independent and can be written in Wave 1/2 in parallel; the *run*
> (Tasks 2–4) is gated on `AGENTPHONE_API_KEY` and is the first step of
> Wave 3. Execute Tasks 2–4 inline with the operator watching output.

**Goal:** Stand up the live telephony substrate: Robin's AgentPhone agent
+ number + webhook pointed at the public tunnel, **and** a second
"simulated 24 Hour Gym receptionist" agent loaded with Plan 02's
receptionist prompt — printing every ID needed for `.env`.

**Architecture:** One idempotent script `scripts/setup_agentphone.py`
(plain httpx against the documented API in `agentphone/agentphone-notes.md`)
+ a cloudflared HTTPS tunnel. A pre-decided fallback replaces the 2nd
agent with a teammate phone / TTS if provisioning stalls.

**Tech Stack:** Python 3.11+, httpx, cloudflared (or ngrok).

**Pre-decided fallback (design doc "Fixture fallback", DAY_PLAN
checkpoint):** if the 2nd agent is not answering as the receptionist
within **30 minutes** of starting Task 3 (decision point ≈ when Wave 3
begins), STOP and use a teammate's phone or a 6-line local TTS as the
receptionist at `RECEPTIONIST_TO_NUMBER`. Do not let fixture provisioning
eat the build.

---

## File Structure

- Create `scripts/setup_agentphone.py` — idempotent provisioning (Robin agent, number, webhook; receptionist agent + number).
- Create `scripts/tunnel.md` — exact tunnel command + the "do not restart" rule.
- Modify `.env` (gitignored; **never committed**) — populated from the script's printed IDs.

---

### Task 0: API contract lock (Wave-1 GATE — do not skip)

The provisioning endpoint shapes and field names this script uses —
`POST /v1/agents` `{"name":...}`, `POST /v1/numbers` `{}`,
bind `POST /v1/agents/{id}/numbers` `{"numberId":...}`,
`POST /v1/webhooks` `{"url":...,"timeout":...}` — are taken from the
Moss×AgentPhone cookbook and `agentphone/agentphone-notes.md` and are **NOT
confirmed against a live key**. They must be verified as part of the 5-fact
API-contract-lock tracked in Plan 00's GATE (`docs/superpowers/plans/2026-05-17-robin-00-execution-sequence.md`)
before this script is run.

`agentphone/agentphone-notes.md` marks HMAC signature verification and
inbound DTMF capture as OPEN (unconfirmed against live API). Field names
in provisioning endpoints carry the same uncertainty.

- [ ] **Step 1: Before running Tasks 2–4, confirm all five field names
  match the live API** (by reading `llms-full.txt` and the webhooks/events
  page, or by a throwaway test call with `curl` once the key is in hand).
  `scripts/setup_agentphone.py` is **the single place to adjust field
  names** if the live API differs. This is a hard gate — do NOT run the
  provisioning script until this check is complete.

---

### Task 1: Write the provisioning script (key-INDEPENDENT — Wave 1/2)

**Files:**
- Create: `scripts/setup_agentphone.py`

This task writes code only; it does not call the API. It can run in
parallel with Plans 01–04.

- [ ] **Step 1: Write `scripts/setup_agentphone.py`**

```python
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
```

- [ ] **Step 2: Syntax-check (no API call)**

Run: `python3 -m py_compile scripts/setup_agentphone.py && echo OK`
Expected: `OK`.

- [ ] **Step 3: Write `scripts/tunnel.md`**

```markdown
# Tunnel (HTTPS for the AgentPhone webhook)

cloudflared (preferred):
  cloudflared tunnel --url http://localhost:8000

Note the printed https URL → export it, do NOT restart the tunnel later
(prior-session lesson: ~12s cooldown + the webhook URL changes, breaking
the registered webhook). Keep this process running for the whole demo.

  export PUBLIC_BASE_URL="https://<the-printed-host>"

Fallback: `ngrok http 8000` → use the https forwarding URL.
Run the FastAPI server with:  uvicorn robin.app:app --port 8000
(see Plan 06 for the composed-app entrypoint).
```

- [ ] **Step 4: Commit**

```bash
git add scripts/setup_agentphone.py scripts/tunnel.md
git commit -m "feat: idempotent AgentPhone provisioning script + tunnel notes"
```

---

### Task 2: Bring up the tunnel (Wave 3 — needs nothing but the server import)

- [ ] **Step 1: Start the tunnel**

Run: `cloudflared tunnel --url http://localhost:8000`
Expected: a `https://<random>.trycloudflare.com` URL is printed. Leave
this process running (separate terminal). Do not restart it.

- [ ] **Step 2: Export the public URL**

Run: `export PUBLIC_BASE_URL="https://<the-printed-host>"`
Expected: `echo $PUBLIC_BASE_URL` shows the https URL (no trailing slash).

- [ ] **Step 3: Checkpoint**

Confirm `PUBLIC_BASE_URL` is set and the tunnel terminal still shows the
connection alive before continuing.

---

### Task 3: Provision (Wave 3 — gated on AGENTPHONE_API_KEY)

- [ ] **Step 1: Export the key**

Run: `export AGENTPHONE_API_KEY="<the key from agentphone.ai / Discord>"`
Expected: set (do not echo it; do not commit it).

- [ ] **Step 2: Run the provisioning script**

Run: `cd /Users/francescorosciano/docs/robin && python3 scripts/setup_agentphone.py`
Expected: prints `ROBIN_AGENT_ID=`, `FROM_NUMBER_ID=`,
`RECEPTIONIST_AGENT_ID=`, `RECEPTIONIST_NUMBER_ID=` lines with real IDs;
no HTTP error.

- [ ] **Step 3: Populate `.env` (gitignored — never commit)**

Add to `/Users/francescorosciano/docs/robin/.env` the printed IDs plus:
`ANTHROPIC_API_KEY`, `AGENTPHONE_API_KEY`, `AGENTPHONE_WEBHOOK_SECRET`
(from the AgentPhone webhook config), `BROWSER_USE_API_KEY`,
`PUBLIC_BASE_URL`, and `RECEPTIONIST_TO_NUMBER` (E.164 of the receptionist
number shown in the AgentPhone dashboard).

- [ ] **Step 4: Verify the recording add-on is enabled (demo GATE)**

`agentphone/agentphone-notes.md`: `GET /v1/calls/{id}` returns
`recordingUrl` and `recordingAvailable: true` **only if the recording
add-on is enabled on the account**. This gates the demo's "recording
visible in the dashboard" acceptance criterion.

Place one throwaway test call via the AgentPhone dashboard (or `curl`):

```bash
# After the call ends, substitute the real call_id:
curl -s -H "Authorization: Bearer $AGENTPHONE_API_KEY" \
  https://api.agentphone.ai/v1/calls/<call_id> | python3 -m json.tool
```

Expected output includes:
```json
{
  "recordingAvailable": true,
  "recordingUrl": "https://..."
}
```

If `recordingAvailable` is `false` or absent: **stop — go to the
AgentPhone dashboard → account / add-ons → enable the recording add-on —
then repeat this step.** Do not proceed to Task 4 until `recordingAvailable`
is confirmed `true`.

- [ ] **Step 5: Verify `.env` is gitignored**

Run: `git check-ignore .env && echo IGNORED`
Expected: `.env` then `IGNORED` (must NOT be trackable).

---

### Task 4: Verify the simulated receptionist answers (30-min fallback gate)

- [ ] **Step 1: Call the receptionist number by phone**

Dial the receptionist E.164 (`RECEPTIONIST_TO_NUMBER`) from any phone.
Expected: it answers in-character as the 24 Hour Gym receptionist and
opens with block #1 ("you can only cancel in person…").

- [ ] **Step 2: Decision gate (pre-decided — do not deliberate live)**

- Works → proceed to Plan 06.
- **Not answering correctly within 30 minutes of starting Task 3** →
  execute the fallback: set `RECEPTIONIST_TO_NUMBER` to a teammate's
  phone or a local 6-line TTS reading `src/robin/fixtures/prompts/receptionist.txt`.
  The rest of the pipeline is unchanged (Robin still "dials the number").
  Note the fallback in the run log; move on.

- [ ] **Step 3: Commit the run log (no secrets)**

```bash
git add docs/legal-citations-verified.md 2>/dev/null; true
git commit --allow-empty -m "chore: provisioning complete (IDs in gitignored .env)"
```

(The commit is bookkeeping; the IDs live only in `.env`, never in git.)

---

## Self-Review

- **Spec coverage:** Robin agent + number + webhook (agentphone-notes
  "Provisioning"); 2nd receptionist agent with Plan 02 prompt (design
  "Before You Code" #3 + "Simulated … Receptionist"); tunnel + the "do
  not restart" lesson (DAY_PLAN GATE); pre-decided fixture fallback
  (design "Fixture fallback" + DAY_PLAN checkpoint). Covered.
- **Placeholder scan:** the script is complete; endpoints match
  `agentphone/agentphone-notes.md` (`POST /v1/agents`, `/v1/numbers`,
  `/v1/agents/{id}/numbers`, `/v1/webhooks`). If a field name differs in
  the live API, that is the single place to adjust (operator watches
  output — this is why the strategy is executing-plans, not subagent).
- **Webhook timeout = 120s:** registered in `_post(c, "/webhooks", {...,
  "timeout": 120})`. Rationale: agentphone-notes states 30s default;
  Browser Use research can take ~60s; Plan 03 keepalive interims extend
  the turn, but 120s at the webhook layer is the backstop.
- **Recording add-on gate:** Task 3 Step 4 requires `GET /v1/calls/{id}`
  to return `recordingAvailable: true` before proceeding to Task 4. If
  false, the add-on must be enabled in the AgentPhone dashboard. This
  gates the demo's "recording visible in the dashboard" acceptance
  criterion (agentphone-notes "Recording").
- **Task 0 API-contract gate:** endpoint field names (`name`,
  `numberId`, `url`, `timeout`) are taken from the cookbook and are not
  live-key confirmed. Task 0 mandates verifying them against the live API
  (via `llms-full.txt`, the webhooks/events page, or a throwaway `curl`)
  as part of Plan 00's 5-fact GATE before the script is run.
- **Type consistency:** prints exactly the env var names Plan 03
  `config.load_settings()` requires (`ROBIN_AGENT_ID`, `FROM_NUMBER_ID`,
  `RECEPTIONIST_TO_NUMBER`, `PUBLIC_BASE_URL`) so Plan 06's startup guard
  passes. Reads `src/robin/fixtures/prompts/receptionist.txt` (Plan 02).
- **Security:** key/IDs only via env + gitignored `.env`; Task 3 Step 5
  hard-checks `.env` is ignored; nothing secret is printed back or
  committed.
