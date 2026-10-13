#!/usr/bin/env bash
# eclaude.sh — open a brand-new Claude Code session in its own terminal window.
#
# The new session has its own context, its own pseudo-terminal, and its own
# latch id, so it can be watched and typed into from elsewhere. It is
# indistinguishable from a session you start by hand.
#
# Usage: eclaude.sh [cwd] [--name NAME] [--fork F] [--no-latch] [--dry-run]
#
#   cwd         working directory for the new session (default: the
#               caller's current directory)
#   --name      latch session name, so you can refer to it by name later
#   --fork      config dir: default (~/.claude), a NAME (~/.claude-NAME), or a
#               path. Omitted, the caller's CLAUDE_CONFIG_DIR is inherited, so a
#               session spawned from a forked session stays on that fork.
#   --no-latch  launch without the supervisor (not watchable from outside)
#   --dry-run   print the command that would run, open nothing
#
# Binaries are resolved from PATH, then from ~/.local/bin. Nothing here is
# specific to one machine.
set -euo pipefail

CWD="$PWD"
NAME=""
USE_LATCH=1
DRY_RUN=0
# Inherit the caller's fork unless --fork says otherwise. Without this a session
# spawned from a ~/.claude-NAME session comes up on ~/.claude and uses the wrong
# config, MCP registrations, and folder-trust records.
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)     NAME="${2:-}"; shift 2 ;;
    --fork)
      case "${2:-}" in
        default) CONFIG_DIR="$HOME/.claude" ;;
        "")      echo "eclaude: --fork needs a value" >&2; exit 1 ;;
        *)
          case "$2" in
            */*|~*) CONFIG_DIR="${2/#\~/$HOME}" ;;
            *)      CONFIG_DIR="$HOME/.claude-$2" ;;
          esac
          # A bare existing directory is not proof of a config fork — claude
          # would silently scaffold a new one there and you would lose your
          # settings without an error. Require the marker file.
          [[ -f "$CONFIG_DIR/.claude.json" ]] || {
            echo "eclaude: $CONFIG_DIR has no .claude.json — not a config fork." >&2
            echo "         Use default, a fork NAME, or point at a real config dir." >&2
            exit 1
          } ;;
      esac
      shift 2 ;;
    --no-latch) USE_LATCH=0; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,17p' "$0"; exit 0 ;;
    *)          CWD="$1"; shift ;;
  esac
done

CWD="${CWD/#\~/$HOME}"
[[ -d "$CWD" ]] || { echo "eclaude: no such directory: $CWD" >&2; exit 1; }

if [[ -n "$CONFIG_DIR" ]]; then
  [[ -d "$CONFIG_DIR" ]] || {
    echo "eclaude: no such config directory: $CONFIG_DIR" >&2
    echo "         --fork takes default, a fork NAME, or a path that exists." >&2
    exit 1
  }
fi

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

# The new window is a fresh login shell, so the fork has to travel in the
# command itself — the caller's exported environment does not reach it.
ENV_PREFIX=""
[[ -n "$CONFIG_DIR" ]] && ENV_PREFIX="CLAUDE_CONFIG_DIR=$(printf '%q' "$CONFIG_DIR") "

if [[ "$USE_LATCH" == "1" ]]; then
  ARGS=(run)
  [[ -n "$NAME" ]] && ARGS+=(--name "$NAME")
  ARGS+=(-- "$CLAUDE_BIN" --dangerously-skip-permissions)
  CMD="cd $(printf '%q' "$CWD") && ${ENV_PREFIX}$(printf '%q' "$LATCH_BIN")"
  for a in "${ARGS[@]}"; do CMD+=" $(printf '%q' "$a")"; done
else
  CMD="cd $(printf '%q' "$CWD") && ${ENV_PREFIX}$(printf '%q' "$CLAUDE_BIN") --dangerously-skip-permissions"
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
    # The command is handed over as a temp SCRIPT, never interpolated into the
    # AppleScript source. Interpolating meant %q shell-escaping was re-read by
    # AppleScript, which has different escape rules: a space or quote in a path
    # was a syntax error, and a backslash silently collapsed into the wrong
    # directory. The temp path is mktemp-generated and therefore safe to inline.
    LAUNCHER="$(mktemp "${TMPDIR:-/tmp}/eclaude-launch.XXXXXX")"
    {
      echo '#!/usr/bin/env bash'
      echo "rm -f -- $(printf '%q' "$LAUNCHER")"
      echo "cd $(printf '%q' "$CWD") || exit 1"
      [[ -n "$CONFIG_DIR" ]] && echo "export CLAUDE_CONFIG_DIR=$(printf '%q' "$CONFIG_DIR")"
      if [[ "$USE_LATCH" == "1" ]]; then
        printf 'exec %q run' "$LATCH_BIN"
        [[ -n "$NAME" ]] && printf ' --name %q' "$NAME"
        printf ' -- %q --dangerously-skip-permissions\n' "$CLAUDE_BIN"
      else
        printf 'exec %q --dangerously-skip-permissions\n' "$CLAUDE_BIN"
      fi
    } > "$LAUNCHER"
    chmod +x "$LAUNCHER"

    osascript <<EOF
set prevApp to ""
try
  tell application "System Events" to set prevApp to name of first application process whose frontmost is true
end try
tell application "Terminal"
  activate
  do script "$LAUNCHER"
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
