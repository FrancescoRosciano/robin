# Browser Use (Cloud) — confirmed

Source of truth (read directly):
- Quickstart: https://docs.browser-use.com/cloud/quickstart
- Full LLM docs (read for depth): https://docs.browser-use.com/llms-full.txt
  (index: https://docs.browser-use.com/llms.txt)

## Why it's in Robin (mandatory)

Robin = a voice chief-of-staff that *acts*. AgentPhone gives it the
**phone** (call in, dial out). **Browser Use gives it the web** (click,
fill, navigate, order). The kickoff explicitly pitched the combo:
AgentPhone + Browser Use unlocks phone-gated web tasks (2FA, DoorDash).
Also a sponsor track: Browser Use prizes ($3k/2k/1k credits + AirPods).

## Auth
- API key from `https://cloud.browser-use.com/settings?tab=api-keys&new=1`
- Env: `BROWSER_USE_API_KEY` (**need this — second key to obtain**)

## SDK + minimal usage
- Python: `pip install browser-use-sdk`  (TS: `npm install browser-use-sdk`)
```python
from browser_use_sdk.v3 import AsyncBrowserUse
client = AsyncBrowserUse()                 # reads BROWSER_USE_API_KEY
result = await client.run("Go to <site> and do <task>; return <what>")
print(result.output)
```
TS: `import { BrowserUse } from "browser-use-sdk/v3"; await new BrowserUse().run("...")`

## Role in Robin's flow
- Discovery decides the channel(s): a **phone** task → AgentPhone
  `POST /v1/calls`; a **web** task → `client.run(<task>)`; a task needing
  both → run the web task, and when it hits a phone step (OTP, voice
  confirmation) hand that leg to AgentPhone.
- The outbound "execute" leg generalises: phone and/or web. The outcome
  classifier (DONE / NEEDS_APPROVAL / BLOCKED) consumes either a call
  transcript (AgentPhone SSE) or `result.output` (Browser Use).

## OPEN — confirm from llms-full.txt before relying on it
- Polling vs streaming, task status values, structured/JSON output schema.
- Live session / preview URL (can the human watch?).
- **Human-in-the-loop / pause for input** mid-task — this is the hook for
  the OTP/2FA handoff to AgentPhone. Critical for the combo demo; verify
  the exact mechanism (pause + resume with provided value).
- Concurrency / session reuse, cloud limits/pricing.

## Demo angle (strong, multi-sponsor)
"Call Robin → 'order my usual on DoorDash' → Robin runs Browser Use to
do the order → site asks for phone confirmation → Robin (AgentPhone)
handles the call → rings you back: done." Hits the AgentPhone grand prize
AND the Browser Use track. Keep it to ONE combo path; don't sprawl.
