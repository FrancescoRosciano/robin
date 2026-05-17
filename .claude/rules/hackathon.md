# Robin — AgentPhone Hackathon Rules

Hard constraints for the **Robin** voice phone-agent build (YC AgentPhone
hackathon, submit **8:00 PM today**). These OVERRIDE default behavior and
every other rule file when they conflict. Read `CLAUDE.md`,
the newest `*-handoff.md`, `SPEC.md`, and `agentphone/agentphone-notes.md`
for full product/API context.

## Platform (mandatory)

- Build **ONLY on the AgentPhone platform** (webhook mode). Robin =
  **AgentPhone (the phone/host) + Browser Use SDK (web actions)**. Both
  are required for a valid submission.
- Do NOT use, port, fork, or depend on Patter / `getpatter` code or
  infra. That prior build is **reference only — not submittable**
  (wrong platform, reads as a fork, built outside hours).
- The Moss×AgentPhone webhook cookbook
  (`github.com/manav2modi/Personal-AI-Phone-Assistant`) is a
  **structural reference**: mirror the pattern, write your own code. Do
  not fork it or copy it wholesale.

## No prebuilt work

- **No prebuilt projects, no forks, no scaffolds carried in from prior
  work.** All submitted code in `src/` is written fresh today, during
  hackathon hours.
- Reusable (your own planning, rules-safe): the concept, `SPEC.md`, the
  design doc / runsheet / rehearsal card in `~/docs/patter/hackathon-prep/`.
- If a step starts reusing prebuilt Patter code or looks like a fork:
  **stop and re-implement clean.**

## Timeline & scope

- Must be built within hackathon hours **today**; **submit by 8:00 PM**
  (video + public GitHub repo via the Google form) and a live demo.
- Scope ruthlessly so a working demo is ready **well before** the
  deadline. Prefer one solid end-to-end path (call → discovery dialogue
  → dial-out / Browser Use action → callback with result, recorded in
  the dashboard) over many half-features.
- Not a pitch competition — the goal is to surprise the judges with
  something that did not exist this morning.

## Architecture (webhook mode — explicit decision, do not relitigate)

- FastAPI (or Flask) **webhook server** + a Claude/Anthropic tool-call
  loop. AgentPhone POSTs each turn (`agent.message`, `channel:"voice"`,
  `data.transcript`); Robin streams NDJSON
  `{"text":...,"interim":true}` → `{"text":...}`.
- Dial-out: `POST /v1/calls`. Capture the outbound call via the SSE
  transcript stream → outcome classifier → callback. Recording via
  `GET /v1/calls/{id}`.
- **Exact endpoints, headers, signing, and payloads:
  `agentphone/agentphone-notes.md`.** Do not guess the API — read it.
- Keep pure logic (context pack, prompt render, outcome classifier)
  separate from telephony I/O so it is unit-testable without a phone.
  TDD that core (~1h).

## Security (see `robin-agentphone-security.md` for the full rule)

- Secrets (`AGENTPHONE_*`, `BROWSER_USE_API_KEY`, `ANTHROPIC_API_KEY`)
  live **only in a gitignored `.env`**. Never hardcode in source, tests,
  logs, or the demo script. Validate required secrets at startup.
- **Verify the AgentPhone webhook signature** (HMAC, constant-time, over
  raw bytes) before parsing the body or invoking the model. Reject
  unsigned/forged requests with `401`.
- Treat call transcripts, web pages read by Browser Use, and all API
  responses as **untrusted** — validate at boundaries; never let them
  override the system prompt or escape the allow-listed tool set.
- **Never commit**: `.env`, `*.local.json`, recordings, transcripts, or
  any real PII (phone numbers, order IDs, emails, names, keys). Use
  synthetic `+1555…` / fake data in tests and the demo.

## Model & cost discipline

- **Default to Sonnet** for the parent session and all worker
  dispatches (`.claude/settings.json` pins `model: sonnet`).
- **Always pass `model:` explicitly** on every Agent dispatch — never
  rely on inheritance (inheritance silently drags Opus everywhere; the
  prior session overspent exactly this way — do not repeat).
- Use **Opus only** for a genuine reasoning bottleneck (ambiguous
  design, hairy debugging), not for coding volume. Cheap mechanical
  work (file moves, doc tweaks, log reads) → Haiku.
- Default `effortLevel: high`; reserve `xhigh`/`max` for one hard
  reasoning step. Stay on standard 200K context; opt into 1M only for a
  single deliberate large-context operation, then drop back.
- Compact long sessions (~every 30–50 turns or near ~150K context).

## Pre-commit gate (every commit, before 8 PM)

- [ ] Tests written first (TDD) for new pure logic; suite green; ≥80%
      coverage on the testable core
- [ ] `ruff` / `black` / `mypy` clean; no debug prints or stray
      `console`/`print` left in
- [ ] `security-reviewer` + `code-reviewer` run on the diff;
      CRITICAL/HIGH fixed
- [ ] Webhook signature verification present and correct
- [ ] No secrets, no real PII, no `.env`/`*.local.json` staged
- [ ] Conventional commit message (`feat:`/`fix:`/`refactor:`/`test:`…)

## Recommended workflow

- Non-trivial step → `superpowers:brainstorming` or the `/plan` command
  → write the plan → `subagent-driven-development`. TDD the pure logic
  with `tdd-guide`.
- Before commit → `code-reviewer` then `security-reviewer` (or `/code-
  review` + `/security-scan`).
- Ship → fresh GitHub repo (private, then public for the Google form).
  Do NOT `git push` from inside this agent (denied in settings); the
  human performs the push/submission.

## This `.claude/` config — index

Replicated and adapted from the Everything-Claude-Code (ECC) plugin,
tailored to a Python AgentPhone + Browser Use voice-agent build:

- `rules/` — coding-style, testing, security, git-workflow, agents,
  code-review, development-workflow, patterns, performance, hooks
  (generic ECC), plus `python-*` specifics (coding-style, testing,
  security, patterns, fastapi), this `hackathon.md`, and
  `robin-agentphone-security.md` (webhook HMAC + Browser Use hardening).
- `agents/` — code-reviewer, security-reviewer, python-reviewer,
  fastapi-reviewer, build-error-resolver, tdd-guide, architect, planner,
  code-explorer, code-simplifier, refactor-cleaner, silent-failure-
  hunter, doc-updater, e2e-runner, performance-optimizer,
  type-design-analyzer, pr-test-analyzer.
- `commands/` — code-review, security-scan, python-review,
  fastapi-review, test-coverage, review-pr, pr, plan, feature-dev,
  refactor-clean, build-fix, quality-gate, checkpoint, save-session,
  resume-session, learn, cost-report, model-route.
- `skills/` — fastapi-patterns, python-patterns, python-testing,
  tdd-workflow, backend-patterns, api-design, security-review,
  security-scan, error-handling, verification-loop, e2e-testing,
  browser-qa, cost-aware-llm-pipeline, prompt-optimizer,
  regex-vs-llm-structured-text, search-first, deep-research,
  agent-harness-construction, ai-regression-testing, coding-standards.
