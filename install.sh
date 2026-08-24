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
SKILLS=(turbo standup readout sid eclaude)
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
# --- the alias: /steer and /drive are inert without it ---------------------
#
# Asked, never assumed. Editing someone's shell profile is not something an
# installer should do quietly, but printing a line after the fact is how the
# step gets missed and how /steer ends up installed and silently doing nothing.
#
# SKILLPACK_ZSHRC overrides the target file so this path can be tested without
# touching a real profile.
offer_latch_alias() {
  local rc="${SKILLPACK_ZSHRC:-$HOME/.zshrc}"

  [ -d "$ROOT/latch" ] || return 0

  if [ "$(uname -s)" != "Darwin" ]; then
    echo
    echo "latch is macOS-only, so /steer and /drive are not usable here."
    echo "See docs/WINDOWS-STEER.md for what a port would take."
    return 0
  fi

  local latch_bin claude_bin
  latch_bin="$(command -v latch 2>/dev/null || true)"
  [ -n "$latch_bin" ] && [ -x "$HOME/.local/bin/latch" ] ||     latch_bin="${latch_bin:-$([ -x "$HOME/.local/bin/latch" ] && echo "$HOME/.local/bin/latch")}"
  if [ -z "$latch_bin" ]; then
    echo
    echo "latch is not installed, so /steer and /drive will do nothing."
    echo "It ships in this repo under latch/ — install it, then re-run this script."
    return 0
  fi
  claude_bin="$(command -v claude-stable 2>/dev/null || command -v claude 2>/dev/null || true)"
  if [ -z "$claude_bin" ]; then
    echo
    echo "No 'claude' or 'claude-stable' on PATH — cannot build the alias. Skipping."
    return 0
  fi

  if [ ! -f "$rc" ]; then
    echo
    echo "No $rc, so this script will not create one. To make /steer work, put"
    echo "this where your shell reads it:"
    echo "  alias claude='$latch_bin run -- $claude_bin --dangerously-skip-permissions'"
    return 0
  fi

  local current
  current="$(grep -n "alias claude=" "$rc" 2>/dev/null || true)"
  if printf '%s' "$current" | grep -q "latch run --"; then
    echo
    echo "Your claude alias already starts sessions under latch — nothing to do."
    echo "/steer and /drive will work in any NEW terminal window."
    return 0
  fi

  echo
  echo "/steer and /drive need every Claude session to start under latch, which"
  echo "owns the session's terminal so another window can watch it and type into"
  echo "it. Without this they install, appear in your skill list, and do nothing."
  echo
  echo "This adds one line to $rc (a timestamped backup is written first):"
  echo "  alias claude='$latch_bin run -- $claude_bin --dangerously-skip-permissions'"
  echo
  echo "That flag lets a session act without stopping to ask each time, which is"
  echo "what makes an unattended supervised run possible. Answer n to skip it and"
  echo "the alias will be added without the flag."

  if [ ! -t 0 ]; then
    echo
    echo "(Not an interactive terminal — skipping. Re-run this script directly to"
    echo " be asked, or add the line above yourself.)"
    return 0
  fi

  printf "\nWrap your claude alias for latch? [y/N] "
  local reply=""
  read -r reply || true
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Skipped. /steer and /drive are installed but will do nothing until this is done."
       return 0 ;;
  esac

  printf "Include --dangerously-skip-permissions? [Y/n] "
  local perms=""
  read -r perms || true
  local flag=" --dangerously-skip-permissions"
  case "$perms" in
    n|N|no|NO) flag="" ;;
  esac

  local backup="${rc}.bak-latch-$(date +%s)"
  cp "$rc" "$backup" || { echo "error: could not back up $rc — nothing changed"; return 1; }

  if [ -n "$current" ]; then
    # An unwrapped alias exists. latch swaps it in place and writes its own
    # backup; ours above is belt and braces.
    if [ -z "${SKILLPACK_ZSHRC:-}" ] && "$latch_bin" alias-on >/dev/null 2>&1; then
      echo "Wrapped your existing alias (latch wrote its own backup too)."
    else
      # latch alias-on only rewrites an alias containing claude-stable, and only
      # in the real ~/.zshrc — fall back to editing the line ourselves.
      local tmp="${rc}.skillpack-tmp-$$"
      sed "s|^alias claude=.*|alias claude='$latch_bin run -- $claude_bin$flag'|" "$rc" > "$tmp" \
        && mv "$tmp" "$rc" \
        && echo "Replaced your existing claude alias."
    fi
  else
    # No alias at all. `latch alias-on` does NOT help here — it only rewrites an
    # alias that already exists and reports claude_alias_not_found otherwise.
    printf "\nalias claude='%s run -- %s%s'\n" "$latch_bin" "$claude_bin" "$flag" >> "$rc"
    echo "Added the alias to $rc"
  fi

  echo "Backup: $backup"
  echo
  echo "It does NOT apply to any terminal already open. To confirm it works:"
  echo "  1. open a NEW terminal window and run: claude"
  echo "  2. from a DIFFERENT window run:        latch ls"
  echo "  3. the new session must appear there — that listing is the proof."
  echo "To undo: latch alias-off"
}

offer_latch_alias
echo "Done. In Claude Code: /turbo, /standup, /readout, /sid, /eclaude"
echo "                      /steer and /drive once latch is wired up."
echo "                      /eclaude launches windows via bin/eclaude.sh"
