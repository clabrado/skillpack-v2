from __future__ import annotations

import json
import os
from pathlib import Path
from .paths import SESSIONS_DIR, ensure_latch_home


class AmbiguousSession(Exception):
    """More than one session matches the selector."""

    def __init__(self, message: str, candidates: list[dict]):
        super().__init__(message)
        self.candidates = candidates


class NoSession(Exception):
    pass


def session_path(sid: str) -> Path:
    return SESSIONS_DIR / f"{sid}.json"


def write_session(entry: dict) -> None:
    ensure_latch_home()
    p = session_path(entry["sid"])
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entry, indent=2) + "\n")
    tmp.replace(p)
    try:
        p.chmod(0o600)
    except OSError:
        pass


def read_session(sid: str) -> dict | None:
    p = session_path(sid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def remove_session(sid: str) -> None:
    try:
        session_path(sid).unlink(missing_ok=True)
    except TypeError:
        p = session_path(sid)
        if p.exists():
            p.unlink()


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def list_sessions(gc: bool = True) -> list[dict]:
    ensure_latch_home()
    out = []
    if not SESSIONS_DIR.exists():
        return out
    for p in SESSIONS_DIR.glob("*.json"):
        try:
            entry = json.loads(p.read_text())
        except Exception:
            continue
        if gc and entry.get("pid") and not pid_alive(entry["pid"]):
            try:
                p.unlink()
            except OSError:
                pass
            continue
        out.append(entry)
    out.sort(key=lambda s: s.get("started_at") or "", reverse=True)
    return out


def claimed_transcript_paths(except_sid: str | None = None) -> set[str]:
    """Transcript paths already owned by other live latch sessions."""
    claimed = set()
    for s in list_sessions(gc=True):
        if except_sid and s.get("sid") == except_sid:
            continue
        tp = s.get("transcript_path")
        if tp:
            claimed.add(str(Path(tp).resolve()) if Path(tp).exists() else tp)
            claimed.add(tp)
    return claimed


def format_session_row(s: dict) -> str:
    csid = s.get("claude_session_id") or "-"
    if isinstance(csid, str) and len(csid) > 12:
        csid = csid[:8] + "…"
    return (
        f"{s.get('sid')}\t"
        f"name={s.get('name') or '-'}\t"
        f"port={s.get('port')}\t"
        f"idle={s.get('idle')}\t"
        f"status={s.get('status')}\t"
        f"pid={s.get('pid')}\t"
        f"claude={csid}\t"
        f"cwd={s.get('cwd')}\t"
        f"started={s.get('started_at') or '-'}"
    )


def format_candidates(cands: list[dict]) -> str:
    lines = ["matching sessions:"]
    for s in cands:
        lines.append("  " + format_session_row(s))
    lines.append("disambiguate with exact --sid, or --name plus --cwd")
    return "\n".join(lines)


def resolve_sid(
    selector: str | None,
    *,
    cwd: str | None = None,
    allow_newest: bool = False,
    require_unique_name: bool = True,
) -> dict:
    """
    Resolve a live latch session.

    Multi-session rules:
    - Exact sid match always wins (unique).
    - Name match: if multiple share the name, filter by cwd if given;
      if still multiple → AmbiguousSession.
    - 'newest' / 'latest' / None: only legal when exactly one live session,
      OR allow_newest=True (opt-in footgun).
    - Optional cwd filter applied after selection type.
    """
    sessions = list_sessions()
    if cwd:
        cwd_res = str(Path(cwd).resolve())
        sessions = [
            s
            for s in sessions
            if str(Path(s.get("cwd") or "").resolve()) == cwd_res
            or (s.get("cwd") or "") == cwd
        ]

    if not sessions:
        raise NoSession(
            "no live latch sessions"
            + (f" for cwd={cwd}" if cwd else "")
            + " — start with: latch run -- claude"
        )

    if not selector or selector in ("newest", "latest"):
        if len(sessions) == 1 or allow_newest:
            return sessions[0]
        raise AmbiguousSession(
            f"{len(sessions)} live latch sessions; refusing ambiguous 'newest'. "
            "Pass an exact sid (see latch ls).",
            sessions,
        )

    # Exact sid
    by_sid = [s for s in sessions if s.get("sid") == selector]
    if len(by_sid) == 1:
        return by_sid[0]
    if len(by_sid) > 1:
        # should not happen — sid is unique per file
        raise AmbiguousSession("duplicate sid in registry", by_sid)

    # Name match
    by_name = [s for s in sessions if s.get("name") == selector]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        if require_unique_name:
            raise AmbiguousSession(
                f"name '{selector}' matches {len(by_name)} sessions",
                by_name,
            )
        return by_name[0]

    # Prefix sid match (unique only)
    prefix = [s for s in sessions if str(s.get("sid") or "").startswith(selector)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        raise AmbiguousSession(f"sid prefix '{selector}' is ambiguous", prefix)

    raise NoSession(f"session not found: {selector}\n{format_candidates(list_sessions())}")
