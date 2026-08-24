"""
latchlib/grok_upload_guard.py — structural fix for ticket #1899 Vector A
residual risk.

Vector A (grok-CLI codebase upload) was already NOT capturing sensitive
data: the steerer spawns `grok -p` with cwd=the latch repo
(latchlib/steer_launch.py), never the steered session's cwd, and empirically
0/6499 grok events on the 2026-07-13 sensitive build were repo uploads. But
the underlying grok-build binary (~/.grok/bin/grok v0.2.93) defaults
`trace_upload`/codebase indexing ON for ANY repo cwd — one cwd mistake
(interactive `grok` run inside a sensitive repo) away from a real leak, and
`~/.grok/config.toml` shipped with no disable setting.

Verified against the actual binary (2026-07-13, not guessed): the grok
CLI's own strings contain the exact log line

    "Codebase upload skipped: disabled by config
     (harness.disable_codebase_upload=true)"

gating its repo_state.upload tar/GCS-enqueue path — i.e. a real, honored
local kill switch exists: `[harness]\ndisable_codebase_upload = true` in
~/.grok/config.toml. Checked and confirmed there is NO env-var equivalent
for this specific key (grok's own bundled `--help`-adjacent env docs list
GROK_TELEMETRY_ENABLED / GROK_FEEDBACK_ENABLED / GROK_DEPLOYMENT_KEY under
"Telemetry", nothing under "harness") — config.toml is the only lever.

This guard makes sure that lever is thrown before the steerer ever shells
out to `grok -p`, self-healing if config drift (a `grok update`/`grok
setup` re-fetch, a stale machine, manual edits) ever turns it back off.
"""

from __future__ import annotations

import time
from pathlib import Path

GROK_CONFIG_PATH = Path.home() / ".grok" / "config.toml"


def _parse_harness_disable(text: str) -> bool:
    """Dependency-free TOML section/key scan (this repo is stdlib-only,
    targets Python 3.9 — no tomllib). Only looks at [harness] ->
    disable_codebase_upload; ignores everything else."""
    in_harness = False
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") :
            in_harness = s.strip("[]").strip() == "harness"
            continue
        if in_harness and s.split("=", 1)[0].strip() == "disable_codebase_upload":
            val = s.split("=", 1)[1].strip().lower()
            return val.startswith("true")
    return False


def is_codebase_upload_disabled(config_path: Path = GROK_CONFIG_PATH) -> bool:
    if not config_path.exists():
        return False
    try:
        return _parse_harness_disable(config_path.read_text())
    except OSError:
        return False


def ensure_codebase_upload_disabled(config_path: Path = GROK_CONFIG_PATH) -> dict:
    """Idempotent. Backs up config.toml before any write (mandatory per this
    task's mutation discipline). Only ever adds/flips
    `[harness] disable_codebase_upload = true` — touches no other key,
    section, or setting."""
    if is_codebase_upload_disabled(config_path):
        return {"changed": False, "path": str(config_path)}

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("[harness]\ndisable_codebase_upload = true\n")
        return {"changed": True, "path": str(config_path), "created": True}

    text = config_path.read_text()
    backup = config_path.with_name(f"{config_path.name}.bak-latch-{int(time.time())}")
    backup.write_text(text)
    backup.chmod(0o600)

    lines = text.splitlines()
    out_lines: list[str] = []
    in_harness = False
    harness_seen = False
    key_written = False

    def _close_harness_if_needed():
        nonlocal key_written
        if in_harness and not key_written:
            out_lines.append("disable_codebase_upload = true")
            key_written = True

    for line in lines:
        s = line.strip()
        if s.startswith("[") and not s.startswith("[["):
            _close_harness_if_needed()
            in_harness = s.strip("[]").strip() == "harness"
            if in_harness:
                harness_seen = True
            out_lines.append(line)
            continue
        if in_harness and s.split("=", 1)[0].strip() == "disable_codebase_upload":
            out_lines.append("disable_codebase_upload = true")
            key_written = True
            continue
        out_lines.append(line)
    _close_harness_if_needed()

    if not harness_seen:
        out_lines.append("")
        out_lines.append("[harness]")
        out_lines.append("disable_codebase_upload = true")

    new_text = "\n".join(out_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    config_path.write_text(new_text)
    return {"changed": True, "path": str(config_path), "backup": str(backup)}
