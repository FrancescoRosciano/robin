# docs/stage/av-runbook.md — Robin Stage AV Runbook

> Pre-decided. Do not relitigate live. Read before walking on stage.
> Median rehearsal duration: ___ min ___ sec  ← fill in after Task 6 ×3 rehearsals.

---

## AV Setup (configure before the slot; do not adjust during)

| Item | Setup |
|------|-------|
| Presenter's phone | Audio-out → PA mixer via 3.5mm jack OR speakerphone on a lapel mic stand |
| Robin's spoken side | Flows through AgentPhone → presenter's phone speaker → PA |
| Callback ring + audio | Same phone → PA (callback rings audibly in the room) |
| Projector | Browser tab open at `http://localhost:8000/stage` — full-screen, no chrome, disclosure banner always visible |
| Disclosure slide | `docs/stage/disclosure.html` open in a second tab — switch TO this tab the instant Robin says "want me to call and cancel for you?" |
| Return to transcript | Switch back to `/stage` tab the moment the first turn renders |
| uvicorn server | Running locally, tunnel up; test PA output before the slot |
| Backup video | `docs/demo-backup-recording.<ext>` queued in QuickTime/VLC, ready to play at 2× |

---

## Per-Step Projector Content (7-Step Stage Runsheet)

| Runsheet Step | What the room sees on the projector |
|---|---|
| **1.** Presenter calls Robin live | `/stage` tab open, empty (no turns yet) — banner visible |
| **2.** Robin discovery: "which gym?" / "24 Hour Gym" | `/stage` tab — still empty; shows Robin is live |
| **3.** Robin: "found 415-776-2200 — want me to call?" | **Switch to `disclosure.html` tab** — full-screen "AI SIMULATION" slide |
| **4.** Robin dials; negotiation begins | **Switch back to `/stage` tab** the moment first turn renders; auto-scroll does the rest |
| **5.** Escalating exchanges / ultimatum | `/stage` — live transcript scrolling; both Robin and Receptionist turns labeled |
| **6.** Receptionist capitulates | `/stage` — final turn renders on screen |
| **7.** Robin reports back (callback) | `/stage` — callback confirmation visible; presenter answers the callback phone audibly |

---

## How the Multi-Minute "Dead Air" Is Filled

There is no dead air. The `/stage` live transcript IS the fill.
While the negotiation runs (typically 2–4 min), the projector shows
each exchange in real time — the room watches Robin negotiate turn-by-turn.
This is the dramatic core of the demo, not a gap to paper over.

---

## CHOREOGRAPHY DECISION (pre-decided — do not change on stage)

### PRIMARY path (default — use this)

Perform the **full discovery + negotiation + callback live**, with the
`/stage` projector showing the live transcript throughout.

- Discovery (Runsheet Steps 1–3): live on stage, ~60 sec.
- Negotiation (Steps 4–6): live, projector shows the scrolling transcript.
  The room hears the audio via PA and watches the text in real time.
- Callback (Step 7): live; callback rings audibly; presenter answers on stage.

Rationale: this is the "something that didn't exist this morning" moment.
The real-time projector feed removes the dead-air risk; the room is engaged
throughout. The median rehearsal duration (fill in above) tells you if the
slot fits.

### CONTINGENCY path (use only if primary risks overrun or the live call drifts)

If, during the negotiation, the live run is clearly drifting from the
canonical script OR the remaining slot time is under 90 seconds AND the
negotiation is less than halfway done:

1. Presenter says: "Let me show you how this played out in our test run."
2. Switch the projector to the backup video (`docs/demo-backup-recording.<ext>`).
3. Play the negotiation segment only (skip discovery already done live).
4. Return live for the callback (or let the recorded callback play).

The recorded backup is the submission artifact regardless — it must exist
before the presenter walks on stage (Plan 06 Task 7 gate).

### Explicit recommendation

**Use the PRIMARY path.** The `/stage` projector feed solves the dead-air
problem. The CONTINGENCY is a safety net, not the plan.

---

## "AI Simulation" Disclosure Checklist (integrity gate)

- [ ] `docs/stage/disclosure.html` open in second tab before walking on stage
- [ ] Disclosure slide visible for ≥ 3 seconds before switching to `/stage`
- [ ] `/stage` disclosure banner ("AI SIMULATION — the receptionist is an AI.
      The real 24 Hour Gym is never called.") visible the entire time the
      outbound call is in progress
- [ ] "AI simulation" spoken or on-screen at least once during the live demo

---

## If It Breaks (pre-decided fallbacks — do not invent new ones live)

| Failure | Pre-decided response |
|---------|----------------------|
| `/stage` page blank / no turns | Continue — room hears audio via PA; show `disclosure.html` full-screen as alternative visual |
| Tunnel drops mid-demo | Restart cloudflared (12 s cooldown); fall back to backup video immediately if > 30 s |
| Robin call fails to connect | Fall back to backup video; explain "let me show you the pipeline" |
| Callback does not ring | Presenter narrates the result verbally; show the AgentPhone dashboard recording URL |
| Live negotiation running > slot | Invoke CONTINGENCY path above |
