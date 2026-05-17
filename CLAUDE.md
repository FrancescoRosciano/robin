# Robin — AgentPhone Hackathon Build (project brief)

> Read this → the newest `*-handoff.md` here → `SPEC.md` →
> `agentphone/agentphone-notes.md` (the real API) → the approved design
> doc (see "Approved demo" below) → `DAY_PLAN.md`.
> That is the full context to start building.

## What this is

**Robin**: every superhero needs an assistant who just handles it. You
phone a number, Robin runs a discovery dialogue (brainstorm → plan →
execute, asking clarifying questions), dials out on your behalf, and you
press **1** to stay on the line or **2** to hang up and get a callback
with the result. Every call is recorded and visible in the dashboard.

## Approved demo (office-hours, 2026-05-17 — supersedes the generic framing above)

Pitch unchanged ("phone your agent; it does the call you hate").

**Live stage runsheet (this is the canonical demo — build to this):**

1. Presenter calls Robin live on stage: "I want to cancel my gym
   membership."
2. Robin discovery: asks which gym → "24 Hour Gym". Robin says it's
   looking it up, "found their line, 415-776-2200 — want me to call and
   cancel for you?" → presenter says yes. Browser Use really runs here:
   the number lookup is set-dressing; the **real payload is researching
   the cancellation laws** Robin will cite.
3. Robin dials out; the stage hears Robin vs a **simulated 24 Hour
   Gym receptionist** (a 2nd controlled AgentPhone agent). Disclose
   on-screen that the receptionist is an AI simulation.
4. Both negotiate hard — escalating tone, hard lines, fast exchanges.
   Receptionist obstructs (in person / 50% off / certified letter /
   stalling).
5. Robin's close: cites the pre-vetted laws (X, Y, Z), then the
   ultimatum — "Two options. Easy: cancel now, I leave you 5★ on Google.
   Hard: I escalate to your manager's manager, file a complaint that
   this retention process is misleading, demand compensation for the
   misleading offer, and post reviews everywhere. Your decision."
6. Receptionist capitulates: "Fine — I'll cancel your subscription and
   refund your last month."
7. Robin reports back to the caller (same call / callback): cancelled +
   last-month refund + confirmation #.

