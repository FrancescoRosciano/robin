# docs/RUNSHEET.md — Robin Stage Runsheet (the on-stage card)

> Pre-decided. Do not relitigate live. This is the **content checklist +
> timing**. The AV/projector wrapper (which tab, when to switch, PA
> setup) is owned by `docs/stage/av-runbook.md` — read that too.
> The combined rehearsal (this + the AV runbook) is the single gate
> before submission.
>
> **Median rehearsal duration: ___ min ___ sec**  ← fill in after the
> ×3 timed rehearsals (Plan 06 Task 8 Step 2).

---

## On-screen disclosure (must be visible during dial-out — Step 3 on)

> **CONTROLLED DEMO — Robin's side is fully live (real web research,
> real inbound discovery, real outbound call, real callback). The
> receptionist runs in a safe test environment — a briefed teammate —
> so no real business is contacted.** Both call sides are scripted and
> stated to be.

This is the honest disclosure: it frames the demo as a deliberate
controlled environment while keeping the substantive fact (the
receptionist is a briefed teammate, no real business is called). Do
**not** describe the receptionist as an "AI" or "AI simulation" — that
would be false (it is a human teammate); and do not drop the
controlled-environment disclosure entirely (concealing the teammate is
the disqualifying line per CLAUDE.md). Keep this legible on the
projector the entire time the outbound call is in progress.

---

## The 7-step runsheet (canonical — verbatim from CLAUDE.md)

| # | Step | Target time |
|---|------|-------------|
| **1** | Presenter calls Robin live on stage: *"I want to cancel my gym membership."* | 0:00–0:15 |
| **2** | Robin discovery: asks which gym → *"24 Hour Gym"*. Robin says it's looking it up, *"found their line, 415-776-2200 — want me to call and cancel for you?"* → presenter says yes. Browser Use really runs here: the number lookup is set-dressing; the **real payload is researching the cancellation laws** Robin will cite. | 0:15–1:15 |
| **3** | Robin dials out; the stage hears Robin vs the **24 Hour Gym receptionist, played by a briefed teammate on a real phone** (this is the demo design for this leg — a controlled test environment, not an AI agent). **Disclosure slide up** (see above): "CONTROLLED DEMO" — Robin live, receptionist = a briefed teammate in a safe test environment. | 1:15–1:45 |
| **4** | Both negotiate hard — escalating tone, hard lines, fast exchanges. Receptionist obstructs (in person / 50% off / certified letter / stalling). | 1:45–3:30 |
| **5** | Robin's close: cites the pre-vetted laws (X, Y, Z), then the ultimatum — *"Two options. Easy: cancel now, I leave you 5★ on Google. Hard: I escalate to your manager's manager, file a complaint that this retention process is misleading, demand compensation for the misleading offer, and post reviews everywhere. Your decision."* | 3:30–4:15 |
| **6** | Receptionist capitulates: *"Fine — I'll cancel your subscription and refund your last month."* | 4:15–4:30 |
| **7** | Robin reports back to the caller (same call / callback): cancelled + last-month refund + confirmation #. | 4:30–5:00 |

Times above are a target skeleton — replace with the **observed median**
from the ×3 rehearsals so the stage slot is known. The cited laws
(X, Y, Z) are pre-verified and hosted verbatim in
`src/robin/fixtures/law.html` — see `docs/legal-citations-verified.md`.

---

## If it breaks (pre-decided — do not invent new fallbacks live)

| Situation | Pre-decided response |
|---|---|
| **No API key by early afternoon** | Waves 1–2 done against fakes; the moment keys land → Plan 05 run → Plan 06. Escalate keys on Discord / on-site in parallel. |
| **Inbound DTMF unsupported** | Already shipped voice keyword ("say one / say two"). No call-bridging — do not attempt it live. |
| **Receptionist teammate unreachable / leg stalls** | Fall back to the recorded backup video for the negotiation leg (Plan 05 fixture fallback). The teammate is the design, the backup is the safety net. |
| **Live run drifts / negotiation overruns the slot** | Switch the projector to the recorded backup (`docs/demo-backup-recording.<ext>`) — the CONTINGENCY path in `docs/stage/av-runbook.md`. Return live for the callback. |
| **6:00 PM** | Feature freeze. Whatever is end-to-end is the demo. **If the recorded backup (Plan 06 Task 7) does not yet exist, stop everything and capture it now with whatever works.** |
| **Stage page blank / tunnel drop / call fails / callback silent** | See the operational failure table in `docs/stage/av-runbook.md` (Plan 07 owns the AV wrapper). |

> The recorded backup is the submission artifact **and** the stage
> safety net regardless of how the live run goes — it must already exist
> before the presenter walks on stage (Plan 06 Task 7 gate).
