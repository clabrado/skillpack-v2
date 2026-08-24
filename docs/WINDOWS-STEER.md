# What `/steer` needs to run on Windows

`/steer` is the one skill in this pack with a hard operating-system dependency.
This is the map of it, so the port is a piece of work rather than a mystery.

## The short version

**One file blocks it: `latch/latchlib/run.py`, 720 lines.** Everything else in
latch is portable Python and needs no change — the event stream, the HTTP
interface, the injector, the session registry, the steerer, and the decision
engine all work as-is.

`run.py` is the supervisor. It creates a pseudo-terminal, runs your agent inside
it, and forwards keystrokes both ways. Injecting text into a live session means
writing into that pseudo-terminal. Unix and Windows both have this facility;
they do not share an API.

## Exactly what is Unix-only

| Lines | What it does | Windows equivalent |
|---|---|---|
| 263 | `os.openpty()` — make the pseudo-terminal | ConPTY, via the `pywinpty` package |
| 268–273 | `os.fork()`, `os.setsid()`, `TIOCSCTTY` — run the child inside it | `pywinpty` spawns the child itself; there is no fork on Windows |
| 455–462 | `termios`/`tty` raw mode on the operator's own terminal | `msvcrt` character reads, or leave the console in its default mode |
| 482–492 | `SIGWINCH`, `SIGTERM`, `SIGHUP` | Windows console resize events; `SIGTERM` has no real equivalent |
| 511–519 | `select()` on the terminal handle | `pywinpty`'s own read API — `select` does not accept these handles on Windows |
| 675 | `TIOCSWINSZ` — tell the child the window resized | `pywinpty`'s `setwinsize()` |

Injection itself (`os.write` at 331) is a plain write to that handle and carries
over unchanged once the handle comes from ConPTY.

## The shape of the work

Put a small backend behind the parts above — one implementation using the Unix
calls, one using `pywinpty` — and have `run.py` pick at import. Nothing else in
the file, and nothing anywhere else in latch, should need to change. The
non-blocking write path and its byte-ceiling logic are already careful and are
worth preserving exactly: a blocking write in that spot wedged the whole system
once, and the comment at line 297 records it.

## What would prove it works

Not "it imports". The port is done when, on Windows:

1. `latch run -- claude` starts a session you can actually type in;
2. `latch ls` shows it from a *different* window;
3. `latch inject <id> "hello"` puts that text into the session;
4. resizing the window does not corrupt the display;
5. closing the session deregisters it rather than leaving a ghost.

Steps 2 and 3 are the whole point. A port that starts a session but cannot be
reached from outside has not delivered anything `/steer` needs.

## Honest status

**Not attempted.** This document was written on a Mac. Nothing here has been
run on Windows, and the line numbers are from the vendored copy in this repo at
the time of writing — check them against the file rather than trusting them.

Until then, Windows users get `/turbo`, `/standup`, `/readout`, `/sid` and
`/eclaude`. Those four goal-holding skills carry the pack; what Windows loses is
reaching into a session that is already running.
