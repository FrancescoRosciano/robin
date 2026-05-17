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

## Receptionist — FALLBACK INVOKED (Plan 05 Task 4, pre-decided)

Calling the hosted receptionist number connected but produced **dead
air** — no greeting, no response to speech. Root cause (best read):
AgentPhone agents are webhook-mode OR hosted-mode; the docs do **not**
document webhook scope or how to force hosted mode. A single globally
registered webhook + our webhook server not yet running (Plan 06) most
plausibly routed the receptionist into webhook mode → silence.

Per the plan's pre-decided gate ("don't rabbit-hole undocumented
hosted-mode under deadline"), a local fallback was invoked. Robin's
pipeline is unchanged either way; it still "dials the number."

**DECISION (2026-05-17, FINAL — chosen & wired):** the receptionist is
played by a **human teammate on a real phone**, reading the cheat card
derived from `src/robin/fixtures/prompts/receptionist.txt`. This is
Plan 05's other pre-decided fallback ("set RECEPTIONIST_TO_NUMBER to a
teammate's phone"). `RECEPTIONIST_TO_NUMBER` in `.env` is mirrored from
`TEAMMATE_NUMBER`. Robin's pipeline is unchanged — it just dials a
number a person answers. This removes the OpenAI-Realtime telephony
bridge (and its undocumented AgentPhone audio-contract dependency) from
the critical path entirely.

Fallback tiers, in order:
1. **Human teammate on a phone** (PRIMARY — chosen, wired). Number in
   `.env` (`RECEPTIONIST_TO_NUMBER` = `TEAMMATE_NUMBER`). Script:
   `docs/2026-05-17-receptionist-cheat-card.md`.
2. **OpenAI Realtime receptionist** (optional, SUPERSEDED as primary) —
   see `docs/decisions/2026-05-17-receptionist-openai-realtime.md`;
   kept on file, implementation not pursued unless the teammate falls
   through and a dynamic auto-receptionist is wanted later.
3. **Local TTS soundboard** (last-ditch, zero-dependency) —
   `scripts/receptionist_tts.sh` (macOS `say`).

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
