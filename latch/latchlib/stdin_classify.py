"""Classify raw stdin bytes: real keystrokes vs terminal-protocol replies.

WHY THIS EXISTS (STEER-02, 2026-08-03)

`run.py` used to call `injector.human_typed()` for ANY bytes read from stdin.
Bytes on stdin are NOT the same thing as keystrokes: a focused terminal
emits protocol traffic with no human involved —

  * focus in/out reports  ESC [ I / ESC [ O   (Claude Code's TUI enables focus
    reporting, so merely clicking on the window generates these)
  * SGR mouse reports     ESC [ < 35;10;3 M/m (any mouse motion over the window)
  * legacy mouse reports  ESC [ M <3 bytes>
  * CPR/DSR replies       ESC [ 12;40 R       (answer to a cursor-position query)
  * DA replies            ESC [ ? 1;2 c       (answer to a device-attributes query)
  * OSC replies           ESC ] 11;rgb:... BEL (answer to a colour query)
  * bracketed-paste guards ESC [ 200~ / ESC [ 201~

A focused-but-idle window therefore read as "a human is typing", which pinned
`last_human_input_at` and made latch refuse steer injections with 409
human_active — the parked-steer defect this ticket exists to fix.

INJECTION-DoS NOTE (stated deliberately): before this classifier, the flag was
reachable by the *steered session itself*. A session that writes `ESC[c` or a
DSR query to its own tty makes the TERMINAL answer on the supervisor's stdin,
which pinned `last_human_input_at` and locked the supervisor out of injecting.
That is an adversarial-payload path to disabling supervision, not just an
annoyance. Recognised replies no longer count as human.

HONEST LIMIT: an unrecognised reply sequence still counts as human. That is why
the drop path in the steerer had to die too — an item that cannot be classified
is DELAYED (queued, with a latch-enforced deadline), never discarded.
"""
from __future__ import annotations

import re

# Complete, recognisable terminal→application replies. Order inside the
# alternation does not matter (no two patterns share a prefix ambiguity that
# changes the match length).
_REPLY_RE = re.compile(
    rb"\x1b\[[IO]"                      # focus in / focus out
    rb"|\x1b\[<[0-9;]+[Mm]"             # SGR mouse
    rb"|\x1b\[M[\x00-\xff]{3}"          # legacy X10 mouse (3 payload bytes)
    rb"|\x1b\[[0-9]+;[0-9]+R"           # CPR / DSR cursor position report
    rb"|\x1b\[\?[0-9;]*c"               # DA (device attributes) reply
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC reply (BEL- or ST-terminated)
    rb"|\x1b\[20[01]~"                  # bracketed-paste guards
)

# A trailing fragment that could still GROW into one of the above on the next
# read. Anchored to end-of-buffer, so it only ever matches the tail.
_PARTIAL_RE = re.compile(
    rb"\x1b\[M[\x00-\xff]{0,2}$"        # legacy mouse missing payload bytes
    rb"|\x1b\[[0-9;?<]*$"               # CSI with parameters, no final byte yet
    rb"|\x1b\][^\x07\x1b]*$"            # OSC not yet terminated
    rb"|\x1b$"                          # bare ESC
)

# Cap on how much of an incomplete sequence we hold between reads. A human
# cannot type 64 bytes of a single escape sequence, and an unbounded carry
# would be a way to make arbitrary keystrokes invisible.
CARRY_MAX = 64


class StdinClassifier:
    """Stateful across reads, because an escape sequence can split across them.

    `feed(data) -> bool`: True iff, after removing recognised terminal replies
    and holding back an incomplete trailing sequence, any bytes remain. Those
    residual bytes are treated as a human at the keyboard.

    The caller still forwards the ORIGINAL bytes to the PTY untouched —
    classification only gates the human-active flag, never the data path.
    """

    def __init__(self) -> None:
        self._carry = b""

    def feed(self, data: bytes) -> bool:
        buf = self._carry + (data or b"")
        self._carry = b""
        if not buf:
            return False

        residual = _REPLY_RE.sub(b"", buf)

        m = _PARTIAL_RE.search(residual)
        if m:
            frag = residual[m.start():]
            if len(frag) <= CARRY_MAX:
                # hold it back — it may complete into a reply on the next read
                self._carry = frag
                residual = residual[: m.start()]
            # oversized fragment: refuse to swallow it, count it as human

        return len(residual) > 0
