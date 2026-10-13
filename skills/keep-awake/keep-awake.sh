#!/usr/bin/env bash
#
# keep-awake — keep this Mac fully awake AND unlocked for a set number of hours.
#
# Suppresses (for the duration, then auto-reverts):
#   * system sleep            * display sleep / auto-darken
#   * disk spin-down          * screen saver
#   * automatic screen lock   * Wi-Fi idle disconnect
#
# Does NOT disable password-on-lock: manual lock (Ctrl-Cmd-Q) still works and
# still requires your password. Only the *automatic idle* triggers are held off,
# and only until the timer expires.
#
# Mechanism: a detached `caffeinate -dimsu` holding the UserIsActive assertion
# (the flag macOS checks before starting the screen saver / auto-lock), plus
# screen saver -> Never. No sudo required.
#
# The screen-saver idleTime change is a *persistent* per-user default, so it is
# stashed before being overwritten and restored when the caffeinate hold ends —
# whether that end is `stop` or the timer expiring, via a detached watcher.
# (Pre-2026-07-28 versions never restored it: one run disabled idle auto-lock
# permanently.)
#
# Usage:
#   keep-awake.sh [<hours>]        start (default 8)     e.g. keep-awake.sh 10
#   keep-awake.sh start [<hours>]  same as above
#   keep-awake.sh status           show current state (session + persistent config)
#   keep-awake.sh stop             stop early, restore normal sleep/lock
#   keep-awake.sh attach [<idle>]  adopt an already-running hold (see SKILL.md)

set -euo pipefail

# Override only for testing this script; production always uses the HOME path.
STATE_DIR="${KEEP_AWAKE_STATE_DIR:-${HOME}/.local/state/keep-awake}"
PIDFILE="${STATE_DIR}/pid"             # caffeinate pid holding the assertions
WATCHFILE="${STATE_DIR}/watcher"       # detached restore-watcher pid
ENDFILE="${STATE_DIR}/until"           # human-readable expiry
PREVFILE="${STATE_DIR}/prev-idletime"  # stashed screensaver idleTime, or __unset__
UNSET_SENTINEL="__unset__"
# macOS default screen-saver start delay; used only when no prior value survives.
DEFAULT_IDLETIME="${KEEP_AWAKE_DEFAULT_IDLETIME:-1200}"
mkdir -p "$STATE_DIR"

_alive()    { [ -f "$PIDFILE" ]   && ps -p "$(cat "$PIDFILE" 2>/dev/null)"   >/dev/null 2>&1; }
_watching() { [ -f "$WATCHFILE" ] && ps -p "$(cat "$WATCHFILE" 2>/dev/null)" >/dev/null 2>&1; }

# --- screen saver idleTime: stash / suppress / restore -----------------------

_read_idletime() {
  defaults -currentHost read com.apple.screensaver idleTime 2>/dev/null || echo "$UNSET_SENTINEL"
}

# Never overwrite an existing stash with our own suppressed 0 — that would lose
# the real prior setting across a re-start.
_stash_idletime() {
  [ -s "$PREVFILE" ] && return 0
  local cur; cur=$(_read_idletime)
  if [ "$cur" = "0" ]; then
    # Already suppressed by an earlier run with no stash: no true prior value to
    # recover, so fall back to the macOS default rather than leaving it at 0.
    printf '%s\n' "$DEFAULT_IDLETIME" > "$PREVFILE"
  else
    printf '%s\n' "$cur" > "$PREVFILE"
  fi
}

_suppress_idletime() {
  defaults -currentHost write com.apple.screensaver idleTime -int 0 2>/dev/null || true
}

_restore_idletime() {
  [ -s "$PREVFILE" ] || return 0
  local prev; prev=$(cat "$PREVFILE" 2>/dev/null || echo "")
  if [ "$prev" = "$UNSET_SENTINEL" ] || [ -z "$prev" ]; then
    defaults -currentHost delete com.apple.screensaver idleTime 2>/dev/null || true
  else
    defaults -currentHost write com.apple.screensaver idleTime -int "$prev" 2>/dev/null || true
  fi
  rm -f "$PREVFILE" 2>/dev/null || true
}

# --- watcher -----------------------------------------------------------------

# Polls the caffeinate pid; when it is gone (timer expired, killed, crashed),
# restores idleTime. Idempotent with `stop`.
_watch() {
  local pid="${1:?_watch needs a pid}"
  while ps -p "$pid" >/dev/null 2>&1; do sleep 20; done
  _restore_idletime
  rm -f "$PIDFILE" "$ENDFILE" "$WATCHFILE" 2>/dev/null || true
}

_spawn_watcher() {
  nohup "$0" _watch "$1" >/dev/null 2>&1 &
  local wpid=$!
  disown 2>/dev/null || true
  echo "$wpid" > "$WATCHFILE"
}

# --- actions -----------------------------------------------------------------

