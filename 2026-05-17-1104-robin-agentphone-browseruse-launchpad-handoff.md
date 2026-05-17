<goal>
# Goal
Win the YC AgentPhone "Call My Agent" Hackathon (TODAY 2026-05-17, submit
by **8:00 PM** — video + public GitHub via the Google form; live demo
too) with **Robin**: phone a number → discovery dialogue (brainstorm →
plan → execute) → Robin acts on your behalf via **AgentPhone** (the phone
call) and **Browser Use** (the web task) → press **1** stay on the line /
**2** hang up + callback → recording in the dashboard.
</goal>

<CurrentState>
## Current State
**Launchpad complete; zero product code written (by rules, the build is
fresh during hackathon hours).** Project home: `~/docs/robin/` with
`CLAUDE.md`, `SPEC.md`, `DAY_PLAN.md`, `README.md`, `.env.example`,
`.gitignore`, `.claude/` (settings.json + rules/hackathon.md, from the
ECC fallback), `agentphone/agentphone-notes.md`,
`browseruse/browseruse-notes.md`, empty `src/` + `tests/`.

**APIs are known** (no more research blocking): AgentPhone webhook-mode
endpoints, payloads, transcript SSE, recording, and the founder's
reference repo are documented in `agentphone/agentphone-notes.md`;
Browser Use SDK usage in `browseruse/browseruse-notes.md`.

**Only blockers: two API keys + a public URL.** Need
`AGENTPHONE_API_KEY` (agentphone.ai / Discord
`https://tinyurl.com/ycagentphone`) and `BROWSER_USE_API_KEY`
(cloud.browser-use.com), plus an HTTPS tunnel for the webhook.

The prior **Patter / `getpatter`** build under `~/docs/patter/` (repo
`patterai-patter`, GitHub `FrancescoRosciano/pulsen`) is **reference
only — NOT submitted** (wrong platform, reads as a fork, built
off-hours). Mine it for architecture, do not copy its code.
</CurrentState>

<FilesInFlight>
## Files in flight
- (none — launchpad docs are done; `src/` is intentionally empty. The
  fresh AgentPhone+BrowserUse webhook build starts once the two keys are
  in hand, mirroring `github.com/manav2modi/Personal-AI-Phone-Assistant`.)
</FilesInFlight>

<Changed>
## Changed
- `~/docs/robin/` (new project) — full launchpad: CLAUDE.md, SPEC.md,
  DAY_PLAN.md, README.md, .env.example, .gitignore, .claude/
  (settings.json + rules/hackathon.md), agentphone/agentphone-notes.md
  (confirmed API + founder & Moss reference repos),
  browseruse/browseruse-notes.md, src/ + tests/ skeleton.
- (Reference only, NOT the submission) `~/docs/patter/` — the Patter
  build + `~/docs/patter/hackathon-prep/` planning kit (design doc,
  runsheet, rehearsal card, goal-rules, kickoff notes).
</Changed>

<FailedAttempts>
## Failed attempts
- Strategy "dogfood Patter": invalid vs the written rules (must use
  AgentPhone; no prebuilt/forks; build during hours). Whole Patter
  codebase is reference, not the entry.
- WebFetch on the big AgentPhone docs (`llms-full.txt`, `llms.txt`) — the
  summarizer drops API specifics. Fix: read `llms-full.txt` and the
  Calls guide directly; the founder repo + Moss cookbook are the
  concrete blueprints.
- `configure-ecc` can't run unattended (needs interactive
  AskUserQuestion) — used the fallback (`.claude/settings.json` +
  rules/hackathon.md).
- gh/Bash: hook-bypass disallowed; classifier hard-blocks external-repo
  push + agent-inferred collaborator. The USER must run repo-create /
  push / collaborator-invite commands via `!`.
- Prior session overspent on blanket-Opus + 1M context. Discipline:
  default Sonnet, explicit `model:` per dispatch, compact often.
- Inbound caller-DTMF (press 1/2) capture is NOT confirmed in the
  AgentPhone Calls guide — voice fallback ("say one / say two") is the
  safe default; verify the DTMF-in event in `llms-full.txt` before
  promising the literal keypad.
</FailedAttempts>

<NextStep>
## Next step
Once `AGENTPHONE_API_KEY` + `BROWSER_USE_API_KEY` + a public HTTPS URL
are in `~/docs/robin/.env`, scaffold a fresh webhook server in
`~/docs/robin/src/` mirroring `github.com/manav2modi/Personal-AI-Phone-Assistant`
(provision agent/number/webhook via a setup script; ndjson Claude
tool-call loop) and smoke one inbound call where Robin speaks.
</NextStep>
