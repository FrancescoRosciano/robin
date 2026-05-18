# Runbook — Robin

Operational procedures. Generated sections are marked. Hackathon build:
single-branch `main`, the human performs the push/submission (agent
`git push` is denied).

## Bring-up (order matters)

1. **Tunnel** (HTTPS for the AgentPhone webhook). See `scripts/tunnel.md`.
   `cloudflared tunnel --url http://localhost:8000` → note the
   `https://<host>.trycloudflare.com`. **Do NOT restart it** (~12s
   cooldown + the URL changes and breaks the registered webhook). Keep
   it running the whole demo.
2. **Provision** (idempotent): `./scripts/provision.sh`
   - Loads `.env`, reuses (never restarts) a live tunnel, runs
     `scripts/setup_agentphone.py`, upserts the 4 IDs into `.env`, and
     hard-checks `.env` is gitignored.
   - `./scripts/provision.sh --numbers` — read-only, prints the dialable
     `+E.164` numbers.
   - Re-runs are safe: creation is skipped when `*_AGENT_ID` /
     `*_NUMBER_ID` are already in `.env`.
3. **Receptionist** = a briefed teammate on a real phone (the design).
   Set `TEAMMATE_NUMBER` in `.env`; `provision.sh` mirrors it into
   `RECEPTIONIST_TO_NUMBER`. Brief them with
   `docs/2026-05-17-receptionist-cheat-card.md`. Break-glass only (if the
   teammate is physically absent): `scripts/receptionist_tts.sh`.
4. **Server**: host `:8080` → container `:8000`; the tunnel targets host
   `:8080` (compose maps `8080:8000`; the compose default `command` is
   `pytest -q`, so the server is started explicitly, not via plain
   `docker compose up`).

## HTTP endpoints

<!-- AUTO-GENERATED: routes (from src/robin/app.py, src/robin/stage.py) -->
| Method | Path | Source | Purpose |
|--------|------|--------|---------|
| GET  | `/healthz`          | app.py   | Liveness check |
| GET  | `/fixture/law.html` | app.py   | Hosted pre-vetted legal citations (demo) |
| POST | `/webhook`          | app.py   | AgentPhone per-turn webhook (Svix-verified) |
| GET  | `/stage`            | stage.py | Stage dashboard (HTML) |
| GET  | `/stage/stream`     | stage.py | Stage live event stream |
<!-- /AUTO-GENERATED -->

## Health & monitoring

- `GET /healthz` for liveness.
- Tunnel terminal must still show the connection alive before any call.
- Recording add-on gate: `GET /v1/calls/{id}` must return
  `recordingAvailable: true` (enable the add-on in the AgentPhone
  dashboard if absent) — gates the "recording in dashboard" criterion.

## Common issues → fix

<!-- AUTO-GENERATED: incidents (from this session's run log) -->
| Symptom | Cause | Fix |
|---------|-------|-----|
| `502` / read-timeout on `POST /agents` | AgentPhone API degraded (hackathon load) | Re-run `./scripts/provision.sh` — it retries 502/503/504 + timeouts with jittered backoff; check the AgentPhone Discord |
| `ConfigError: missing required environment variable(s)` | `.env` missing a `_REQUIRED` var | Add it (see `.env.example` / `src/robin/config.py`); common: `PUBLIC_BASE_URL`, `RECEPTIONIST_TO_NUMBER`, `ROBIN_AGENT_ID`, `FROM_NUMBER_ID` |
| Receptionist number answers with **dead air** | Hosted AgentPhone agent (undocumented mode) — abandoned path | Receptionist is a teammate on a phone by design; ensure `RECEPTIONIST_TO_NUMBER` = the teammate |
| Webhook turn dies ~30s mid Browser-Use research | Webhook `timeout` not honored | Rely on Plan 03 keepalive interims |
| Duplicate "Robin" agents in dashboard | Non-idempotent `POST /agents` retried during the outage | Pick one, pin all 4 IDs in `.env`; re-runs then skip creation |
<!-- /AUTO-GENERATED -->

## Rollback

- Code: `git revert <sha>` on `main` (do not force-push; agent push is
  denied — the human submits).
- Provisioning: no rollback needed — re-running is idempotent once the 4
  IDs are pinned in `.env`. Strays in the dashboard are harmless.

## Escalation

- AgentPhone API/contract (webhook scope, hosted mode, audio): the
  AgentPhone hackathon Discord `https://tinyurl.com/ycagentphone` — the
  fastest unblock for both Robin's inbound path and any auto-receptionist.