# Tear down WITHOUT restoring — used by `start` when replacing its own hold, so
# the outgoing watcher cannot race the incoming suppression.
_teardown_quiet() {
  if _watching; then kill "$(cat "$WATCHFILE")" 2>/dev/null || true; fi
  if _alive;    then kill "$(cat "$PIDFILE")"   2>/dev/null || true; fi
  rm -f "$PIDFILE" "$ENDFILE" "$WATCHFILE" 2>/dev/null || true
}

stop() { _teardown_quiet; _restore_idletime; }

start() {
  local hours="${1:-8}"
  if ! printf '%s' "$hours" | grep -Eq '^[0-9]+([.][0-9]+)?$'; then
    echo "keep-awake: hours must be a positive number (got '$hours')" >&2; exit 2
  fi
  local secs; secs=$(awk -v h="$hours" 'BEGIN{printf "%d", h*3600}')
  if [ "${secs:-0}" -le 0 ]; then echo "keep-awake: hours must be > 0" >&2; exit 2; fi

  _stash_idletime   # capture the real prior value BEFORE teardown/suppress
  _teardown_quiet   # replace any prior keep-awake this script owns (no stacking)
  _suppress_idletime

  nohup caffeinate -dimsu -t "$secs" >/dev/null 2>&1 &
  local pid=$!
  disown 2>/dev/null || true

  if ! ps -p "$pid" >/dev/null 2>&1; then
    _restore_idletime
    echo "keep-awake: caffeinate failed to start" >&2; exit 1
  fi

  echo "$pid" > "$PIDFILE"
  local endts; endts=$(( $(date +%s) + secs ))
  date -r "$endts" "+%Y-%m-%d %H:%M" > "$ENDFILE" 2>/dev/null || true
  local restore_to; restore_to=$(cat "$PREVFILE" 2>/dev/null || echo '?')
  _spawn_watcher "$pid"

  local hdisp; hdisp=$(awk -v h="$hours" 'BEGIN{printf (h==int(h))?"%d":"%g", h}')
  local until_str; until_str=$(cat "$ENDFILE" 2>/dev/null || true)
  echo "keep-awake: ON for ${hdisp}h${until_str:+ (until ${until_str})} - pid ${pid}"
  echo "  no sleep | no display-off | no disk-sleep | no screen saver | no auto-lock"
  echo "  on stop or expiry: screen saver idleTime -> ${restore_to} (watcher pid $(cat "$WATCHFILE"))"
  echo "  stop early: keep-awake stop"
}

# Adopt a hold started by an older copy of this script: stash a restore value and
# attach a watcher, so expiry reverts the screen saver instead of leaving it off.
attach() {
  if ! _alive; then
    echo "keep-awake: nothing to attach to (no live hold in $PIDFILE)" >&2; exit 1
  fi
  local pid; pid=$(cat "$PIDFILE")
  if [ -n "${1:-}" ]; then printf '%s\n' "$1" > "$PREVFILE"; else _stash_idletime; fi
  _suppress_idletime   # the adopted hold's contract includes screen saver -> never
  if _watching; then kill "$(cat "$WATCHFILE")" 2>/dev/null || true; fi
  _spawn_watcher "$pid"
  echo "keep-awake: attached watcher $(cat "$WATCHFILE") to caffeinate pid ${pid}"
  echo "  on stop or expiry: screen saver idleTime -> $(cat "$PREVFILE")"
}

status() {
  if _alive; then
    local pid; pid=$(cat "$PIDFILE")
    local until_str; until_str=$(cat "$ENDFILE" 2>/dev/null || true)
    local el; el=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
    echo "keep-awake: ON - pid ${pid}${until_str:+, until ${until_str}}${el:+, elapsed ${el}}"
    echo "  session assertions held:"
    pmset -g assertions | grep -E "\b${pid}\b" | sed 's/^[[:space:]]*/    /' || true
  else
    echo "keep-awake: OFF (no session hold active)"
    rm -f "$PIDFILE" "$ENDFILE" 2>/dev/null || true
  fi
  echo "  screen saver idleTime now: $(_read_idletime)   (0 = never)"
  if _watching; then
    echo "  restore watcher: pid $(cat "$WATCHFILE") -> idleTime $(cat "$PREVFILE" 2>/dev/null || echo '?') on stop/expiry"
  elif _alive; then
    echo "  restore watcher: NONE - expiry will NOT revert the screen saver (run: keep-awake attach)"
  fi
  echo "  persistent power config (pmset -g custom):"
  pmset -g custom \
    | grep -E '(Battery|AC) Power:|^[[:space:]]+(displaysleep|disksleep|sleep|powernap|tcpkeepalive)[[:space:]]' \
    | sed 's/^/    /' || true
}

cmd="${1:-start}"
case "$cmd" in
  stop)   stop; echo "keep-awake: OFF - normal sleep/lock behavior restored.";;
  status) status;;
  start)  start "${2:-8}";;
  attach) attach "${2:-}";;
  _watch) _watch "${2:?}";;
  *)
    if printf '%s' "$cmd" | grep -Eq '^[0-9]+([.][0-9]+)?$'; then
      start "$cmd"
    else
      echo "usage: keep-awake.sh [<hours> | start <hours> | stop | status | attach [idle]]   (default 8h)" >&2
      exit 2
    fi
  ;;
esac
