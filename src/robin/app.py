"""FastAPI composition root: webhook + law fixture + health."""
import json
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from robin import obs
from robin.loop import run_turn
from robin.signature import MalformedJSONError, SignatureError, verify_signature

_log = logging.getLogger("uvicorn.error")

# Secure by default. Only a runtime env override (never committed, never in
# .env) may disable webhook signature verification — a documented demo-only
# escape hatch for when the upstream Svix signing secret cannot be pinned.
_SKIP_VERIFY = os.environ.get("ROBIN_SKIP_WEBHOOK_VERIFY") == "1"


def build_app(*, secret: str, law_html_path: str, llm: object,
              tool_impls: dict, system_prompt: str = "You are Robin.") -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/fixture/law.html")
    async def law():
        return FileResponse(law_html_path, media_type="text/html")

    @app.post("/webhook")
    async def webhook(request: Request):
        raw = await request.body()
        if _SKIP_VERIFY:
            _log.warning("ROBIN_SKIP_WEBHOOK_VERIFY=1 — webhook signature "
                         "NOT verified (demo runtime override only)")
        else:
            try:
                verify_signature(raw, dict(request.headers), secret)
            except SignatureError:
                return JSONResponse({"detail": "invalid signature"},
                                    status_code=401)
            except MalformedJSONError:
                return JSONResponse({"detail": "bad request"}, status_code=400)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse({"detail": "bad request"}, status_code=400)
        data = payload.get("data") or {}
        transcript = data.get("transcript", "") if isinstance(data, dict) else ""
        history = payload.get("recentHistory", [])
        call_id = data.get("callId") if isinstance(data, dict) else None
        obs.log_event("webhook", ap_event=payload.get("event"),
                       call_id=call_id,
                       transcript_type=type(transcript).__name__,
                       history=len(history) if isinstance(history, list)
                       else type(history).__name__)

        async def stream():
            async for chunk in run_turn(transcript, history,
                                        system=system_prompt, llm=llm,
                                        tool_impls=tool_impls,
                                        call_id=call_id):
                yield json.dumps(chunk) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app
