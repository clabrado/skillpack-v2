#!/bin/bash
# Install skillpack v2 into ~/.claude/skills/.
#
# Refuses to overwrite. If a skill of that name already exists this stops and
# shows you what differs — moving your copy aside is your decision, not this
# script's. Nothing is ever deleted.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
SKILLS=(turbo standup readout sid)

[ -d "$SRC" ] || { echo "error: no skills/ directory beside this script"; exit 1; }
mkdir -p "$DEST" || exit 1

conflicts=0
for s in "${SKILLS[@]}"; do
  if [ -e "$DEST/$s" ]; then
    echo "SKIP  $s — already exists at $DEST/$s"
    if ! diff -rq "$SRC/$s" "$DEST/$s" >/dev/null 2>&1; then
      echo "      and it DIFFERS from this pack's copy:"
      diff -rq "$SRC/$s" "$DEST/$s" 2>&1 | sed 's/^/        /'
    else
      echo "      (identical — nothing to do)"
    fi
    conflicts=$((conflicts + 1))
    continue
  fi
  cp -R "$SRC/$s" "$DEST/$s" || { echo "error: could not copy $s"; exit 1; }
  [ -f "$DEST/$s/sid.sh" ] && chmod +x "$DEST/$s/sid.sh"
  echo "OK    $s -> $DEST/$s"
done

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
echo "Done. In Claude Code: /turbo, /standup, /readout, /sid"
