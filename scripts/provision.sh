#!/usr/bin/env bash
# Robin Plan 05 — Tasks 2+3 orchestrator (operator-run, watch the output).
#
# Loads .env, brings the cloudflared tunnel up ONCE (never auto-restarts
# it — Plan 05 hard rule: restart = ~12s cooldown + the webhook URL
# changes and breaks the registered webhook), runs the idempotent
# provisioning script, upserts the returned IDs back into .env, and runs
# the .env-gitignore gate. Task 4 (phone the receptionist) and the
# recording-add-on check stay manual — see the printed checklist.
#
# Re-run safe: an already-running tunnel is reused; provisioning skips
# anything whose *_ID is already in .env. Force a fresh tunnel only with
# --new-tunnel (you then MUST re-run provisioning so the webhook URL
# matches).
#
# Secrets: read from .env only; never printed. .env stays gitignored.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="$REPO_ROOT/.env"
TUNNEL_LOG="$REPO_ROOT/scripts/.tunnel.log"
TUNNEL_PID="$REPO_ROOT/scripts/.tunnel.pid"
PY="${PYTHON_BIN:-python3}"
LOCAL_PORT=8000
FORCE_NEW_TUNNEL=0
[ "${1:-}" = "--new-tunnel" ] && FORCE_NEW_TUNNEL=1

die() { echo "ERROR: $*" >&2; exit 1; }

# --- load .env (no echo of values) ---
[ -f "$ENV_FILE" ] || die ".env not found at $ENV_FILE — create it with the keys first."
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
[ -n "${AGENTPHONE_API_KEY:-}" ] || die "AGENTPHONE_API_KEY not set in .env."

# --- upsert KEY=VALUE into .env, preserving the rest, chmod 600 ---
upsert_env() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  if [ -f "$ENV_FILE" ]; then grep -v -E "^${key}=" "$ENV_FILE" > "$tmp" || true; fi
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

# --- tunnel: reuse if alive, else start once (never auto-restart) ---
tunnel_alive() {
  [ -f "$TUNNEL_PID" ] && kill -0 "$(cat "$TUNNEL_PID")" 2>/dev/null
}

scrape_url() {
  grep -oE 'https://[A-Za-z0-9.-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1
}

if [ "$FORCE_NEW_TUNNEL" -eq 1 ] && tunnel_alive; then
  echo ">> --new-tunnel: stopping existing tunnel $(cat "$TUNNEL_PID")"
  kill "$(cat "$TUNNEL_PID")" 2>/dev/null || true
  sleep 2; rm -f "$TUNNEL_PID"
fi

if tunnel_alive && [ "$FORCE_NEW_TUNNEL" -eq 0 ]; then
  PUBLIC_BASE_URL="$(scrape_url)"
  [ -n "$PUBLIC_BASE_URL" ] || die "Tunnel process alive but no URL in $TUNNEL_LOG — inspect it, do not blindly restart."
  echo ">> Reusing running tunnel (NOT restarted): $PUBLIC_BASE_URL"
else
  command -v cloudflared >/dev/null 2>&1 || die "cloudflared not installed (ngrok fallback: see scripts/tunnel.md)."
  echo ">> Starting cloudflared tunnel on :$LOCAL_PORT (leave it running for the whole demo)…"
  nohup cloudflared tunnel --url "http://localhost:$LOCAL_PORT" > "$TUNNEL_LOG" 2>&1 &
  echo $! > "$TUNNEL_PID"
  PUBLIC_BASE_URL=""
  for _ in $(seq 1 40); do
    PUBLIC_BASE_URL="$(scrape_url)"; [ -n "$PUBLIC_BASE_URL" ] && break
    sleep 1
  done
  [ -n "$PUBLIC_BASE_URL" ] || die "Tunnel URL not seen within 40s — check $TUNNEL_LOG."
  echo ">> Tunnel up: $PUBLIC_BASE_URL  (pid $(cat "$TUNNEL_PID"); do NOT restart it)"
fi

export PUBLIC_BASE_URL="${PUBLIC_BASE_URL%/}"
upsert_env PUBLIC_BASE_URL "$PUBLIC_BASE_URL"

# --- provision (idempotent; full output shown for operator review) ---
echo ">> Running provisioning ($PY scripts/setup_agentphone.py)…"
SETUP_OUT="$(mktemp)"
if ! "$PY" scripts/setup_agentphone.py > "$SETUP_OUT" 2>&1; then
  cat "$SETUP_OUT" >&2
  die "Provisioning failed (see output above). Common cause: placeholder/empty AGENTPHONE_API_KEY → 401."
fi
cat "$SETUP_OUT"

# --- upsert the four returned IDs into .env ---
while IFS= read -r line; do
  upsert_env "${line%%=*}" "${line#*=}"
done < <(grep -E '^(ROBIN_AGENT_ID|FROM_NUMBER_ID|RECEPTIONIST_AGENT_ID|RECEPTIONIST_NUMBER_ID)=' "$SETUP_OUT")
rm -f "$SETUP_OUT"
echo ">> IDs written into .env (gitignored)."

# --- Task 3 Step 5 gate: .env MUST be gitignored ---
git check-ignore "$ENV_FILE" >/dev/null 2>&1 || die ".env is NOT gitignored — STOP, do not commit anything."
echo ">> .env is gitignored ✓"

cat <<'CHECKLIST'

──────────────────────────────────────────────────────────────────────
PROVISIONING DONE. Remaining Plan 05 steps are manual (operator):

[ ] Set RECEPTIONIST_TO_NUMBER in .env to the E.164 of the receptionist
    number shown in the AgentPhone dashboard, then re-source .env.

[ ] Task 3 Step 4 — recording add-on gate. Place ONE throwaway call,
    then (substitute the real call_id):
      curl -s -H "Authorization: Bearer $AGENTPHONE_API_KEY" \
        https://api.agentphone.ai/v1/calls/<call_id> | python3 -m json.tool
    Must show  "recordingAvailable": true  and a "recordingUrl".
    If false/absent → AgentPhone dashboard → add-ons → enable Recording.

[ ] Task 4 — phone RECEPTIONIST_TO_NUMBER. It must answer in-character
    as the 24 Hour Fitness receptionist (opens with the "in person only"
    block). 30-min fallback: point RECEPTIONIST_TO_NUMBER at a teammate's
    phone / local TTS reading src/robin/fixtures/prompts/receptionist.txt.

WATCH (Task 0 — unconfirmed in live llms-full.txt):
  • Receptionist persona: if it answers WITHOUT the 24HF script, the API
    ignored `systemPrompt` at agent-create → inject the persona via the
    outbound POST /v1/calls `systemPrompt` instead (that field IS
    confirmed). Single change point: scripts/setup_agentphone.py.
  • Webhook `timeout:120`: if the inbound turn dies ~30s mid Browser-Use
    research, the API ignored it → rely on Plan 03 keepalive interims.
──────────────────────────────────────────────────────────────────────
CHECKLIST
