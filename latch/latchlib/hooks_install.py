from __future__ import annotations

import json
import time
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
SHIM = str(Path(__file__).resolve().parent.parent / "hooks" / "latch-hook.sh")

# UserPromptSubmit + PostToolUse are load-bearing (v1.1): on this claude build
# fresh interactive sessions write their transcript JSONL lazily, so hooks are
# the primary semantic feed for the steerer.
EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "Notification")


def _load() -> dict:
    if SETTINGS.exists():
        return json.loads(SETTINGS.read_text())
    return {}


def _save(settings: dict) -> None:
    if SETTINGS.exists():
        backup = SETTINGS.with_name(f"settings.json.bak-latch-{int(time.time() * 1000)}")
        backup.write_bytes(SETTINGS.read_bytes())
        print(f"backup: {backup}")
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n")
    tmp.rename(SETTINGS)


def _is_latch(command: str) -> bool:
    # match by basename so a moved repo's STALE absolute path is still recognised
    return isinstance(command, str) and command.rstrip("/").endswith("latch-hook.sh")


def _strip_latch(hooks: dict) -> bool:
    """Remove every latch-hook.sh entry (any path) from all events. Self-heal."""
    changed = False
    for event in list(hooks.keys()):
        kept = []
        for g in hooks[event]:
            if isinstance(g, dict):
                before = g.get("hooks", [])
                after = [h for h in before if not _is_latch(h.get("command", ""))]
                if len(after) != len(before):
                    changed = True
                g["hooks"] = after
                if after:
                    kept.append(g)
                # drop now-empty group
            else:
                kept.append(g)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    return changed


def install() -> int:
    settings = _load()
    hooks = settings.setdefault("hooks", {})
    # self-heal: clear any prior latch entries (incl. stale paths from a move)
    _strip_latch(hooks)
    for event in EVENTS:
        hooks.setdefault(event, []).append(
            {"hooks": [{"type": "command", "command": SHIM}]}
        )
    _save(settings)
    print(f"installed {len(EVENTS)} hooks -> {SHIM}")
    return 0


def uninstall() -> int:
    settings = _load()
    hooks = settings.get("hooks", {})
    if _strip_latch(hooks):
        _save(settings)
        print("latch hooks removed")
    else:
        print("nothing to remove")
    return 0
