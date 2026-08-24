from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .paths import LATCH_HOME, LOGS_DIR, ensure_latch_home

REPO = Path(__file__).resolve().parent.parent
STEERER = REPO / "client" / "steerer.py"
STEERERS_DIR = LATCH_HOME / "steerers"
ZSHRC = Path.home() / ".zshrc"

WRAPPED_ALIAS = (
    "alias claude='latch run -- /Users/beans/.local/bin/claude-stable "
    "--dangerously-skip-permissions'"
)
BARE_ALIAS = (
    "alias claude='/Users/beans/.local/bin/claude-stable --dangerously-skip-permissions'"
)


def _steerers_dir() -> Path:
    ensure_latch_home()
    STEERERS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return STEERERS_DIR


def marker_path(sid: str) -> Path:
    return _steerers_dir() / f"{sid}.json"


# A steerer whose marker has not been touched in this long is not credibly
# supervising anything (STEER-02 ruling B). It ticks at least every 15s from the
# SSE heartbeat, so 120s is ~8 missed ticks — well past noise.
MARKER_STALE_S = 120.0


def update_marker(sid: str, patch: dict) -> None:
    """Read-modify-write the steerer marker. Tolerates a missing/corrupt file.

    This is the steerer's ONLY authoritative write. It deliberately does NOT
    mirror latch's inject queue: a mirror of the queue is what made the steerer
    believe items were delivered while latch still held them. The marker answers
    one question — is a supervisor alive and deciding? — and nothing else.
    """
    p = marker_path(sid)
    try:
        m = json.loads(p.read_text()) if p.exists() else {}
        if not isinstance(m, dict):
            m = {}
    except Exception:
        m = {}
    m.update(patch)
    try:
        p.write_text(json.dumps(m, indent=2) + "\n")
        p.chmod(0o600)
    except OSError:
        pass


def marker_staleness(m: dict, now: float | None = None) -> float | None:
    """Age in seconds of the last recorded decision, or None if never recorded."""
    ts = m.get("last_decision_ts")
    if not isinstance(ts, (int, float)):
        return None
    return (time.time() if now is None else now) - float(ts)


def steerer_running(sid: str) -> dict | None:
    p = marker_path(sid)
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text())
    except Exception:
        return None
    pid = m.get("pid")
    if pid and _pid_alive(pid):
        return m
    p.unlink(missing_ok=True)
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def default_goalpack(sess: dict, goal_text: str | None = None) -> Path:
    """Write a minimal goalpack when the caller didn't supply one."""
    _steerers_dir()
    gp = STEERERS_DIR / f"{sess['sid']}.goal.md"
    body = goal_text or (
        f"# Goal\nSteer the Claude Code session in {sess.get('cwd')} toward the "
        f"objective the user gave it. Serve the user's intent; keep Claude on task.\n\n"
        "# Constraints\n- Stay inside the working directory.\n"
        "- Do not start unrelated work.\n\n"
        "# Definition of done\n- The user's core task is delivered and verified.\n\n"
        "# Stop conditions\n- No time/steer budget — runs until done/blocked or "
        "you `latch steer --stop` it. Pass --max-minutes/--max-steers explicitly "
        "if you want a hard cap for this run.\n"
    )
    gp.write_text(body)
    return gp


