---
name: sid
description: >-
  Print this session's identifier, its transcript file on disk, and the related
  identifiers (web session link, process id, scratchpad, child-session flag).
  Artifact only — no narration. Triggers: "/sid", "what is your sid", "what's
  the session id", "where is this transcript", "transcript path".
---

# /sid — this session's identity

Run the script and print its output:

```bash
bash ~/.claude/skills/sid/sid.sh
```

On Windows, run the PowerShell version instead — same output:

```powershell
powershell -NoProfile -File $HOME\.claude\skills\sid\sid.ps1
```

Report the block as-is. Do not paraphrase the paths, and do not add narration
unless Chris asks a follow-up.

## Why a script and not a guess

The session id comes from `CLAUDE_CODE_SESSION_ID`, which Claude Code exports
into every shell it spawns. That is authoritative.

**Never identify the session by finding the most recently modified `.jsonl` in
`~/.claude/projects/`.** Chris routinely runs concurrent sessions — latch
sessions, steered sessions, child sessions — so modification time identifies
whichever session wrote last, which is frequently not this one. That method is
wrong often enough to be worse than useless, because it fails silently and
plausibly.

## What it prints

- `SESSION ID` — from the environment, exact.
- `TRANSCRIPT` — `~/.claude/projects/<slug>/<sid>.jsonl`, where `<slug>` is the
  **launch** directory with `/` replaced by `-`. The launch directory is not
  always the current one, so the script tries the derived path first and then
  searches every project directory for the exact filename. Line count, size,
  and last-write time come from the file itself.
- `WEB SESSION`, `PID`, `SCRATCHPAD`, child-session note — printed only when the
  underlying value actually exists. An absent field is omitted, never invented.

## Failure behaviour (all three tested)

- **No `CLAUDE_CODE_SESSION_ID`** — says so plainly and exits 1. It does not
  fall back to guessing.
- **Unrelated working directory** — the derived path misses, the filename search
  finds it anyway.
- **Transcript genuinely absent** — reports a measured absence and says a
  brand-new session may not have been flushed to disk yet. Absence of the file
  is not a claim that the session is unrecorded.

## Not this skill

- Estate-wide status (services, board, git) → `/status`.
- Narrated status of the current work → `/readout`.
- Listing or managing other sessions → latch (`latch ls`).
