"""AgentPhone NDJSON line helpers (interim keeps the turn open)."""
import json


def interim(text: str) -> str:
    return json.dumps({"text": text, "interim": True}) + "\n"


def final(text: str, *, hangup: bool = False) -> str:
    obj: dict = {"text": text}
    if hangup:
        obj["hangup"] = True
    return json.dumps(obj) + "\n"
