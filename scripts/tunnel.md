# Tunnel (HTTPS for the AgentPhone webhook)

cloudflared (preferred):
  cloudflared tunnel --url http://localhost:8000

Note the printed https URL → export it, do NOT restart the tunnel later
(prior-session lesson: ~12s cooldown + the webhook URL changes, breaking
the registered webhook). Keep this process running for the whole demo.

  export PUBLIC_BASE_URL="https://<the-printed-host>"

Fallback: `ngrok http 8000` → use the https forwarding URL.
Run the FastAPI server with:  uvicorn robin.app:app --port 8000
(see Plan 06 for the composed-app entrypoint).
