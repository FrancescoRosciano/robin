"""Stage projector routes.

GET /stage       — serve the self-contained HTML projector page.
GET /stage/stream — SSE stream of TranscriptTurn events for the page JS.

Mount this router onto the main FastAPI app AFTER the broadcaster is
available. The broadcaster singleton is passed in via the factory so this
module stays testable without importing main.py.
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse

_STAGE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Robin — Live Negotiation</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0a0a; color: #f0f0f0; font-family: 'Segoe UI', system-ui, sans-serif; }

  #banner {
    position: fixed; top: 0; left: 0; right: 0;
    background: #b91c1c; color: #fff;
    text-align: center; font-size: 1.4rem; font-weight: 700;
    padding: 0.6rem 1rem;
    z-index: 100;
    letter-spacing: 0.04em;
  }

  #transcript {
    margin-top: 4rem; padding: 2rem;
    max-width: 900px; margin-left: auto; margin-right: auto;
  }

  .turn {
    margin-bottom: 1.8rem;
    padding: 1rem 1.4rem;
    border-radius: 0.6rem;
    font-size: 1.6rem;
    line-height: 1.5;
    max-width: 85%;
  }
  .turn.agent {
    background: #1e3a5f;
    border-left: 6px solid #3b82f6;
    margin-right: auto;
  }
  .turn.user {
    background: #1a3a1a;
    border-left: 6px solid #22c55e;
    margin-left: auto;
  }
  .turn .label {
    font-size: 0.85rem;
    font-weight: 600;
    opacity: 0.7;
    margin-bottom: 0.4rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
</style>
</head>
<body>
<div id="banner">
  AI SIMULATION &mdash; the receptionist is an AI.&nbsp;
  The real 24 Hour Fitness is never called.
</div>
<div id="transcript"></div>
<script>
  const transcript = document.getElementById('transcript');
  const es = new EventSource('/stage/stream');

  es.addEventListener('turn', function(e) {
    const data = JSON.parse(e.data);
    const div = document.createElement('div');
    div.className = 'turn ' + (data.role === 'agent' ? 'agent' : 'user');
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = data.role === 'agent' ? 'Robin' : 'Receptionist';
    const text = document.createElement('div');
    text.textContent = data.content;
    div.appendChild(label);
    div.appendChild(text);
    transcript.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  });

  es.onerror = function() {
    // reconnect is automatic with EventSource — no action needed
  };
</script>
</body>
</html>
"""


def make_stage_router(broadcaster) -> APIRouter:
    """Build the /stage router bound to the given TurnBroadcaster instance."""
    router = APIRouter()

    @router.get("/stage", response_class=HTMLResponse)
    async def stage_page():
        return HTMLResponse(content=_STAGE_HTML)

    @router.get("/stage/stream")
    async def stage_stream():
        """SSE endpoint: subscribe to the broadcaster, emit turn events."""
        q = broadcaster.subscribe()

        async def event_generator():
            try:
                while True:
                    try:
                        turn = await asyncio.wait_for(q.get(), timeout=15.0)
                        payload = json.dumps(
                            {"role": turn.role, "content": turn.content})
                        yield f"event: turn\ndata: {payload}\n\n"
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"   # keep the connection alive
            except asyncio.CancelledError:
                pass
            finally:
                broadcaster.unsubscribe(q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            })

    return router
