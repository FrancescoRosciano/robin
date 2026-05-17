# Decision: Human teammate on a phone as the simulated receptionist

- **Date:** 2026-05-17
- **Status:** Accepted — FINAL, chosen & wired.
- **Supersedes:** `2026-05-17-receptionist-openai-realtime.md` (kept on
  file as a documented option, not pursued).
- **Scope:** the demo's simulated "24 Hour Gym receptionist" leg only.

## Context

The receptionist leg of the demo is performed by a **human teammate**.
That is the design. The hosted AgentPhone receptionist agent was tried
and gave dead air (undocumented hosted/webhook mode); that path was
abandoned. The OpenAI-Realtime and local-TTS ideas are parked /
break-glass only — they are not co-equal options to choose between.

## Decision

The receptionist **is a human teammate answering a real phone** as the
24 Hour Gym receptionist, following
`docs/2026-05-17-receptionist-cheat-card.md` (derived from
`src/robin/fixtures/prompts/receptionist.txt`). Robin dials
`RECEPTIONIST_TO_NUMBER` (mirrored from `TEAMMATE_NUMBER` in the
gitignored `.env`). This is the demo architecture for this leg.

## Rationale

- **Most robust on stage:** a human reliably negotiates, handles Robin
  going off-script, and times the capitulation — no brittleness.
- **Removes the hardest blocker:** no OpenAI Realtime ↔ telephony bridge,
  so the undocumented AgentPhone audio-streaming contract is no longer
  on the receptionist critical path.
- **Plan-consistent:** Plan 05 explicitly allows a teammate's phone for
  this leg; here it is the chosen design, not a contingency.
- **Integrity:** a disclosed role-play — a briefed team member playing
  the receptionist. The outbound call never reaches the real company.
  NOTE: on-screen disclosure must say a *team member is role-playing*
  the receptionist, NOT "AI simulation" (see consequences).

## Consequences

- Receptionist leg is **unblocked now** with zero further engineering.
- The teammate must have the cheat card and rehearse the capitulation
  line verbatim (incl. confirmation `24HF-4471`).
- **Disclosure (integrity bright line):** the on-screen / spoken
  disclosure must state the receptionist is a **briefed team member
  role-playing** the 24 Hour Gym front desk — NOT an "AI simulation."
  `CLAUDE.md`'s approved-demo runsheet still says "2nd controlled
  AgentPhone agent" / "AI simulation" and must be reconciled to match
  reality before the demo (flagged to the operator, not auto-edited).
- `scripts/receptionist_tts.sh` is **break-glass only** (teammate
  physically unavailable at showtime) — not a designed alternative.
- Robin's *own inbound* path still needs Plan 06 (webhook server behind
  the tunnel) — unaffected by this decision.
