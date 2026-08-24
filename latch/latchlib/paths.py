from __future__ import annotations

import os
from pathlib import Path

LATCH_HOME = Path.home() / ".latch"
TOKEN_PATH = LATCH_HOME / "token"
SESSIONS_DIR = LATCH_HOME / "sessions"
LOGS_DIR = LATCH_HOME / "logs"
AUDIT_PATH = LATCH_HOME / "audit.jsonl"


def ensure_latch_home() -> None:
    for d in (LATCH_HOME, SESSIONS_DIR, LOGS_DIR):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        LATCH_HOME.chmod(0o700)
    except OSError:
        pass


def cwd_to_project_slug(cwd: str) -> str:
    # Claude Code keeps the leading separator: /Users/beans/grok → -Users-beans-grok
    # (verified against ~/.claude/projects on this machine, 2026-07-11)
    resolved = str(Path(cwd).resolve())
    return resolved.replace("/", "-")


def project_jsonl_dir(cwd: str) -> Path:
    return Path.home() / ".claude" / "projects" / cwd_to_project_slug(cwd)
