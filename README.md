# Robin

Every superhero needs a Robin. You phone a number, Robin runs a discovery
dialogue (brainstorm → plan → execute), then **acts** on your behalf —
making the phone call you hate (**AgentPhone**) and doing the web task you
don't want to (**Browser Use**). Press **1** to stay on the line, **2** to
hang up and get a callback with the result. Every call is recorded in the
dashboard.

Built for the YC AgentPhone "Call My Agent" Hackathon (2026-05-17). Fresh
project, written during the event, on AgentPhone (+ Browser Use).

## Start here

1. `CLAUDE.md` — project brief + rules + how to work.
2. The newest `*-handoff.md` — resume state + the single next step.
3. `SPEC.md` — what to build.
4. `agentphone/agentphone-notes.md` — the confirmed AgentPhone API +
   the founder's webhook-mode reference repo.
5. `browseruse/browseruse-notes.md` — the Browser Use API + how it fits.
6. `DAY_PLAN.md` — hour-by-hour to the 8:00 PM submission.

## Run (once built)

```bash
cp .env.example .env      # fill keys; .env is gitignored, never commit it
# (build the webhook server in src/ per SPEC.md + agentphone-notes.md)
```

Webhook mode: a public HTTPS server AgentPhone POSTs call turns to; a
Claude tool-call loop streams ndjson replies; Browser Use SDK runs web
tasks; `POST /v1/calls` dials out; SSE transcript → outcome → callback.

## Status

Launchpad ready, API known, fresh build pending (needs the AgentPhone +
Browser Use API keys). The prior Patter build under `~/docs/patter/` is
reference only — NOT submitted (wrong platform / fork / built off-hours).

MIT.
