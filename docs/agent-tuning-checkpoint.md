# Recommendation — agent tuning belongs in Plan 06, not a new Plan 07

> Hand-off note for the session that owns the robin plan set. Not a plan
> edit — fold into Plan 06 if you agree, discard if not.

## The gap

"Tuning the agents" is currently smeared across three plans with no
single owner of the question **"is the negotiation good enough to go on
stage?"**:

- Plan 02 — *writes* both prompts (inbound discovery, outbound
  negotiation playbook, receptionist obstruction system prompt).
- Plan 05 — *wires them live* (`PATCH /v1/agents/{id}`
  `{"voiceMode":"webhook"}` + webhook URL for Robin; create the 2nd
  hosted receptionist agent and load its `systemPrompt`).
- Plan 06 — *converges them by ear* (manual win-gate + ×3 rehearsals).

## Why not a separate Plan 07

- Plan 00 / the execution sequence is frozen; a 7th plan reopens the
  orchestration map on hackathon day.
- Tuning is not independently schedulable — hard-gated to Wave 3 (live
  key + tunnel + both agents provisioned), can't parallelize, is
  structurally the tail of Plan 06.
- Plan 06 already owns the loop (win-gate + ×3 rehearsals); a Plan 07
  duplicates ownership and the frozen risk-register entry.

## Recommended: a named checkpoint inside Plan 06

Add an explicit "Agent tuning convergence" checkpoint with a hard
pass/fail rubric, e.g.:

> **PASS** iff 3/3 consecutive rehearsals: Robin lands cancel +
> last-month refund + a `24HF-####` confirmation, with **no operator
> intervention**, in **under N minutes**. Otherwise the recorded backup
> run is the stage artifact (already the pre-decided fallback).

Two agents, tuned differently — capture both in the checkpoint:

- **Robin** (webhook): dashboard prompt is inert. Levers = in-repo
  inbound template + per-call `systemPrompt` on `POST /v1/calls`.
- **Receptionist** (hosted): a genuine `systemPrompt` on the 2nd agent —
  this is the one that's actually tuned as an AgentPhone agent.

Source for the API facts: `agentphone/agentphone-notes.md`
(§ "Agent tuning / configuration — CONFIRMED").
