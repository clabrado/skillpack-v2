---
name: keep-awake
disable-model-invocation: true
description: >-
  Keep this Mac fully awake AND unlocked for a set number of hours - no system
  sleep, no display darkening, no disk spin-down, no screen saver, no automatic
  lock, no Wi-Fi idle disconnect. Takes an hours argument (default 8). Built for
  leaving a long unattended job or overnight agent run going without the screen
  locking. Auto-reverts when the timer expires; never weakens password-on-lock.
  Actions: start <hours>, status, stop. Triggers - "keep my mac awake", "don't
  let it sleep or lock", "stay awake/unlocked for N hours", "all-nighter for my
  agent", "caffeinate for the night", "stop it locking while X runs".
---

# /keep-awake - keep the Mac awake + unlocked for N hours

**macOS only** (`caffeinate`, `defaults`, `pmset`). Not installed on Windows.

Starts a detached `caffeinate -dimsu` that holds the **UserIsActive** assertion (the
flag macOS checks before starting the screen saver or auto-locking) and sets the screen
saver to **Never**. Everything auto-reverts when the timer runs out.

The screen-saver setting is a *persistent* per-user default, so the script stashes the
prior value in `~/.local/state/keep-awake/prev-idletime` and a detached **restore watcher**
puts it back when the caffeinate hold ends — on `stop` **or** on timer expiry. `status`
prints the current value, the restore target, and whether a watcher is attached.

**Suppressed for the duration only:** system sleep | display sleep / auto-darken |
disk spin-down | screen saver | automatic screen lock | Wi-Fi idle disconnect.

**Never touched:** your password-on-lock. Manual lock (Ctrl-Cmd-Q) still works and still
requires your password - only the *automatic idle* triggers are held off, until the
timer expires.

## How to run it

Backed by `keep-awake.sh` in this folder. Parse the hours from the user's request (default
to **8** if unstated), then run the matching action and relay the script's one-line
confirmation back. Don't re-explain unless asked.

| Intent | Command |
|---|---|
| Start for N hours | `bash ~/.claude/skills/keep-awake/keep-awake.sh <hours>` |
| Start, default 8h | `bash ~/.claude/skills/keep-awake/keep-awake.sh` |
| Check current state | `bash ~/.claude/skills/keep-awake/keep-awake.sh status` |
| Stop early / restore | `bash ~/.claude/skills/keep-awake/keep-awake.sh stop` |
| Adopt an orphaned hold | `bash ~/.claude/skills/keep-awake/keep-awake.sh attach [<idleTime>]` |

Accepts whole or fractional hours (`10`, `1.5`, `0.5`). Extract just the number from
phrases like "keep it awake for 10 hours" before passing it.

## Notes
- The script manages **its own** caffeinate via a pidfile (`~/.local/state/keep-awake/`),
  so `stop` only stops the one it started - it won't disturb other caffeinate holds.
- Re-running `start` replaces any prior keep-awake hold it owns (no stacking).
- **Keep the Mac plugged in** for long runs - since nothing sleeps, battery would drain.
- This is the *session* layer. The *persistent* baseline (never auto-sleep/darken/disk-sleep
  + tcpkeepalive on) is separate, survives reboots, and was applied once via
  `sudo pmset -a sleep 0 displaysleep 0 disksleep 0 powernap 0 tcpkeepalive 1`. `status`
  prints it for reference. To re-apply it on a fresh machine, run pmset under the macOS
  GUI admin-auth dialog: `osascript -e 'do shell script "/usr/bin/pmset -a ..." with administrator privileges'`.
- **`attach`** adopts a caffeinate hold started by an older copy of this script (one that
  left no watcher): it stashes a restore value, re-asserts screen-saver-never, and spawns
  the watcher. Pass an explicit `idleTime` (or `__unset__` to delete the override and fall
  back to the macOS default) when the true prior value is unrecoverable.
- **Reboot caveat:** a reboot kills both caffeinate and the watcher, so the screen-saver
  override would survive with nothing to revert it. `prev-idletime` persists on disk, so
  the recovery is just `keep-awake stop`. `status` flags this case (`restore watcher: NONE`).
- `KEEP_AWAKE_STATE_DIR` exists only to test this script against a scratch state dir —
  never point production at anything but the default.
- **Fixed defect, for the record:** the screen-saver `idleTime -int 0` write was never
  reverted by `stop` *or* expiry, so a single run disabled idle auto-lock permanently. Now
  stashed + restored by a watcher; all three paths (expiry, `stop`, unset-key round-trip)
  verified end-to-end.
