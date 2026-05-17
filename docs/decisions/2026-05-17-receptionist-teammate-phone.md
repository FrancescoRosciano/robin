# Decision: Human teammate on a phone as the simulated receptionist

- **Date:** 2026-05-17
- **Status:** Accepted — FINAL, chosen & wired.
- **Supersedes:** `2026-05-17-receptionist-openai-realtime.md` (kept on
  file as a documented option, not pursued).
- **Scope:** the demo's simulated "24 Hour Gym receptionist" leg only.

## Context

The hosted AgentPhone receptionist agent gave dead air (undocumented
hosted/webhook mode). Successive fallbacks were considered: local TTS
soundboard, then OpenAI Realtime. A free human teammate then became
available to play the receptionist live.

## Decision

A **human teammate answers a real phone** as the 24 Hour Gym
receptionist, following `docs/2026-05-17-receptionist-cheat-card.md`
(derived from `src/robin/fixtures/prompts/receptionist.txt`). Robin
dials `RECEPTIONIST_TO_NUMBER` (mirrored from `TEAMMATE_NUMBER` in the
gitignored `.env`).

## Rationale

- **Most robust on stage:** a human reliably negotiates, handles Robin
  going off-script, and times the capitulation — no brittleness.
- **Removes the hardest blocker:** no OpenAI Realtime ↔ telephony bridge,
  so the undocumented AgentPhone audio-streaming contract is no longer
  on the receptionist critical path.
- **Plan-sanctioned:** this is Plan 05's explicit pre-decided fallback
  ("a teammate's phone").
- **Integrity:** still a disclosed simulation; the outbound call never
  reaches the real company. The teammate is briefed, not impersonating
  a real business.

## Consequences

- Receptionist leg is **unblocked now** with zero further engineering.
- The teammate must have the cheat card and rehearse the capitulation
  line verbatim (incl. confirmation `24HF-4471`).
- `scripts/receptionist_tts.sh` remains the last-ditch tier if the
  teammate is unavailable at showtime.
- Robin's *own inbound* path still needs Plan 06 (webhook server behind
  the tunnel) — unaffected by this decision.
