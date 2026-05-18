# docs/stage/hardening-and-recovery.md — Robin Hardening & Stage Recovery

> Operator-grade. Read before going on stage. Pre-decided — do not invent alternatives live.

---

## PART 1 — Webhook Signature Posture for Submission

### Decision: commit the gate, run demo with `ROBIN_SKIP_WEBHOOK_VERIFY=1`, disclose it

**Why this is the one correct path:**

The Svix signing secret (`whsec_…`) rotates every time the AgentPhone Webhooks
dashboard is viewed and cannot be fetched via the AgentPhone REST API
(`agentphone-notes.md` documents `/v1/agents`, `/v1/numbers`, `/v1/calls`, and
SSE — no endpoint exposes the webhook signing secret). Pinning it before 8 PM is
not possible without incurring another rotation event the moment anyone checks
the dashboard again. Attempting to run verification ON with an unpinned secret
produces a 401 wall that kills the live demo.

**What is committed (already in place — do not change):**

- `src/robin/signature.py` — correct Svix verification via the official `svix`
  library over raw bytes, with constant-time compare, replay window, and
  `MalformedJSONError` / `SignatureError` split. Verification logic is sound.
- `src/robin/app.py` — `_SKIP_VERIFY` reads `ROBIN_SKIP_WEBHOOK_VERIFY` from
  the environment at startup. Default is `False` (verification ON). The bypass
  is a runtime-only env override; it is never in `.env.example`, never
  committed, never in source.
- The gate logs a `WARNING` on every skipped request — the bypass is
  self-documenting in the server logs.

**The code is secure-by-default. The bypass is a documented, disclosed
runtime-only escape hatch for a platform limitation, not a security shortcut.**

### Required disclosure — paste verbatim into README.md (human step)

Add this block to `README.md` under a "Webhook Signature" heading before
pushing the public repo:

```
## Webhook Signature

Robin implements full Svix HMAC webhook verification (`src/robin/signature.py`)
and runs with it **enabled by default** (`ROBIN_SKIP_WEBHOOK_VERIFY` unset).

For the live hackathon demo the bypass flag (`ROBIN_SKIP_WEBHOOK_VERIFY=1`) is
set at runtime only, because the AgentPhone platform does not expose the Svix
signing secret via its REST API — the secret rotates on every dashboard view and
cannot be programmatically pinned before the submission deadline. This is a
documented platform constraint, not a code shortcut. The verification path
(`src/robin/signature.py`) is committed, tested, and remains the production
default. Anyone deploying Robin to their own AgentPhone account with a stable
secret can drop the flag.
```

**Human action required:** add the block above to README.md, then push.

---

## PART 2 — Tunnel Stability

### Decision: named `cloudflared` tunnel with a stable hostname

**Why not a quick tunnel:** `cloudflared tunnel --url` (quick tunnel) gives a
random `*.trycloudflare.com` hostname that changes on every restart and has no
uptime SLA. One crash mid-demo means re-registering the AgentPhone webhook URL —
a 60-90 second human action under stage pressure.

**Why a named tunnel:** a named tunnel gets a permanent, human-readable
`<name>.cfargotunnel.com` subdomain (or your own CNAME). It survives process
restarts without changing the URL. Cloudflare's free plan supports named tunnels
with no paid signup.

### One-time setup (do this now, before the demo slot) — human steps

```bash
# 1. Authenticate (opens browser — do once per machine)
cloudflared tunnel login

# 2. Create the named tunnel (do once; stores credentials in ~/.cloudflared/)
cloudflared tunnel create robin-demo

# 3. Note the tunnel UUID printed above, then create the config file
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/robin-demo.yml <<'EOF'
tunnel: robin-demo
credentials-file: /Users/francescorosciano/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: robin-demo.cfargotunnel.com
    service: http://localhost:8080
  - service: http_status:404
EOF
# Replace <TUNNEL-UUID> with the UUID printed in step 2.

# 4. Route the tunnel hostname (do once)
cloudflared tunnel route dns robin-demo robin-demo.cfargotunnel.com

# 5. Start the tunnel (keep this terminal open during demo)
cloudflared tunnel --config ~/.cloudflared/robin-demo.yml run robin-demo
```

Webhook URL to register in AgentPhone dashboard (human step — one-time):
```
https://robin-demo.cfargotunnel.com/webhook
```

