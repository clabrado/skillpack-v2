#!/usr/bin/env bash
# eclaude.sh — open a brand-new Claude Code session in its own terminal window.
#
# The new session has its own context, its own pseudo-terminal, and its own
# latch id, so it can be watched and typed into from elsewhere. It is
# indistinguishable from a session you start by hand.
#
# Usage: eclaude.sh [cwd] [--name NAME] [--no-latch]
#
#   cwd         working directory for the new session (default: $HOME)
#   --name      latch session name, so you can refer to it by name later
#   --no-latch  launch without the supervisor (not watchable from outside)
#   --dry-run   print the command that would run, open nothing
#
# Binaries are resolved from PATH, then from ~/.local/bin. Nothing here is
# specific to one machine.
set -euo pipefail

CWD="$HOME"
NAME=""
USE_LATCH=1
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)     NAME="${2:-}"; shift 2 ;;
    --no-latch) USE_LATCH=0; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,14p' "$0"; exit 0 ;;
    *)          CWD="$1"; shift ;;
  esac
done

CWD="${CWD/#\~/$HOME}"
[[ -d "$CWD" ]] || { echo "eclaude: no such directory: $CWD" >&2; exit 1; }

find_bin() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then command -v "$name"; return 0; fi
  [[ -x "$HOME/.local/bin/$name" ]] && { echo "$HOME/.local/bin/$name"; return 0; }
  return 1
}

# claude-stable is a pinned build; plain claude is the normal name. Either works.
CLAUDE_BIN="$(find_bin claude-stable || find_bin claude || true)"
[[ -n "$CLAUDE_BIN" ]] || {
  echo "eclaude: no 'claude' or 'claude-stable' on PATH or in ~/.local/bin" >&2
  exit 1
}

if [[ "$USE_LATCH" == "1" ]]; then
  LATCH_BIN="$(find_bin latch || true)"
  if [[ -z "$LATCH_BIN" ]]; then
    echo "eclaude: latch not found — launching WITHOUT it." >&2
    echo "         The session will start, but nothing can type into it from" >&2
    echo "         another window. Install latch (see latch/ in this repo) or" >&2
    echo "         pass --no-latch to silence this." >&2
    USE_LATCH=0
  fi
fi

if [[ "$USE_LATCH" == "1" ]]; then
  ARGS=(run)
  [[ -n "$NAME" ]] && ARGS+=(--name "$NAME")
  ARGS+=(-- "$CLAUDE_BIN" --dangerously-skip-permissions)
  CMD="cd $(printf '%q' "$CWD") && $(printf '%q' "$LATCH_BIN")"
  for a in "${ARGS[@]}"; do CMD+=" $(printf '%q' "$a")"; done
else
  CMD="cd $(printf '%q' "$CWD") && $(printf '%q' "$CLAUDE_BIN") --dangerously-skip-permissions"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "$CMD"
  exit 0
fi

case "$(uname -s)" in
  Darwin)
    # Launch WITHOUT stealing focus. Terminal needs a moment at the front for
    # the window to open reliably, so remember what was frontmost and hand
    # focus straight back — a spawned window must never interrupt typing.
    osascript <<EOF
set prevApp to ""
try
  tell application "System Events" to set prevApp to name of first application process whose frontmost is true
end try
tell application "Terminal"
  activate
  do script "$CMD"
end tell
if prevApp is not "" and prevApp is not "Terminal" then
  try
    tell application prevApp to activate
  end try
end if
EOF
    ;;
  *)
    # No Terminal.app. Try the common Linux emulators, then fall back to
    # saying so plainly rather than silently doing nothing.
    for term in x-terminal-emulator gnome-terminal konsole xterm; do
      if command -v "$term" >/dev/null 2>&1; then
        "$term" -e bash -lc "$CMD" &
        echo "eclaude: opened a new $term window"
        echo "eclaude: verify with: latch ls"
        exit 0
      fi
    done
    echo "eclaude: no terminal emulator found. Run this yourself:" >&2
    echo "  $CMD" >&2
    exit 1
    ;;
esac

echo "eclaude: opened a new Terminal window running: $CMD"
echo "eclaude: verify registration with: latch ls"
