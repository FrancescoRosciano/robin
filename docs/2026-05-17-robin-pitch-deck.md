# Robin — Stage Pitch Deck (spec for a deck generator)

> **How to use this file:** feed it to a deck generator (Gamma /
> Claude / frontend-slides). It is the source of truth for *content
> and intent*. Each slide block gives the on-slide copy, visual
> direction, and the speaker notes (what is said out loud). The deck
> is **3 slides** — it is a launchpad for a live demo, not a pitch to
> be read. Slide 3 ends and the phone takes over.

---

## Deck meta (apply to all slides)

- **Format:** 16:9, projected on a stage. Read from the back of a room.
- **Tone:** confident, a little cheeky, fast. Comic-book sidekick
  energy without being childish. Robin is the sidekick; the audience
  member is the superhero.
- **Visual language:** dark cinematic background, one bold accent
  colour, huge type, almost no body text. One idea per slide. The
  presenter's voice carries the detail — the slide is the punchline,
  not the script.
- **Type:** oversized display headline; minimal supporting line.
  Nothing a person has to squint to read.
- **Motion (if supported):** a single hard cut or quick reveal per
  slide. No slow fades, no bullet-by-bullet builds.
- **Wordmark:** "Robin" present but understated on slides 1 and 3.

---

## Slide 1 — Hook

**Headline:**
> Every superhuman needs a sidekick.

**Reveal line (appears after a beat):**
> Meet **Robin**. Call it. Tell it what you want. Give it a number.
> It handles the rest.

**Visual direction:**
- Near-black stage. The line "Every superhuman needs a sidekick."
  dominates. On the reveal, "Robin" snaps in big with the accent
  colour; the three actions (*call it · tell it · give it a number*)
  sit small underneath as a single tight line.
- A subtle phone motif (a call connecting) — suggested, not literal
  clip-art.

**Speaker notes (say this):**
- "Every superhuman needs a sidekick." (beat)
- "This is yours. It's called Robin. You phone it, you tell it what
  you want, you hand it a number — and it goes and does the call you
  hate, for you."
- Keep it to ~10 seconds. Land the line, don't explain it. The demo
  explains it.

---

## Slide 2 — The waste

**Headline:**
> You will spend **[VERIFY: e.g. weeks]** of your life on hold.

**Supporting line:**
> T‑Mobile. Amazon. The gym. Insurance. Hold music. Transfers.
> "Please stay on the line."

**Emotional turn (final line, own beat):**
> You could have spent that time in Italy.

**Visual direction:**
- The big number / duration is the hero of the slide. The list of
  offenders (T‑Mobile, Amazon, gym, insurance) is small, grey,
  almost a mutter under the number.
- On the last line, the grey list drops away and "in Italy" lands
  warm — a hard tonal cut from grey bureaucracy to something you
  actually want. (Optional: a single warm Italy image vs. the grey
  hold-screen.)

**Speaker notes (say this):**
- "Add it up. The calls you don't want to make — T‑Mobile, Amazon,
  the gym, insurance — you'll spend **[number]** of your life on
  hold." 
- "That's not time you get back. You could have spent it in Italy."
- Deliver the last line dry, not sentimental. It's the setup for the
  flip on slide 3.

> **[VERIFY] before stage:** pick a number you can defend if a judge
> challenges it. A wrong stat at YC is a credibility hit. Options:
> (a) a sourced figure with the source ready to name; (b) a safe,
> obviously-honest framing like "weeks of your life" with no false
> precision. Do **not** invent a precise statistic. This is the only
> hard fact on the slide — get it right or make it deliberately soft.

---

## Slide 3 — Live demo (the launchpad)

**Headline:**
> Let's cancel my gym membership.

**Setup line:**
> New Year's resolution: get back to the gym. Reality: I haven't gone.
> So — let's cancel **24 Hour Gym**, and let Robin make the call.

**Persistent on-screen disclosure (must stay visible the entire time
the outbound call is in progress — verbatim from `docs/RUNSHEET.md`):**
> *The receptionist is a briefed teammate openly role-playing the
> 24 Hour Gym front desk — not an AI, and not the real company. The
> real 24 Hour Gym is never called. The pipeline is real: live web
> research, real inbound discovery, real outbound call. Both call
> sides are scripted and stated to be.*

**Visual direction:**
- Minimal. One line, then get out of the way — this slide exists for
  ~10 seconds before the phone takes over the room.
- The disclosure is a small, permanently legible footer band (not a
  popup) — readable from the back, but it never competes with the
  call audio for attention. It stays up through the whole dial-out
  and negotiation. Do **not** call the receptionist an "AI" anywhere
  on screen — it's a human teammate; that wording would be false.

**Speaker notes (say this, then go live):**
- "One of my New Year's resolutions was to start going to the gym
  again. I'm… not going. So let's cancel it — and I'm not going to
  sit on hold. Robin is."
- Then place the call to Robin live on stage and follow
  `docs/RUNSHEET.md` (the 7-step runsheet owns everything from here:
  discovery → dial-out → negotiation → callback). This deck's job is
  done the moment the call connects.
- **Post-demo verbal close (no slide — say it after Robin reports
  back):** "Cancelled. Last month refunded. Confirmation number on
  the line. I made one phone call and said what I wanted — Robin did
  the part nobody wants to do." Keep it to one breath; let the result
  on the call be the proof, not your summary.

---

## Optional 4th slide (only if a recorded backup replaces the live leg)

If the live negotiation is swapped for the recorded backup (per the
`docs/RUNSHEET.md` contingency table), add one closing card so the
talk still has an ending:

**Headline:**
> One call. Robin did the rest.

**Body:** the demo outcome — *cancelled · last month refunded ·
confirmation #* — as three short tokens, plus the GitHub repo / where
to find it. Keep the same disclosure footer if the recording is shown.

> Default is **3 slides**. This 4th card is a contingency ending, not
> part of the planned flow — only use it if the live demo is replaced
> by the recording.

---

## Build notes for the deck generator

- Three slides. Huge type, almost no body text, one idea per slide.
- Slides 1 and 2 are spoken over in ~10–15s each; slide 3 is on
  screen ~10s then stays as the disclosure-bearing backdrop for the
  whole live call.
- The only paragraph of text anywhere is the disclosure on slide 3 —
  it is a legal/integrity requirement, must be legible from the back,
  and must remain on screen for the full duration of the outbound
  call. Treat it as non-negotiable fixed furniture, not decoration.
- Do not add slides, agendas, team bios, or architecture diagrams.
  This is a demo launchpad, not a read-through pitch.
