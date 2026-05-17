# Robin Plan 05 — Run Log (2026-05-17)

Operational record of the provisioning & tunnel run. IDs/secrets live
only in the gitignored `.env`; none are reproduced here.

## Outcome

- **Provisioning: SUCCEEDED.** `scripts/setup_agentphone.py` created the
  Robin agent + number, the receptionist agent + number, bound numbers,
  and registered the webhook. The 4 IDs were upserted into `.env`.
  - Live-confirmed (Task 0): `POST /v1/agents`, `/v1/numbers`,
    `/v1/agents/{id}/numbers`, `/v1/webhooks` all behave as documented.
  - AgentPhone API was intermittently `502`/timing-out during the run;
    `setup_agentphone.py` was hardened (90s timeout, jittered retry on
    502/503/504 + timeouts, fast-fail on 4xx/500) and rode through it.
  - Dialable numbers retrieved read-only via `scripts/show_numbers.py`
    (`./scripts/provision.sh --numbers`). `RECEPTIONIST_TO_NUMBER` set
    in `.env`.
- **Tunnel:** cloudflared up and reused (never restarted, per the hard
  rule). One stray older cloudflared on :8000 + one unrelated on :8080
  were left untouched.

## Receptionist — a human teammate on a phone (THE design)

**The receptionist is a human teammate on a real phone. That is the
demo architecture for this leg — not a fallback, not a contingency.**
Robin dials `RECEPTIONIST_TO_NUMBER` (mirrored from `TEAMMATE_NUMBER`
in the gitignored `.env`); the teammate answers and negotiates from
`docs/2026-05-17-receptionist-cheat-card.md` (derived from
`src/robin/fixtures/prompts/receptionist.txt`). Robin's pipeline is
unchanged — it just dials a number a person answers.

Why it is NOT an AgentPhone agent (history, not a tier list): the
hosted AgentPhone receptionist agent connected but produced dead air —
AgentPhone agents are webhook- or hosted-mode and the docs do not
document webhook scope or how to force hosted mode; a global webhook
with no running server most plausibly routed it to a dead webhook. That
path was **abandoned**. The OpenAI-Realtime idea
(`docs/decisions/2026-05-17-receptionist-openai-realtime.md`) is
**superseded and parked**. `scripts/receptionist_tts.sh` exists ONLY as
break-glass if the teammate is physically unavailable at showtime — an
emergency stub, not a designed alternative.

## Still OPEN (not Plan 05-blocking; carried forward)

1. **Recording add-on gate (Task 3 Step 4): UNVERIFIED.** Needs a real
   call_id + `GET /v1/calls/{id}` showing `recordingAvailable: true`.
   No documented "list calls" endpoint — likely needs the AgentPhone
   web app. Gates the demo's "recording in dashboard" criterion.
2. **Robin's own inbound path** has the SAME hosted-vs-webhook
   dependency and **cannot** be faked. Plan 06 must run the FastAPI
   webhook server behind the tunnel; the webhook-scope / hosted-mode
   question is best resolved via the AgentPhone Discord (undocumented).
3. `.env` must also carry `ANTHROPIC_API_KEY`,
   `AGENTPHONE_WEBHOOK_SECRET` (the `whsec_…`), `BROWSER_USE_API_KEY`
   for Plans 03/06 (not verifiable here — `.env` reads are denied).
