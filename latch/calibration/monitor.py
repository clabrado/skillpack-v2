#!/usr/bin/env python3
"""
Calibration monitor — tails a steerer's log + latch session health and
appends structured, timestamped entries to a calibration record. Runs
detached so it survives independent of any single Claude turn.
"""
from __future__ import annotations
import json, re, sys, time, urllib.request, pathlib

SID = sys.argv[1]
OUT = pathlib.Path(sys.argv[2])
LATCH_LOG = pathlib.Path.home() / ".latch" / "logs" / f"steerer-{SID}.log"
TOKEN_PATH = pathlib.Path.home() / ".latch" / "token"

DECISION_RE = re.compile(r"^\[(open|decision[^\]]*|text|redirect|inject)\]\s*(.*)$")

def token():
    return TOKEN_PATH.read_text().strip()

def health(port):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/health",
        headers={"Authorization": f"Bearer {token()}"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())

def find_port():
    for p in (pathlib.Path.home() / ".latch" / "sessions").glob("*.json"):
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        if s.get("sid") == SID:
            return s.get("port")
    return None

def emit(kind, payload):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind, **payload}
    with OUT.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def main():
    emit("monitor_start", {"sid": SID})
    offset = 0
    last_idle = None
    while True:
        # tail steerer log for new lines
        if LATCH_LOG.exists():
            data = LATCH_LOG.read_bytes()
            if len(data) > offset:
                new = data[offset:].decode(errors="replace")
                offset = len(data)
                for line in new.splitlines():
                    m = DECISION_RE.match(line.strip())
                    if m:
                        emit("steerer_line", {"tag": m.group(1), "text": m.group(2)[:2000]})
        # snapshot health / idle transitions
        port = find_port()
        if port:
            try:
                h = health(port)
                idle = h.get("idle")
                if idle != last_idle:
                    emit("idle_transition", {"idle": idle, "idle_source": h.get("idle_source")})
                    last_idle = idle
            except Exception as e:
                emit("health_error", {"error": str(e)})
        else:
            emit("session_gone", {})
            break
        # steerer still alive?
        steerer_dir = pathlib.Path.home() / ".latch" / "steerers"
        marker = steerer_dir / f"{SID}.json"
        if not marker.exists():
            emit("steerer_exited", {})
            break
        time.sleep(5)
    emit("monitor_end", {})

if __name__ == "__main__":
    main()
