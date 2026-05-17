# Decision: OpenAI Realtime as the simulated receptionist

- **Date:** 2026-05-17
- **Status:** Accepted
- **Supersedes:** the local TTS soundboard (`scripts/receptionist_tts.sh`)
  as the *primary* receptionist; the soundboard is demoted to last-ditch
  zero-dependency safety net.
- **Scope:** the demo's simulated "24 Hour Gym receptionist" leg only.
  Robin's own inbound path is unaffected (that is Plan 06).

## Context

The hosted AgentPhone receptionist agent answered calls with dead air
(undocumented hosted vs. webhook mode; see the Plan 05 run log). Plan
05's pre-decided fallback was a human-paced macOS-`say` soundboard. That
works but is brittle on stage and cannot negotiate — it only replays
fixed lines, so it can't react if Robin goes off-script.

## Decision

Play the receptionist with an **OpenAI Realtime API speech-to-speech
session**, driven by the existing persona in
`src/robin/fixtures/prompts/receptionist.txt` (4 escalation blocks, hold
through legal citations, capitulate verbatim only on the two-option
ultimatum). It is a real, controlled AI simulation — consistent with the
demo's integrity bright line ("AI simulation" disclosed on screen).

## Rationale

- **Dynamic negotiation:** reacts to whatever Robin actually says,
  instead of fixed lines — a far stronger, more honest demo.
- **Same persona source of truth:** reuses
  `receptionist.txt`; no behavioral drift between the prompt and what is
  spoken.
- **Controlled & disclosed:** still a scripted, disclosed AI sim — the
  outbound call never reaches the real company.

## Open question / risk (must resolve at implementation)

OpenAI Realtime is a **WebSocket audio API, not a phone number.** Robin
"dials a number" (AgentPhone `POST /v1/calls` → `RECEPTIONIST_TO_NUMBER`),
so the receptionist must be reachable as a callable number whose call
media is bridged to a Realtime session. Unresolved:

- **Bridge mechanism:** AgentPhone receptionist number → media stream →
  OpenAI Realtime → back. Candidates: AgentPhone webhook-mode agent
  whose server proxies audio to Realtime; or a Twilio Media Streams ↔
  Realtime bridge owning `RECEPTIONIST_TO_NUMBER`. AgentPhone's
  webhook/audio-streaming contract for this is **undocumented** — Discord
  question, same blocker as Plan 06's Robin path.
- **New secret:** `OPENAI_API_KEY` in the gitignored `.env`
  (startup-validated, never committed).
- **Latency/barge-in:** Realtime↔telephony round-trip must stay tight
  enough for a believable live negotiation.
- **Model id:** confirm the current OpenAI Realtime model name against
  OpenAI docs at implementation time (do not hardcode from memory).

## Consequences

- Implementation is **deferred** (non-trivial bridge work — tracked for
  Plan 06/07, gated on the same AgentPhone audio-contract Discord
  answer). Until then the TTS soundboard remains the working fallback,
  so the demo is never without a receptionist.
- `scripts/receptionist_tts.sh` is kept, not deleted — explicit
  last-ditch tier.
