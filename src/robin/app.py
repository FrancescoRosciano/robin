"""FastAPI composition root: webhook + law fixture + health."""
import json

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from robin.loop import run_turn
from robin.signature import SignatureError, verify_signature


def build_app(*, secret: str, law_html_path: str, llm,
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
        try:
            verify_signature(raw, dict(request.headers), secret)
        except SignatureError:
            return JSONResponse({"detail": "invalid signature"},
                                status_code=401)
        payload = json.loads(raw)
        transcript = payload.get("data", {}).get("transcript", "")
        history = payload.get("recentHistory", [])

        async def stream():
            async for chunk in run_turn(transcript, history,
                                        system=system_prompt, llm=llm,
                                        tool_impls=tool_impls):
                yield json.dumps(chunk) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app
