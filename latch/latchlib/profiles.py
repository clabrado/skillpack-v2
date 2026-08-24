"""Target injection profiles.

A latch session may set `--profile <name>` to tell the injector how to safely
drive a *specific* target TUI. This is core latch concern (a supervisor that
types into arbitrary terminal UIs must know each target's key semantics — it is
terminfo, not coupling to a downstream product), so the table lives here rather
than being scattered as string-compares through inject.py.

Each profile is a dict of injector capability flags, merged over DEFAULT:

  esc_interrupt: bool
      True  → the injector may send a bare Esc to interrupt an in-flight turn
              (redirect/interrupt modes). Correct for Claude Code, whose TUI
              binds Esc to "interrupt generation".
      False → NEVER send a bare Esc. Some TUIs bind Esc to cancel/quit, so a
              stray Esc at a modal tears the session down (live-tested with
              Grok Build 2026-07-18: Esc at its "trust this directory?" prompt
              kills the process). redirect degrades to type+submit; interrupt
              becomes a no-op.

To add a target, add one row here — do not edit inject.py's logic. Profiles are
built-in by design; a future `~/.latch/profiles.toml` merge is the escape hatch
if operator-defined profiles are ever needed (not built — YAGNI until asked).
"""
from __future__ import annotations

DEFAULT: dict = {"esc_interrupt": True, "has_idle_signal": True}

PROFILES: dict[str, dict] = {
    # Grok Build's TUI binds Esc to cancel/quit, not interrupt-generation.
    "grok-build": {"esc_interrupt": False},
    # Generic interactive target: a REPL, an ncurses installer, a pager, an
    # ssh session at a prompt. We do NOT know what this program binds Esc to,
    # and the grok-build precedent shows the cost of guessing wrong (a stray
    # Esc at its trust-directory modal killed the process). So: assume the
    # dangerous case. `redirect` degrades to type+submit and `interrupt`
    # becomes a no-op; use an explicit `keys: [ctrl-c]` to interrupt instead,
    # which is universal on a PTY in a way that Esc is not.
    #
    # has_idle_signal=False is load-bearing and was found by an e2e test, not by
    # reading code: latch's idle state is driven by CLAUDE's event stream (turn
    # boundaries). A python REPL, an installer or a pager emits no such event, so
    # `when: "idle"` queues forever and the keystrokes never land — the inject
    # returns accepted+queued and silently does nothing. For these targets the
    # injector treats "idle" as "now".
    "tui": {"esc_interrupt": False, "has_idle_signal": False},
}


def get(name: str | None) -> dict:
    """Return the merged capability flags for a profile name (None → DEFAULT)."""
    return {**DEFAULT, **PROFILES.get(name or "", {})}
