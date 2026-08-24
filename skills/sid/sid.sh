#!/bin/bash
# /sid — print this session's id, transcript path, and related identifiers.
# Authoritative source is CLAUDE_CODE_SESSION_ID, exported by Claude Code into
# every shell it spawns. Never guess from "newest .jsonl" — concurrent sessions
# in this estate make modification time an unreliable identifier.
set -uo pipefail

SID="${CLAUDE_CODE_SESSION_ID:-}"
PROJECTS="$HOME/.claude/projects"

if [ -z "$SID" ]; then
  echo "SESSION ID:  unavailable — CLAUDE_CODE_SESSION_ID is not set in this shell."
  echo "             (Not running under Claude Code, or the variable was stripped.)"
  exit 1
fi

echo "SESSION ID:  $SID"

# Transcript lives at ~/.claude/projects/<slug>/<sid>.jsonl, where <slug> is the
# launch directory with '/' replaced by '-'. The launch cwd is not necessarily the
# current cwd, so try the derived path first, then search every project dir.
SLUG="$(echo "$PWD" | sed 's#/#-#g')"
CAND="$PROJECTS/$SLUG/$SID.jsonl"
TRANSCRIPT=""

if [ -f "$CAND" ]; then
  TRANSCRIPT="$CAND"
else
  TRANSCRIPT="$(find "$PROJECTS" -maxdepth 2 -name "$SID.jsonl" -type f 2>/dev/null | head -1)"
fi

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  SIZE="$(du -h "$TRANSCRIPT" | cut -f1 | tr -d ' ')"
  LINES="$(wc -l < "$TRANSCRIPT" | tr -d ' ')"
  MTIME="$(date -r "$TRANSCRIPT" -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)"
  echo "TRANSCRIPT:  $TRANSCRIPT"
  echo "             $LINES lines, $SIZE, last written $MTIME"
else
  echo "TRANSCRIPT:  not found on disk for $SID"
  echo "             searched $PROJECTS (depth 2). A brand-new session may not"
  echo "             have been flushed to disk yet — this is a measured absence,"
  echo "             not proof the session is unrecorded."
fi

# Optional extras — printed only when actually present, never invented.
[ -n "${CLAUDE_CODE_BRIDGE_SESSION_ID:-}" ] && \
  echo "WEB SESSION: https://claude.ai/code/${CLAUDE_CODE_BRIDGE_SESSION_ID}"
[ -n "${CLAUDE_PID:-}" ] && echo "PID:         ${CLAUDE_PID}"
[ "${CLAUDE_CODE_CHILD_SESSION:-0}" = "1" ] && \
  echo "NOTE:        this is a CHILD session (spawned by another Claude session)."

SCRATCH="/private/tmp/claude-501/$(basename "$(dirname "${TRANSCRIPT:-/x/y}")")/$SID/scratchpad"
[ -d "$SCRATCH" ] && echo "SCRATCHPAD:  $SCRATCH"
exit 0
