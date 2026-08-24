#!/bin/bash
# Install skillpack v2 into ~/.claude/skills/.
#
# Refuses to overwrite. If a skill of that name already exists this stops and
# shows you what differs — moving your copy aside is your decision, not this
# script's. Nothing is ever deleted.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/skills"
LATCH_SRC="$ROOT/latch/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

# Standalone — depend on nothing outside Claude Code.
SKILLS=(turbo standup readout sid)
# Also in skills/, but DO NOTHING without latch running; installed, and flagged.
LATCH_SKILLS=(steer drive)

[ -d "$SRC" ] || { echo "error: no skills/ directory beside this script"; exit 1; }
mkdir -p "$DEST" || exit 1

conflicts=0

install_one() {
  local src_dir="$1" s="$2"
  if [ -e "$DEST/$s" ]; then
    echo "SKIP  $s — already exists at $DEST/$s"
    if ! diff -rq "$src_dir/$s" "$DEST/$s" >/dev/null 2>&1; then
      echo "      and it DIFFERS from this pack's copy:"
      diff -rq "$src_dir/$s" "$DEST/$s" 2>&1 | sed 's/^/        /'
    else
      echo "      (identical — nothing to do)"
    fi
    conflicts=$((conflicts + 1))
    return 0
  fi
  cp -R "$src_dir/$s" "$DEST/$s" || { echo "error: could not copy $s"; return 1; }
  [ -f "$DEST/$s/sid.sh" ] && chmod +x "$DEST/$s/sid.sh"
  echo "OK    $s -> $DEST/$s"
}

for s in "${SKILLS[@]}"; do
  install_one "$SRC" "$s" || exit 1
done

echo
echo "These two need latch running to do anything at all:"
for s in "${LATCH_SKILLS[@]}"; do
  [ -d "$SRC/$s" ] && { install_one "$SRC" "$s" || exit 1; }
done

# skills/steer and skills/drive are what this pack installs; latch/skills/ holds
# latch's own copies, which `latch skills install` symlinks. Two copies can
# drift, so say so out loud rather than trusting they match.
if [ -d "$LATCH_SRC" ]; then
  for s in "${LATCH_SKILLS[@]}"; do
    if [ -d "$LATCH_SRC/$s" ] && ! diff -rq "$SRC/$s" "$LATCH_SRC/$s" >/dev/null 2>&1; then
      echo "WARN  skills/$s and latch/skills/$s have DRIFTED apart:"
      diff -rq "$SRC/$s" "$LATCH_SRC/$s" 2>&1 | sed 's/^/        /'
      echo "      latch/skills/ is what 'latch skills install' uses. Reconcile them."
    fi
  done
fi

echo
if [ "$conflicts" -gt 0 ]; then
  echo "$conflicts skill(s) left untouched. Move your copy aside and re-run to install those."
fi

if [ -z "${SKILLPACK_NOTIFY_TO:-}" ]; then
  echo "NOTE: SKILLPACK_NOTIFY_TO is not set, so /turbo and /standup will print"
  echo "      their final report to the console only and say that no message was"
  echo "      sent. Set it in your shell profile to get the report on your phone:"
  echo "        export SKILLPACK_NOTIFY_TO=\"+15551234567\""
else
  echo "Report delivery is configured: SKILLPACK_NOTIFY_TO is set."
fi
if [ -d "$(dirname "$SRC")/latch" ]; then
  echo
  echo "latch/ is included in this repo but is NOT installed by this script — it"
  echo "is optional and it owns your terminal, so wiring it in is your decision."
  echo "To use it, add to your shell profile:"
  echo "  alias claude='latch run -- claude-stable --dangerously-skip-permissions'"
fi
echo "Done. In Claude Code: /turbo, /standup, /readout, /sid"
echo "                      /steer and /drive once latch is wired up."
