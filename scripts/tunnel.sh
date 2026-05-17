#!/usr/bin/env bash
# Robin demo tunnel — deterministic, stable ngrok static domain.
#
# One-time:  ngrok config add-authtoken <token>   (you run this)
# Every run: scripts/tunnel.sh                     (URL never changes)
#
# Reads NGROK_DOMAIN from the environment or arg 1. The webhook you
# register in AgentPhone is always:  https://$NGROK_DOMAIN/webhook
#
# Robin's port is 8080 (8000 is the unrelated Patter process).

set -euo pipefail

PORT="${PORT:-8080}"
DOMAIN="${1:-${NGROK_DOMAIN:-}}"

if [[ -z "${DOMAIN}" ]]; then
  echo "ERROR: no static domain. Pass it or set NGROK_DOMAIN." >&2
  echo "  scripts/tunnel.sh robin-xxxx.ngrok-free.app" >&2
  exit 1
fi

if ! ngrok config check >/dev/null 2>&1; then
  echo "ERROR: ngrok config invalid." >&2
  exit 1
fi

if ! grep -q authtoken \
  "$HOME/Library/Application Support/ngrok/ngrok.yml" 2>/dev/null; then
  echo "ERROR: no ngrok authtoken. Run:" >&2
  echo "  ngrok config add-authtoken <YOUR_TOKEN>" >&2
  exit 1
fi

echo "Robin tunnel → https://${DOMAIN}  (→ localhost:${PORT})"
echo "AgentPhone webhook URL:  https://${DOMAIN}/webhook"
echo "Ctrl-C to stop."
exec ngrok http "${PORT}" --url "https://${DOMAIN}" --log stdout
