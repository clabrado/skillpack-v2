---
name: eclaude
description: >-
  Open a brand-new Claude Code session in its own terminal window — fresh
  context, its own pseudo-terminal, its own latch id, independently watchable
  and steerable. Optional working directory and session name. Triggers -
  "eclaude", "open a new claude window", "launch another claude session",
  "spin up a fresh work stream", "new claude terminal in <repo>".
argument-hint: "[cwd] [--name NAME] [--no-latch] [--dry-run]"
---

# /eclaude — open a new Claude Code window

Starts a genuinely fresh session in its own window. It does **not** share this
session's context. Launched under latch, it registers in `latch ls` and can be
watched and typed into from anywhere — which is what makes `/steer`, `/drive`,
and any supervising session work against it.

## Invocation

```
/eclaude                            # new session in $HOME
/eclaude ~/Projects/thing           # new session, started in that directory
/eclaude ~/Projects/thing --name qa # …and named "qa", so you can refer to it later
/eclaude --no-latch                 # plain session, not watchable from outside
/eclaude --dry-run                  # print the command, open nothing
```

The first non-flag argument is the working directory. If the user gives a bare
word that is not an existing directory (`/eclaude qa`), treat it as `--name qa`
— the script exits non-zero on a directory that does not exist, and guessing
wrong wastes a launch.

## What to run

```bash
bin/eclaude.sh [CWD] [--name NAME]
```

from this repo, or from wherever it is installed. Map the user's words to those
arguments and run exactly that one command.

## After launching

**The script returns as soon as the window is open. It does not wait for the
session to come up, so its exit code says nothing about whether the session
started.** Confirm before reporting success:

```bash
latch ls
```

Report the new session's id and name. If it has not appeared, wait a few
seconds and check once more before calling it a failure — a session takes a
moment to boot and register.

## Things that will bite you

- **A brand-new session may stop on Claude Code's "do you trust this folder?"
  prompt.** It registers in `latch ls` and looks alive while doing nothing at
  all. Measured 2026-08-24. If a spawned session is registered but produces no
  output, check for that prompt before assuming it is working.
- **The spawned session inherits the caller's output stream** unless the
  launcher detaches it, so a naive spawn can hang the caller and flood it with
  the new session's display. `bin/eclaude.sh` opens a terminal window rather
  than inheriting, which avoids this — but any hand-rolled `latch run` in a
  script needs to handle it.
- **Permissions.** The session starts with `--dangerously-skip-permissions`,
  meaning it acts without stopping to ask. That is deliberate for an unattended
  worker you are supervising from outside. Say so plainly if asked; do not
  quietly drop the flag, and do not quietly keep it if the user wants it gone.
- **Without latch** the session still starts — you simply cannot type into it
  from another window. The script says so rather than failing silently.
- **Windows accumulate.** Each launch is a window that stays until closed. A
  fleet of them will eventually make the terminal application stop answering
  scripted requests. Close what you finish with.
