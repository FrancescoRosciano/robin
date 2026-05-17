"""Thin AgentPhone REST/SSE client. Interface frozen in the 00 doc."""
import json
from dataclasses import dataclass
from typing import AsyncIterator

import httpx


@dataclass(frozen=True)
class TranscriptTurn:
    role: str
    content: str
    created_at: str


class AgentPhoneClient:
    def __init__(self, api_key: str,
                 base_url: str = "https://api.agentphone.ai/v1") -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(30.0, read=None))

    async def place_call(self, *, agent_id: str, to_number: str,
                         initial_greeting: str, system_prompt: str,
                         from_number_id: str) -> str:
        r = await self._http.post("/calls", json={
            "agentId": agent_id, "toNumber": to_number,
            "initialGreeting": initial_greeting,
            "systemPrompt": system_prompt, "fromNumberId": from_number_id})
        r.raise_for_status()
        body = r.json()
        call_id = body.get("id") or body.get("callId")
        if not call_id:
            raise ValueError("AgentPhone /calls response missing call id")
        return call_id

    async def stream_transcript(self, call_id: str
                                ) -> AsyncIterator[TranscriptTurn]:
        async with self._http.stream(
                "GET", f"/calls/{call_id}/transcript/stream") as resp:
            resp.raise_for_status()
            event = ""
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    if event == "turn" and data:
                        d = json.loads(data)
                        yield TranscriptTurn(
                            role=d.get("role", ""),
                            content=d.get("content", ""),
                            created_at=d.get("createdAt", ""))
                    elif event == "ended":
                        return

    async def get_recording_url(self, call_id: str) -> str | None:
        r = await self._http.get(f"/calls/{call_id}")
        r.raise_for_status()
        return r.json().get("recordingUrl")
