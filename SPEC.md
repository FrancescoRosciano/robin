# Robin — Spec (build fresh, on AgentPhone, webhook mode)

## Product

> **Canonical demo = the live Stage Runsheet in the approved design doc**
> (`~/.gstack/projects/robin/francescorosciano-unknown-design-20260517-112530.md`)
> and the "Approved demo" section of `CLAUDE.md`. Build to that: cancel a
> 24 Hour Gym membership — discovery → Browser Use legal research →
> outbound call to a *simulated* receptionist → escalating negotiation →
> two-option ultimatum → capitulation + last-month refund + `24HF-4471`.

Call Robin. It runs a real **discovery** dialogue (brainstorm → plan →
execute): asks what you need, probes the goal + constraints + what a good
outcome is, until unambiguous (for the demo: which gym → "24 Hour
Gym"; Robin "finds the number" 415-776-2200 and asks permission to
call). States the plan back. Then dials out on your behalf. Caller
chooses involvement by keypad:

- **Press 1** — stay on the line; get the result on this same call.
- **Press 2** — hang up; get a callback with the summary + result.

Every call is **recorded and visible in the dashboard**.

Honest constraint: literal "press 1 = hear the other call's audio live"
is call-bridging — not confirmed in AgentPhone. Robust reading: press-1 =
"stay on, I deliver the result on this call when done"; press-2 =
callback. Inbound caller-DTMF capture is the one open API item (see
`agentphone/agentphone-notes.md`); **voice fallback** ("say one / say
two") is the safe default and identical UX.

## Technical shape (platform-agnostic core — re-implement fresh, TDD)

Small, telephony-independent, unit-testable, ~1h:

- **context pack**: local JSON — identity (name, callback number),
  target, goal templates (win + fallback). Loaded at call start. Guard
  rejects unfilled placeholders (fail fast, not on stage). Real PII →
  gitignored, never committed.
- **prompt render**: system prompt from the pack; no unfilled `{{slot}}`
  ever ships.
- **outcome classifier**: outbound transcript → exactly three shapes —
  **DONE** (cancellation confirmed + refund acknowledged + confirmation
  `24HF-4471`), **NEEDS_APPROVAL** (hit an OTP/verification it can't
  pass), **BLOCKED** (where + why).
- **three legs**: (1) inbound discovery (webhook tool-call loop),
  (2) outbound (`POST /v1/calls`, works the target), (3) result delivery
  (callback on press-2 / same-call on press-1).

## AgentPhone integration — KNOWN (full detail: `agentphone/agentphone-notes.md`)

Webhook mode (Francesco's call). Confirmed from official docs + the
Moss×AgentPhone cookbook (the structural blueprint — mirror, write fresh):

- Auth `Bearer`, base `https://api.agentphone.ai/v1`. **Need API key.**
- Provision: `POST /v1/agents`, `POST /v1/numbers`, bind, `POST /v1/webhooks`.
- Inbound webhook: `{"event":"agent.message","channel":"voice","data":
  {"transcript":"..."},"recentHistory":[...]}`. Respond NDJSON
  `{"text":...,"interim":true}` → `{"text":...}`; fields `hangup`,
  `action`, `digits`. Tool-calling = interim ack → run tools → final.
- Outbound (the dial-out): `POST /v1/calls` `{agentId,toNumber,
  initialGreeting,systemPrompt,fromNumberId}`.
- Transcript: SSE `GET /v1/calls/{id}/transcript/stream` (`turn` events
  role/content) → feed the classifier.
- Recording: `GET /v1/calls/{id}` → `recordingUrl`.
- Open: inbound caller-DTMF event (else voice fallback); HMAC verify
  (Moss `moss_agentphone.py` shows the approach).

## Browser Use (mandatory — web actions)

Robin's "execute" leg is phone AND/OR web. Discovery decides: a phone
task → AgentPhone `POST /v1/calls`; a web task → `browser-use-sdk`
`await client.run("<task>")` → `result.output`; a task needing both →
run the web task and hand any phone step (OTP/2FA, voice confirm) to
AgentPhone. The outcome classifier consumes either a call transcript
(AgentPhone SSE) or `result.output` (Browser Use). This combo is the
demo's edge and hits the Browser Use sponsor track. API + open items:
`browseruse/browseruse-notes.md`.

## Acceptance (demo)

- Live on stage: presenter calls Robin → discovery (gym → "24 Hour
  Gym"; Robin "finds" 415-776-2200, asks permission) → Browser Use
  returns the X/Y/Z cancellation laws → Robin dials the **simulated**
  receptionist → escalating negotiation → two-option ultimatum (5★ vs.
  boss's-boss + misleading-offer complaint + compensation + reviews) →
  receptionist capitulates: cancellation **+ last-month refund** +
  `24HF-4471` → Robin reports back → recording in the dashboard. Multi-
  minute, no operator intervention. Disclose on screen: receptionist =
  AI simulation; real 24 Hour Gym is never called.
- A clean recorded backup run is mandatory (the Google-form video + the
  safety net) — captured before going on stage.
- One-sentence pitch: *phone your agent; it does the call you hate.*
- Full runsheet + scripts: the approved design doc (Stage Runsheet,
  Legal Citations, Receptionist + Negotiation Playbook sections).

## Bonus tracks (only after the core demo is solid)

Moss (large-data semantic search — the cookbook is Moss×AgentPhone),
MPP/x402 (an agent that *transacts* — Stripe track), AgentMail, Browser
Use, Supermemory, Sponge. Grand prize (YC interview) needs the core
AgentPhone build working first.