**This URL is permanent.** If the tunnel process dies and restarts, the URL does
not change and does not need to be re-registered.

---

## PART 3 — "Tunnel Died Mid-Demo" Recovery Runbook (<60 s)

> Read this aloud once before walking on stage. The steps are ordered for
> minimal hand movement. Target: presenter is back on phone within 45 s.

### Prerequisites (confirm before stage, not during)

- Docker Desktop running.
- Named tunnel configured (Part 2 above).
- Terminal 1 open: the `cloudflared` tunnel process.
- Terminal 2 open: Docker uvicorn (or ready to launch it).
- AgentPhone dashboard webhook URL already set to
  `https://robin-demo.cfargotunnel.com/webhook` (permanent — no change needed).

---

### Recovery sequence

**Step 1 — Restart the tunnel (Terminal 1) — ~5 s**

```bash
cloudflared tunnel --config ~/.cloudflared/robin-demo.yml run robin-demo
```

If the tunnel was the only thing that died, this is the entire recovery.
Proceed to Step 4 (verify). The webhook URL does not change.

---

**Step 2 — If the Docker container also died, restart it (Terminal 2) — ~15 s**

```bash
docker compose run --rm \
  -p 8080:8000 \
  -e PYTHONPATH=src \
  -e ANTHROPIC_API_KEY=<from-your-.env> \
  -e AGENTPHONE_API_KEY=<from-your-.env> \
  -e ROBIN_SKIP_WEBHOOK_VERIFY=1 \
  robin \
  uvicorn robin.main:app --host 0.0.0.0 --port 8000 --log-level info
```

Replace `<from-your-.env>` with the actual values (never commit them; have them
in your shell or a sourced file that is not the committed `.env.example`).

Wait for the log line:
```
INFO:     Application startup complete.
```

---

**Step 3 — Confirm the webhook URL is still correct (AgentPhone dashboard) — ~5 s**

Because you are using a named tunnel the URL (`https://robin-demo.cfargotunnel.com/webhook`)
does not change. No dashboard update is needed unless this is your first restart
with the named tunnel and you had previously registered a quick-tunnel URL.

If you need to update it: AgentPhone dashboard → Webhooks → edit endpoint URL →
paste `https://robin-demo.cfargotunnel.com/webhook` → save. (~20 s)

---

**Step 4 — One-curl verify (Terminal 1 or Terminal 2) — ~5 s**

```bash
curl -s https://robin-demo.cfargotunnel.com/healthz
```

Expected response:
```json
{"ok": true}
```

Any 200 with `{"ok":true}` means the tunnel is up, the container is running, and
FastAPI is healthy. You are back on phone.

---

**Total recovery time (named tunnel, container stayed up): ~10 s**
**Total recovery time (both tunnel + container died): ~25-35 s**

---

### If recovery exceeds 30 s on stage

Switch the projector to the backup video immediately (per av-runbook.md
CONTINGENCY path). Do not keep the audience waiting — narrate: "Let me show you
the pipeline from our test run." The backup video is the submission artifact
regardless.

---

## Quick Reference Card (print and tape to laptop lid)

```
TUNNEL DEAD:
  Terminal 1: cloudflared tunnel --config ~/.cloudflared/robin-demo.yml run robin-demo
  Curl check:  curl -s https://robin-demo.cfargotunnel.com/healthz  →  {"ok":true}

CONTAINER DEAD:
  Terminal 2: docker compose run --rm -p 8080:8000 -e PYTHONPATH=src \
    -e ANTHROPIC_API_KEY=<KEY> -e AGENTPHONE_API_KEY=<KEY> \
    -e ROBIN_SKIP_WEBHOOK_VERIFY=1 robin \
    uvicorn robin.main:app --host 0.0.0.0 --port 8000 --log-level info
  Wait for: "Application startup complete."

WEBHOOK URL (permanent, never changes):
  https://robin-demo.cfargotunnel.com/webhook

>30 s recovery → backup video, narrate, continue.
```

---

## Security Notes

- Never paste real API keys into this file or any committed document.
  Use `<from-your-.env>` placeholders here; source keys from your local
  shell environment before the demo.
- `ROBIN_SKIP_WEBHOOK_VERIFY=1` is set at the `docker compose run` command
  only — it is never in `.env.example`, never committed, never in source.
- The signed, correctly-verified path (`src/robin/signature.py`) remains
  the production default for any deployment where the Svix secret is stable.