def launch_steerer(
    sess: dict,
    goal_path: Path,
    *,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    sid = sess["sid"]
    existing = steerer_running(sid)
    if existing:
        return {"ok": False, "reason": "already_steering", "pid": existing.get("pid"), "sid": sid}

    log = LOGS_DIR / f"steerer-{sid}.log"
    argv = [
        sys.executable,
        str(STEERER),
        "--goal",
        str(goal_path),
        "--sid",
        sid,
    ] + (extra_args or [])

    if dry_run:
        return {"ok": True, "dry_run": True, "argv": argv, "sid": sid}

    logf = open(log, "ab")
    logf.write(f"\n=== steerer launch {time.strftime('%Y-%m-%dT%H:%M:%S')} sid={sid} ===\n".encode())
    logf.flush()
    # Explicitly re-inject the operator's LATCH_* config knobs captured at
    # `latch run` launch time (see run.py's launch_env capture) — this Popen
    # call's own os.environ reflects whatever shell layer invoked `latch
    # steer --self` (a Bash-tool-call subshell inside the running Claude
    # session), which is NOT guaranteed to still carry vars the operator
    # exported in the original terminal. Overlaying launch_env on top of the
    # ambient env guarantees operator config survives regardless.
    env = os.environ.copy()
    launch_env = sess.get("launch_env") or {}
    # make the precedence VISIBLE: values captured at `latch run` time win over
    # the current shell, so e.g. a LATCH_STEER_ENGINE exported hours ago beats
    # one exported just now — silent overrides here cost real debugging time
    overridden = {
        k: v for k, v in launch_env.items()
        if k in os.environ and os.environ[k] != v
    }
    if overridden:
        logf.write(
            (f"[launch_env] session-captured values override current shell for: "
             f"{', '.join(sorted(overridden))} (captured at `latch run` wins)\n").encode()
        )
        logf.flush()
    env.update(launch_env)
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=logf,
        stderr=logf,
        start_new_session=True,  # detach: survives the launching shell / skill turn
        cwd=str(REPO),
        env=env,
    )
    marker = {
        "sid": sid,
        "pid": proc.pid,
        "name": sess.get("name"),
        "port": sess.get("port"),
        "cwd": sess.get("cwd"),
        "goal": str(goal_path),
        "log": str(log),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Seeded so a just-launched steerer does not read as stale before its
        # first tick; the steerer overwrites these via update_marker().
        "last_decision_ts": time.time(),
        "last_action": "launched",
        "engine_err_streak": 0,
    }
    marker_path(sid).write_text(json.dumps(marker, indent=2) + "\n")
    marker_path(sid).chmod(0o600)
    return {"ok": True, "pid": proc.pid, "sid": sid, "log": str(log)}


def stop_steerer(sid: str) -> dict:
    m = steerer_running(sid)
    if not m:
        marker_path(sid).unlink(missing_ok=True)
        return {"ok": False, "reason": "not_running", "sid": sid}
    pid = m["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    marker_path(sid).unlink(missing_ok=True)
    return {"ok": True, "stopped_pid": pid, "sid": sid}


def list_steerers() -> list[dict]:
    out = []
    if not STEERERS_DIR.exists():
        return out
    for p in STEERERS_DIR.glob("*.json"):
        try:
            m = json.loads(p.read_text())
        except Exception:
            continue
        m["alive"] = bool(m.get("pid") and _pid_alive(m["pid"]))
        if not m["alive"]:
            p.unlink(missing_ok=True)
            continue
        age = marker_staleness(m)
        m["heartbeat_age_s"] = None if age is None else round(age, 1)
        # A live PID is NOT proof of supervision — the observed failure was a
        # steerer process that had stopped deciding. Report both.
        m["stale"] = bool(age is None or age > MARKER_STALE_S)
        out.append(m)
    return out


# ---- global alias management (opt-in, backed up) ----

def alias_state() -> str:
    if not ZSHRC.exists():
        return "unknown"
    txt = ZSHRC.read_text()
    if "latch run --" in txt and "alias claude=" in txt:
        return "wrapped"
    if "alias claude=" in txt:
        return "bare"
    return "absent"


def _swap_alias(target: str) -> dict:
    if not ZSHRC.exists():
        return {"ok": False, "reason": "no_zshrc"}
    lines = ZSHRC.read_text().splitlines()
    changed = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("alias claude=") and "claude-stable" in s:
            if s == target:
                return {"ok": True, "already": True}
            lines[i] = target
            changed = True
            break
    if not changed:
        return {"ok": False, "reason": "claude_alias_not_found"}
    backup = ZSHRC.with_name(f".zshrc.bak-latch-{int(time.time())}")
    backup.write_text(ZSHRC.read_text())
    ZSHRC.write_text("\n".join(lines) + "\n")
    return {"ok": True, "backup": str(backup)}


def alias_on() -> dict:
    return _swap_alias(WRAPPED_ALIAS)


def alias_off() -> dict:
    return _swap_alias(BARE_ALIAS)
