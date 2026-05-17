# AgentPhone API — confirmed (webhook mode)

Source of truth (read these directly, don't trust paraphrase):
- Docs home: https://docs.agentphone.ai/welcome  (append `.md` to any page for clean markdown)
- Full LLM docs (read this whole): https://docs.agentphone.ai/welcome/llms-full.txt
- **Calls guide (THE page): https://docs.agentphone.ai/documentation/guides/calls**
- MCP server: https://docs.agentphone.ai/welcome/_mcp/server
- **PRIMARY reference — built by the AgentPhone founder, webhook mode**
  (shared by him directly):
  https://github.com/manav2modi/Personal-AI-Phone-Assistant
  Flask `server.py` (the webhook), `setup_agentphone.py` (provision
  agent/number/webhook), `requirements.txt`, `Procfile` +
  `gunicorn.conf.py` (deploy). Demonstrates: ndjson sentence streaming
  (TTS starts on sentence 1), smart tool routing in a Claude tool-call
  loop, call transfer, hangup detection, SMS. Mirror this pattern, write
  fresh — do NOT fork. (Note: README uses domain `agentphone.to`.)
- **Secondary reference (mirror, write fresh — don't fork):**
  Moss × AgentPhone cookbook —
  https://github.com/usemoss/moss/tree/main/examples/cookbook/agentphone
  Files: `server.py` (FastAPI entrypoint), `moss_agentphone.py` (tool
  schema + tool-call loop + **signature verification**), `create_index.py`,
  `test_integration.py`, `.env.example`, `pyproject.toml`, `railway.json`.
  It is a webhook server backing an AgentPhone number with a Claude
  tool-call loop. Voice only. This is the exact pattern Robin needs.

## Auth
- Base URL: `https://api.agentphone.ai/v1`
- Header: `Authorization: Bearer YOUR_API_KEY` (key from agentphone.ai — **need this; only blocker left**)

## Provisioning
- Create agent: `POST /v1/agents` `{"name":"Robin"}`
- Provision number: `POST /v1/numbers` `{}`  (SMS+voice, Twilio-backed)
- Bind number → agent: `POST /v1/agents/{agent_id}/numbers` `{"numberId":"NUMBER_ID"}`
- Register webhook: `POST /v1/webhooks` `{"url":"https://YOUR_PUBLIC_URL/webhook"}`

## Webhook mode (USE THIS — not hosted; per Francesco)
AgentPhone POSTs each turn to your server; YOUR backend runs the LLM.

**Request (AgentPhone → you):**
```json
{"event":"agent.message","channel":"voice",
 "data":{"transcript":"caller's spoken text"},
 "recentHistory":[{"direction":"inbound|outbound","content":"..."}]}
```
`channel`: `"voice"` (or `"sms"`). 30s default timeout (configurable
5–120s per webhook via `timeout`).

**Response (you → AgentPhone), JSON object; NDJSON streaming recommended:**
```
{"text":"Let me check that.","interim":true}\n
{"text":"Your order shipped yesterday."}\n
```
Fields: `text` (speak), `interim` (NDJSON, turn stays open), `hangup`
(bool, end after speaking), `action` (`"transfer"`|`"hangup"`), `digits`
(DTMF you SEND into an IVR, e.g. `"1"`, aliases `press_digit`/`dtmf`).

**Tool-calling loop** (Anthropic schema): stream interim ack → run tools
→ stream final. Example:
```python
def generate():
    yield json.dumps({"text":"Let me check on that.","interim":True})+"\n"
    answer = run_tool_call(transcript, history)
    yield json.dumps({"text":answer})+"\n"
```

## Outbound call (the dial-out)
```
POST /v1/calls
{"agentId":"agt_...","toNumber":"+1555...","initialGreeting":"Hi, this is Robin.",
 "systemPrompt":"<the outbound-leg persona/goal>","fromNumberId":"num_..."}
```
Agent's first number is caller ID unless `fromNumberId` overrides.
Web calls (browser): `POST /v1/calls/web` (`agentphone-web-sdk`).

## Live transcript streaming (SSE) — per Francesco's tip
```
GET /v1/calls/{call_id}/transcript/stream
```
Events: `connected` (callId, agentId, direction, from/to, status) →
`turn` (`role`:"user"|"agent", `content`, `createdAt`) → `ended`
(callId, status, endedAt, durationSeconds). `: heartbeat` every 15s.
→ feed `turn` content into the outcome classifier.

## Recording
`GET /v1/calls/{call_id}` → `recordingUrl`, `recordingAvailable: true`
(requires the recording add-on enabled). This is "recording in the
dashboard" for the demo.

## Webhook delivery & signature — RESOLVED: Svix (2026-05-17, from dashboard)

Confirmed from the AgentPhone Webhooks dashboard: webhook delivery is
**Svix**. The signing secret is the `whsec_…` value on the Webhooks
page (env `AGENTPHONE_WEBHOOK_SECRET`); the configured endpoint URL is a
Svix ingest URL until you point it at your tunnel.

**Do NOT hand-roll a plain HMAC-SHA256-hex check** (the earlier reference
shape in `.claude/rules/robin-agentphone-security.md` is wrong for Svix).
Svix scheme:
- Headers: `svix-id`, `svix-timestamp`, `svix-signature`.
- Signed content: `{svix-id}.{svix-timestamp}.{raw-body}`.
- Secret after `whsec_` is base64; HMAC-SHA256; base64 result;
  constant-time compare. `svix-signature` may carry multiple
  space-separated `v1,<sig>` values. Timestamp → replay window.

Implement with the official lib in `src/robin/signature.py` (Plan 00
isolates the change point here):
```python
from svix.webhooks import Webhook, WebhookVerificationError
wh = Webhook(os.environ["AGENTPHONE_WEBHOOK_SECRET"])
payload = wh.verify(raw_body, dict(request.headers))  # raises on bad sig
```
Add `svix` to Plan 03's `pyproject.toml`/`requirements.txt`. Still verify
the exact AgentPhone webhook **body** shape against the Moss
`moss_agentphone.py` + live docs (Contract-Lock item #1).

## OPEN — confirm before relying on it
- **Inbound caller DTMF capture (caller presses 1 / 2).** The Calls guide
  documents `digits` as something YOUR response SENDS (to navigate an
  IVR), and inbound speech arrives as `data.transcript`. How a caller's
  own keypress is delivered to the webhook is NOT confirmed in the Calls
  guide excerpt. Check `llms-full.txt` + the webhooks/events page + the
  Moss `moss_agentphone.py`. Fallback if no DTMF-in event: drive 1/2 by
  voice ("say 'one' to stay on, 'two' for a callback") — robust, same UX.
- **HMAC signature verification** — RESOLVED: it's Svix. See the
  "Webhook delivery & signature — RESOLVED: Svix" section above. No
  longer open.

## Sponsor hooks (bonus tracks, after core works)
- **Moss** for large-data semantic search (the cookbook is literally
  Moss×AgentPhone) — Moss track prize.
- **MPP / x402** payment support exists (Stripe track) — an agent that
  *transacts*, e.g. pays a fee mid-call. Only if core demo is solid.

## Robin spec → endpoints
- Inbound discovery dialogue → webhook `agent.message` + tool-call loop,
  NDJSON streaming.
- "Dial out on my behalf" → `POST /v1/calls` with the target + outbound
  systemPrompt.
- Press 1 (stay on) / 2 (callback) → inbound DTMF (confirm) or voice
  fallback; press-2 → `{"hangup":true}` then outbound + a callback call.
- Outbound transcript → SSE stream → outcome classifier (DONE /
  NEEDS_APPROVAL / BLOCKED).
- Recording → `GET /v1/calls/{id}` recordingUrl.
