---
name: eclaude
description: >-
  Open a brand-new Claude Code session in its own terminal window — fresh
  context, its own pseudo-terminal, its own latch id, independently watchable
  and steerable. Optional working directory and session name. Triggers -
  "eclaude", "open a new claude window", "launch another claude session",
  "spin up a fresh work stream", "new claude terminal in <repo>".
argument-hint: "[cwd] [--name NAME] [--fork default|NAME|PATH] [--no-latch] [--dry-run]"
---

# /eclaude — open a new Claude Code window

Starts a genuinely fresh session in its own window. It does **not** share this
session's context. Launched under latch, it registers in `latch ls` and can be
watched and typed into from anywhere — which is what makes `/steer`, `/drive`,
and any supervising session work against it.

## Default behaviour — just launch

`/eclaude` with no arguments means: open a new window in **the directory this
session is in**, no questions asked. Do not ask which directory, do not ask for
a name, do not offer options — run the command. Only read the flags below when
the user actually supplies an argument.

## Invocation

```
/eclaude                            # new session in the CURRENT directory — just launch it
/eclaude ~/Projects/thing           # override: start it in that directory instead
/eclaude ~/Projects/thing --name qa # …and named "qa", so you can refer to it later
/eclaude --no-latch                 # plain session, not watchable from outside
/eclaude --fork NAME                # session on the ~/.claude-NAME config dir
/eclaude --dry-run                  # print the command, open nothing
```

**Config forks.** With no `--fork`, the new session inherits the caller's
`CLAUDE_CONFIG_DIR`, so a session spawned from a forked config stays on it.
Pass `--fork default` (`~/.claude`), `--fork NAME` (`~/.claude-NAME`), or a
path to override. Most people run one config and never need this. This matters beyond
tidiness: folder-trust records, MCP registrations, and settings all live in the
config dir, so the wrong fork means a session that trusts nothing it should.

The first non-flag argument is the working directory; omitted, it is the
current directory. If the user gives a bare word that is not an existing
directory (`/eclaude qa`), treat it as `--name qa`
— the script exits non-zero on a directory that does not exist, and guessing
wrong wastes a launch.

## What to run

```bash
bin/eclaude.sh [CWD] [--name NAME] [--fork default|NAME|PATH]
```

With no CWD argument the script uses the caller's current directory, which is
what a bare `/eclaude` should do — so run it bare.

Run it from this repo, or from wherever it is installed. Map the user's words to those arguments and run
exactly that one command.

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
  all — `idle=True` with `claude=-` (no session id yet) is the tell. Measured
  2026-08-24, reproduced 2026-08-26. A directory is trusted per config fork, so
  a fork that has never opened that directory prompts every single time, and
  `$HOME` is commonly untrusted in every fork. `latch ls` alone will not tell
  you; read the window instead:

  ```bash
  # window 1 is NOT reliably the new one — the launcher hands focus back, so
  # an older window is often frontmost. Search every window instead:
  osascript -e 'tell application "Terminal" to get contents of tabs of windows' \
    | tr ',' '\n' | grep -i "trust this folder" && echo "STUCK ON TRUST PROMPT"
  ```

  Registration also lags the launch by several seconds — check twice, a few
  seconds apart, before calling a launch failed.
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