**Integrity bright line:** the pipeline genuinely runs — real Browser
Use legal research, real AgentPhone inbound discovery, real outbound
call to the controlled simulated receptionist. The raw run is recorded
for the public repo + the Google-form video. Scripting both call sides
(Robin's playbook + the simulated receptionist) is fine and disclosed;
a faked video or non-building repo is disqualifying. The outbound call
never reaches the real company — only the AI simulation.

**Risks to manage:** (a) live multi-minute negotiation on stage — keep
a clean recorded backup video (it is the required submission artifact
regardless); (b) the cited laws (X, Y, Z) must be real and pre-verified,
hosted verbatim — a wrong statute at YC is fatal; (c) named real company
+ simulated receptionist — keep the "AI simulation" disclosure visible
to stay honest and brand-safe.

Full brief + build order:
`~/.gstack/projects/robin/francescorosciano-unknown-design-20260517-112530.md`

## Status (2026-05-17, hackathon day)

Pivot complete. **AgentPhone's API is now KNOWN** — see
`agentphone/agentphone-notes.md` (confirmed from the official docs +
the Moss×AgentPhone cookbook). The only thing still missing is an
**AGENTPHONE_API_KEY** (get from agentphone.ai / Discord
`https://tinyurl.com/ycagentphone`). Everything else is buildable now.

The prior **Patter / `getpatter`** build under `~/docs/patter/` is
**reference only — NOT submittable** (wrong platform, reads as a fork,
built outside hours). All submitted code is written fresh, here, today.

### Pre-flight done (2026-05-17 pre-Wave-1)

- Git repo initialised; private GitHub remote
  **`FrancescoRosciano/robin`** created (`origin`). Initial bootstrap
  commit made locally. **Not pushed** — the human pushes/makes-public at
  submission (agent push stays denied).
- Docker dev environment built and verified (see next section).
  Toolchain green on Python 3.12.13: fastapi 0.136, uvicorn 0.47,
  anthropic 0.102, httpx 0.28, browser-use-sdk 3.6
  (`from browser_use_sdk.v3 import AsyncBrowserUse` OK), pytest 9.0,
  pytest-cov 7.1, pytest-asyncio 1.3, ruff 0.15.
- `src/` and `tests/` still empty — **Wave 1 (Plan 01) is the next
  action.** Keys still gate only Wave 3.

## Dev environment — Docker is MANDATORY on this machine

**Do not fight the host Python.** This machine runs **ThreatLocker**
(endpoint allow-listing). It blocks every non-allow-listed native
binary *per file*: all Homebrew Pythons (3.12/3.13/3.14) fail to
`dlopen` stdlib C-extensions (`mmap … errno=1`), and every compiled
wheel (`pydantic-core`, `ruff`, `coverage`, …) would trip a separate
approval prompt. Only `/usr/bin/python3` (3.9.6 — too old) is
allow-listed. Whack-a-mole approvals are not viable under the deadline.

**All build / test / run happens in Docker** (container Python runs in
the Linux VM, outside host ThreatLocker enforcement):

```
docker compose run --rm robin pytest -q          # tests
docker compose run --rm robin ruff check src tests
docker compose up robin                           # webhook server :8000 (Plan 03)
```

Files: `Dockerfile` (python:3.12-slim), `docker-compose.yml`,
`requirements.txt` (runtime), `requirements-dev.txt` (+ test/lint).
Source is bind-mounted, so edits are live — rebuild only when
requirements change (`docker compose build robin`). The local `.venv/`
(3.9.6) is unusable for this project; ignore it. Plan 01's
`python3 -m pytest` / `ruff` steps run **inside the container**, not on
the host.

## Mandatory components

**Robin = AgentPhone (host platform — the phone) + Browser Use (web
actions).** Both required. Primary build blueprint: the AgentPhone
founder's webhook-mode example
`github.com/manav2modi/Personal-AI-Phone-Assistant` — mirror it, write
fresh, do NOT fork. Web tasks via `browser-use-sdk`. APIs:
`agentphone/agentphone-notes.md`, `browseruse/browseruse-notes.md`.

## HARD RULES (`~/docs/patter/hackathon-prep/goal-rules.md`)

1. **Build using AgentPhone** (the host platform — mandatory).
2. **No prebuilt projects / forks.** Fresh repo, fresh code, during the
   event. (The Moss cookbook is a *structural reference* — mirror the
   pattern, write your own; do not fork it or copy Patter code.)
3. **Build during hackathon hours.** Submit by **8:00 PM** (video +
   public GitHub via Google form). Live demo too.
4. Not a pitch competition — surprise the judges with something that
   didn't exist this morning.

## Architecture (webhook mode — Francesco's explicit call)

FastAPI webhook server + Claude tool-call loop (mirror the Moss cookbook
structure, write fresh). AgentPhone POSTs each turn (`agent.message`,
`channel:"voice"`, `data.transcript`); you stream NDJSON `{"text":...,
"interim":true}` → `{"text":...}`. Dial-out = `POST /v1/calls`. Capture
the outbound call via the SSE transcript stream → outcome classifier →
callback. Recording via `GET /v1/calls/{id}`. Exact endpoints/payloads:
`agentphone/agentphone-notes.md`. Webhook mode (not hosted) — more
control + harnesses + transcript streaming, per Francesco.

## Reusable vs build-fresh

- **Reusable (your own planning — rules-safe):** the concept, `SPEC.md`,
  and the design doc / runsheet / rehearsal card in
  `~/docs/patter/hackathon-prep/`.
- **Reference (read, don't fork):** Moss×AgentPhone cookbook +
  AgentPhone docs (links in `agentphone/agentphone-notes.md`).
- **Build fresh today in `src/`:** the webhook server + the small pure
  logic (context pack, prompt render, outcome classifier — ~1h, TDD).

## How to resume / work

- Resume: read the newest `*-handoff.md` here.
- Non-trivial step: `/office-hours` or `superpowers:brainstorming` →
  `writing-plans` → `subagent-driven-development`. TDD the pure logic.
- Review before commit: `code-reviewer` / `security-reviewer`.
- Ship: fresh GitHub repo (private, then public for the Google form).

## Engineering discipline

- **Model/cost:** default Sonnet; Opus only for genuine reasoning
  bottlenecks; always pass `model:` on agent dispatches; compact long
  sessions. (Prior session overspent on blanket-Opus — do not repeat.)
- **Security:** secrets only in a gitignored `.env`; never commit
  `.env`, `*.local.json`, or real PII (numbers, emails, keys). `.claude/
  settings.json` denies reading `.env` and blocks `git push`/`rm -rf`.
- **Rules:** if a step reuses prebuilt Patter code or looks like a fork,
  stop and re-implement clean.

## Layout

```
robin/
  CLAUDE.md                 this file
  *-handoff.md              session resume doc (read the newest)
  SPEC.md                   product + technical spec
  DAY_PLAN.md               hour-by-hour to the 8 PM submission
  README.md                 repo readme (pitch + run)
  .env.example              required env vars (copy to .env, gitignored)
  .gitignore                hardened (no secrets/PII)
  agentphone/
    agentphone-notes.md     CONFIRMED AgentPhone API (read this)
  src/                      fresh AgentPhone code — written today
  tests/                    pure-logic tests (no telephony)
  .claude/                  project config (rules + settings)
```
