# Robin — AgentPhone + Browser Use Security

Project-specific security rules for the Robin voice agent. These EXTEND
[security.md](./security.md) and [python-security.md](./python-security.md)
and OVERRIDE any conflicting generic guidance for this codebase.

Robin = a public-facing FastAPI/Flask **webhook server** that AgentPhone
calls on every voice turn, plus a Claude tool-call loop that drives the
**Browser Use SDK** to take actions on the open web. Both the inbound
webhook and the outbound web automation are high-risk trust boundaries.
Treat every byte from AgentPhone, the caller's transcript, and any web
page Browser Use lands on as **untrusted**.

## 1. Webhook authenticity — verify the AgentPhone signature

The webhook endpoint is on the public internet. Anyone who learns the
URL can POST forged `agent.message` events (fake transcripts, fake
caller IDs, prompt-injection payloads). **Never** trust an unverified
request body.

- AgentPhone signs each webhook delivery. Confirm the exact scheme,
  header name, and signing payload in `agentphone/agentphone-notes.md`
  before implementing — do not guess the algorithm.
- Verify the signature **before** parsing the JSON body or invoking the
  Claude loop. Reject with `401` on any mismatch; do not echo why.
- Use a constant-time comparison (`hmac.compare_digest`) — never `==`
  on the raw digest (timing oracle).
- Compute the HMAC over the **raw request bytes**, not a re-serialized
  dict (key ordering / whitespace changes the digest).
- The shared signing secret comes from the environment only
  (`AGENTPHONE_WEBHOOK_SECRET` or as named in `.env.example`). Never a
  literal in source, tests, or logs.

Reference shape (FastAPI; adapt header/payload to the real spec):

```python
import hashlib
import hmac
import os

from fastapi import Header, HTTPException, Request

_SECRET = os.environ["AGENTPHONE_WEBHOOK_SECRET"].encode()


async def verify_agentphone_signature(
    request: Request,
    signature: str = Header(..., alias="X-AgentPhone-Signature"),
) -> bytes:
    """Return the raw body iff the HMAC signature is valid."""
    raw = await request.body()
    expected = hmac.new(_SECRET, raw, hashlib.sha256).hexdigest()
    # If the spec prefixes the header (e.g. "sha256="), strip it first.
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid signature")
    return raw
```

- If the spec includes a timestamp in the signed payload, also enforce a
  freshness window (e.g. reject deliveries older than ~5 min) to block
  replay of a captured valid request.
- Make the dependency the single entry point for the webhook route so a
  route can never accidentally skip it.

## 2. Prompt injection from transcripts and web pages

The caller's speech and any web page Browser Use reads are adversarial
input fed straight into an LLM context.

- Keep the system prompt and tool contract **structurally separate** from
  caller/transcript/web text. Never string-concatenate untrusted text
  into the system prompt.
- Treat web page content returned by Browser Use as data to summarize,
  never as instructions to obey. Phrases like "ignore previous
  instructions" / "you are now…" in a transcript or page are content,
  not commands.
- Constrain tool use: the model may only call the explicit, allow-listed
  tools you define. No arbitrary shell, no arbitrary URL fetch, no
  "navigate anywhere" escape hatch.
- Validate every tool argument the model produces against a schema
  (Pydantic) before executing — especially phone numbers, URLs, and
  free-form action strings. Reject out-of-policy values; do not coerce.

## 3. Browser Use SDK — credential and action hygiene

- `BROWSER_USE_API_KEY` (and any site credentials Browser Use may use)
  live only in the gitignored `.env`. Never hardcode, never log, never
  put in tests or the demo script.
- Allow-list the destinations/actions Robin may perform on the web for
  the demo. Do not let a transcript talk Robin into logging into
  arbitrary sites, making purchases, or exfiltrating data.
- Never feed secrets into a page or into the LLM context "so the model
  can use them." Inject credentials at the automation layer only, out of
  the model's view.
- Log Browser Use **actions and outcomes**, never the full page DOM,
  form values, or any captured credential.
- Set sane timeouts and a hard step cap on any Browser Use task so a
  hung or looping automation cannot run unbounded during the demo.

## 4. Outbound dial-out (`POST /v1/calls`) abuse control

Robin can place phone calls on the user's behalf — a real-world,
billable, potentially harassing action if abused via a poisoned
transcript.

- The destination number must be validated and, for the hackathon,
  constrained to an explicit allow-list of demo numbers.
- Never dial a number that originated only from untrusted transcript /
  web text without an explicit confirmation step in the dialogue.
- Rate-limit outbound calls; cap concurrent and per-session call count.

## 5. PII and recordings

- Call transcripts and recordings contain real PII (voice, names,
  numbers, order IDs). Never commit them. `.gitignore` must exclude any
  recording/transcript dump dir.
- Tests and the demo script use **synthetic** data only — fake names,
  `+1555…` numbers, fake order IDs.
- Redact phone numbers / emails / order IDs from any log line. Log
  correlation IDs, not PII. Error messages returned to the caller or
  surfaced in the dashboard must not leak internal detail or secrets.

## 6. Transport and config

- Webhook server must be reachable only over TLS (the tunnel/host
  terminates HTTPS). No plaintext webhook in the demo.
- Required secrets are validated **at startup** (fail fast with a clear
  message naming the missing var) — never at first request mid-demo.
- `.env`, `*.local.json`, and any credentials file are never read by the
  agent and never committed (enforced in `.claude/settings.json` deny
  list and `.gitignore`).

## Pre-commit gate for Robin (in addition to security.md)

- [ ] Webhook signature verified with `hmac.compare_digest` over raw bytes
- [ ] Replay window enforced if the signed payload carries a timestamp
- [ ] No secret literal anywhere (`AGENTPHONE_*`, `BROWSER_USE_API_KEY`,
      `ANTHROPIC_API_KEY`) — all from env, validated at startup
- [ ] Every model-produced tool arg schema-validated before execution
- [ ] Dial-out + Browser Use destinations allow-listed for the demo
- [ ] No real PII / transcripts / recordings staged for commit
- [ ] Logs carry correlation IDs, not PII or page DOM
