# Robin — Hackathon Day Plan (submit 8:00 PM)

Schedule: hacking now → **8:00 PM submissions** (video + public GitHub via
Google form) → ~9:30 PM closing. Live demo too.

## Canonical demo (build & rehearse to this)

The live **Stage Runsheet** in the approved design doc + the "Approved
demo" section of `CLAUDE.md`: cancel a 24 Hour Gym membership →
discovery (gym → "24 Hour Gym"; Robin "finds" 415-776-2200, asks
permission) → Browser Use pulls X/Y/Z cancellation laws → outbound call
to a **simulated** receptionist (2nd controlled AgentPhone agent;
disclosed on screen) → escalating negotiation → two-option ultimatum →
capitulation + last-month refund + `24HF-4471` → report back. The fixture
to stand up first is that simulated receptionist + the pre-vetted
`/fixture/law.html`.

## GATE (blockers — keys only; API is known)

- [ ] **`AGENTPHONE_API_KEY`** (agentphone.ai / Discord
  `https://tinyurl.com/ycagentphone`). API known (`agentphone/agentphone-notes.md`).
- [ ] **`BROWSER_USE_API_KEY`** (cloud.browser-use.com → API keys). API
  known (`browseruse/browseruse-notes.md`).
- [ ] Public HTTPS URL for the webhook (cloudflared/ngrok tunnel, or
  Railway). Prior-session lesson: don't reuse a quick-tunnel for hours;
  ~12s cooldown if you restart it.
- Scaffold blueprint to mirror (write fresh, don't fork): the AgentPhone
  founder's repo `github.com/manav2modi/Personal-AI-Phone-Assistant`
  (Flask `server.py` + `setup_agentphone.py` + ndjson Claude loop).
  Nothing below proceeds without the two keys.

## Build order (webhook mode; mirror Moss cookbook structure, write fresh)

1. **Scaffold** `src/` fresh: FastAPI webhook server + Claude tool-call
   loop + HMAC verify. Provision agent + number + register webhook.
   Smoke: call the number, agent speaks one line.
2. **Pure logic (TDD, ~1h, parallelizable):** `context_pack` (+ guard),
   `prompt` render (no unfilled slots), `outcome` classifier
   (DONE/NEEDS_APPROVAL/BLOCKED). No telephony — unit-tested.
3. **Inbound discovery**: system prompt drives brainstorm→plan→confirm;
   NDJSON streaming (interim ack → final).
4. **Keypad 1/2**: confirm the inbound-DTMF event; if unsupported, voice
   fallback ("say one to stay on, two for a callback"). Same UX.
5. **Dial-out**: `POST /v1/calls` with the target + outbound systemPrompt.
6. **Capture + outcome**: SSE `/v1/calls/{id}/transcript/stream` → feed
   the classifier. Press-2 → callback call with the result; press-1 →
   deliver on the same open call.
7. **Recording**: `GET /v1/calls/{id}` → recordingUrl (enable add-on);
   that is the dashboard receipt.
8. **Record a clean proof run** the moment the happy path works once
   (safety net before hardening).
9. **Harden**: reliability, error paths, then rehearse the live Stage
   Runsheet (approved design doc) end to end — discovery → research →
   escalation → ultimatum → capitulation + refund + `24HF-4471`.

## Checkpoints (pre-decided — don't deliberate live)

- **No API key by early afternoon** → escalate hard on Discord/on-site;
  in parallel build everything mockable (pure logic + the webhook server
  against a local fake) so integration is instant once the key lands.
- **Inbound DTMF unsupported** → ship the voice-fallback (say one/two).
  Do not chase call-bridging.
- **~2 h before submit (≈6 PM)**: freeze features. Whatever works end to
  end is the demo. Record the proof run NOW if not already.

## Submission (≈7:00–8:00 PM)

- [ ] Make the GitHub repo public; README current; secrets/PII verified
  absent from history.
- [ ] **Recorded backup run captured** (clean, raw, end-to-end) — this is
  the Google-form video AND the stage safety net. Mandatory before stage.
- [ ] Submit the Google form (video + repo) before 8:00 PM.
- [ ] Rehearse the **live** Stage Runsheet ≥3× against a clock (it's
  multi-minute: discovery → research → escalation → ultimatum →
  capitulation). Confirm the "AI simulation" disclosure is on screen.

## Bonus (only if core is solid, before freeze)

Moss (cookbook is Moss×AgentPhone — semantic search track), MPP/x402
(agent that transacts — Stripe track). One sponsor hook max; do not risk
the core.
