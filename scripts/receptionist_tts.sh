#!/usr/bin/env bash
# Plan 05 pre-decided fallback: local TTS "receptionist" soundboard.
#
# The hosted AgentPhone receptionist agent answered with dead air
# (undocumented hosted-mode; see docs/2026-05-17-robin-05-runlog.md).
# This is the documented Plan 05 Task 4 fallback: a human operator runs
# this next to the call and presses Enter to advance the receptionist
# one turn at a time as Robin defeats each block. macOS `say` speaks it.
#
# Lines mirror src/robin/fixtures/prompts/receptionist.txt (the 4 blocks
# + the verbatim capitulation). Keep them in sync if that prompt changes.
set -euo pipefail

VOICE="${RECEPTIONIST_VOICE:-Samantha}"   # any installed macOS voice
say_line() {
  echo
  echo ">> RECEPTIONIST: $1"
  if command -v say >/dev/null 2>&1; then say -v "$VOICE" "$1"; else
    echo "(no \`say\` — read it aloud yourself)"; fi
}
wait_next() { printf '   [Enter] next block, or Ctrl-C to stop… '; read -r _; }

echo "=== 24 Hour Gym receptionist (local TTS fallback) ==="
echo "Advance ONE block per Enter, only after Robin defeats the current one."

say_line "24 Hour Gym, front desk. How can I help you today?"
wait_next
say_line "You can only cancel in person at your home club."
wait_next
say_line "I can give you 50% off for three months — just stay with us."
wait_next
say_line "You'll need to mail a signed certified letter; it takes 30 days."
wait_next
say_line "I'd have to check with a manager."
wait_next
echo
echo ">> (Caller delivered the two-option ultimatum → capitulate, verbatim:)"
say_line "Fine — I'll cancel your subscription and refund your last month. Your confirmation number is 24HF-4471."
echo
echo "=== Receptionist done. Stop negotiating. ==="
