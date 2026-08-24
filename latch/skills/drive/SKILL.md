---
name: drive
description: "Type into a running interactive terminal program that the Bash tool cannot reach — a live REPL, an ncurses installer, a pager, a y/n prompt mid-command, an ssh session at a password-less prompt. Works only against sessions deliberately launched under latch (`latch run -- <program>`); unwrapped terminals are invisible and unreachable by design. Use when the user says 'drive that', 'answer that prompt', 'type this into <session>', or needs a stuck interactive program pushed forward. NOT for shell commands — use Bash for those."
argument-hint: "<sid|name> <text to type>  |  <sid|name> --keys enter,y  |  --list  |  <sid|name> --interrupt"
---

# /drive — type into a live interactive program

Bash runs a **fresh process with no controlling TTY**, so it structurally cannot
answer a prompt inside an already-running program. `/drive` can: it writes to the
PTY of a session latch is already wrapping.

## Before anything else — is there a target?

```
latch ls
```

Only sessions started under latch appear. **If the program the user means is not
in that list, it cannot be driven** — say so plainly rather than reaching for
another mechanism. The fix is to relaunch it wrapped:

```
latch run --name <name> --profile tui -- <program>
```

## Driving

```
# type text and submit
latch inject <sid|name> "the text to type"

# type without pressing enter
latch inject --no-submit <sid|name> "partial input"

# press keys — for menus, pagers, y/n prompts, ctrl-c
latch inject --keys enter <sid|name>
latch inject --keys y,enter <sid|name>
latch inject --keys down,down,enter <sid|name>
latch inject --keys ctrl-c <sid|name>
```

Available keys: `enter esc tab shift-tab space backspace up down left right home
end page-up page-down ctrl-c ctrl-d ctrl-z ctrl-r ctrl-l ctrl-u y n q`.
There is deliberately **no general character key** — `keys` mode cannot spell a
command, which is what keeps it outside the danger screen's blind spot.

## Rules that are not negotiable

- **Only when the user asks.** `latch inject` must never be called from a hook,
  from `/loop`, from cron or launchd, or from a background agent. The one
  pre-existing automated caller is the steerer, which the user launches himself.
  A new automated caller needs a ruling, not a good reason.
- **Never use this for shell commands.** If a shell would do, use Bash. `/drive`
  exists for the case Bash cannot reach, and using it as a shell wrapper drops
  every guarantee Bash gives you (exit codes, captured output, no PTY races).
- **Never type credentials.** Injected text is recorded in `~/.latch/audit.jsonl`.
  If a prompt wants a password, hand it back to the user — do not type it.
- **The 10-second human guard is real.** If the user has typed into that terminal
  in the last 10s, injection is refused with `human_active`. That is correct
  behaviour; wait, don't retry in a loop.

## The danger screen

Text payloads are screened against a case-insensitive denylist (`rm -rf`,
`find -delete`, `dd of=/dev/`, `mkfs`, `git reset --hard`, `git push --force`,
`curl|sh`, fork bombs, and similar). A refusal looks like:

```
{"accepted": false, "reason": "danger_screen:recursive force delete (rm -rf)"}
```

Override only when the user has explicitly asked for that exact command:

```
latch inject --force <sid|name> "..."
```

A forced injection is tagged as forced in the audit trail.

**Be honest about what this screen is: a tripwire, not a boundary.** It catches
the accident. It does not stop obfuscation (`$IFS`, base64-pipe-sh), and it
cannot stop *semantic laundering* — injecting innocent text that instructs the
target agent to run the destructive thing itself. The real boundary is that only
latch-wrapped sessions are reachable, that a human invoked this, that every
keystroke is audited, and that ctrl-c is always available.

## Interrupting

```
latch inject --keys ctrl-c <sid|name>     # universal on a PTY — prefer this
latch inject --mode interrupt <sid|name>  # bare Esc; profile-gated
```

`--mode interrupt` is a **no-op** on profiles with `esc_interrupt: false`
(`tui`, `grok-build`). That is deliberate: Grok Build binds Esc to cancel/quit,
and a stray Esc at its trust-directory modal killed the process in live testing.
When in doubt, send `ctrl-c`.

## What this is not

Driving another Claude session is **`/steer`**, not this. Two mechanisms that can
both type into the same agent is the two-tools-that-can-disagree pathology this
estate has ruled against. If the user wants a session supervised rather than
poked, use `/steer`.
