from __future__ import annotations

import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .token import token_matches

HOOK_BODY_MAX = 64 * 1024
HOOK_RATE_MAX = 200  # PostToolUse can burst during tool storms
HOOK_RATE_WINDOW = 1.0
SSE_HEARTBEAT_S = 15.0
# Every handler socket gets a hard I/O deadline. Without one, a peer that
# stops reading (a SIGSTOP'd steerer, a beachballed `latch tail`) parks this
# handler thread in send() FOREVER once the socket buffer fills — observed
# live in the 2026-08-04 3896ac3c wedge, where exactly such a thread anchored
# a process-wide lock convoy. A timed-out client just reconnects.
SOCKET_TIMEOUT_S = 30.0

# A client hanging up mid-request (a killed `latch tail`, an old steerer's SSE
# stream, a one-shot health poll that got Ctrl-C'd) is normal, not a bug.
# socketserver's default handle_error() prints a full traceback to stderr —
# which, since this server runs inside the `latch run` supervisor process,
# lands DIRECTLY on the human's terminal and visually corrupts the Claude TUI
# it's supposed to be transparent underneath. Swallow the expected disconnect
# exceptions; still surface anything genuinely unexpected.
# socket.timeout: on Python 3.9 it is NOT TimeoutError (they merged in 3.10),
# and the per-connection deadline above raises it on any slow/stuck peer.
_EXPECTED_DISCONNECTS = (
    ConnectionResetError,
    BrokenPipeError,
    ConnectionAbortedError,
    TimeoutError,
    socket.timeout,
)


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, _EXPECTED_DISCONNECTS):
            return
        super().handle_error(request, client_address)


def start_server(
    port: int,
    host: str,
    bus,
    sid: str,
    get_state: Callable[[], dict],
    injector,
    on_hook: Callable[[dict], None],
) -> ThreadingHTTPServer:
    hook_hits: list[float] = []
    hook_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(SOCKET_TIMEOUT_S)
            super().setup()

        def log_message(self, fmt, *args):
            return  # quiet

        def _json(self, code: int, obj: Any) -> None:
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read_body(self, max_size: int) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > max_size:
                raise ValueError("body too large")
            return self.rfile.read(n) if n else b""

        def _auth_ok(self) -> bool:
            return token_matches(self.headers.get("Authorization"))

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/v1/health":
                st = get_state()
                self._json(
                    200,
                    {
                        "sid": sid,
                        "pid": st.get("pid"),
                        "status": st.get("status"),
                        "idle": st.get("idle"),
                        "idle_source": st.get("idle_source"),
                        "uptime_s": int((time.time() - st.get("started_at", time.time()))),
                        "clients": bus.client_count(),
                        "dropped_frames": bus.total_dropped(),
                        "unknown_jsonl_records": bus.unknown_jsonl,
                        "claude_session_id": st.get("claude_session_id"),
                        "transcript_path": st.get("transcript_path"),
                        # STEER-02 ruling B: delivery state must be observable
                        # outside the steerer's stderr. An auditor (gx-run,
                        # `latch health`) checks that nothing is queued past its
                        # deliver_by before treating a lane as supervised.
                        "inject_queue": injector.queue_stats(),
                    },
                )
                return
            if u.path == "/v1/stream":
                if not self._auth_ok():
                    self._json(401, {"error": "unauthorized"})
                    return
                qs = parse_qs(u.query)
                replay = int((qs.get("replay") or ["0"])[0] or 0)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                # All writes to this socket happen on THIS handler thread only.
                # The bus never writes to sockets — publish() just queues.
                sub = bus.subscribe()
                try:
                    self.wfile.write(b": ok\n\n")
                    st = get_state()
                    meta = {
                        "v": 1,
                        "t": "meta",
                        "ts": int(time.time() * 1000),
                        "sid": sid,
                        "pid": st.get("pid"),
                        "cwd": st.get("cwd"),
                        "name": st.get("name"),
                        "claude_session_id": st.get("claude_session_id"),
                    }
                    self.wfile.write(f"data: {json.dumps(meta)}\n\n".encode())
                    for frame in bus.replay(replay):
                        self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
                    self.wfile.flush()
                    while True:
                        frame = sub.pop(SSE_HEARTBEAT_S)
                        if frame is None:
                            self.wfile.write(b": heartbeat\n\n")
                        else:
                            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
                        self.wfile.flush()
                except Exception:
                    pass  # client went away — its queue dies with it
                finally:
                    bus.unsubscribe(sub)
                return
            self.send_error(404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/v1/hook":
                # Response writes stay OUTSIDE hook_lock: a socket write can
                # block until the connection deadline, and holding the lock
                # through it would serialize every other hook POST behind one
                # stuck client.
                with hook_lock:
                    now = time.time()
                    hook_hits[:] = [t for t in hook_hits if now - t < HOOK_RATE_WINDOW]
                    limited = len(hook_hits) >= HOOK_RATE_MAX
                    if not limited:
                        hook_hits.append(now)
                if limited:
                    self.send_response(429)
                    self.end_headers()
                    return
                try:
                    raw = self._read_body(HOOK_BODY_MAX)
                    payload = json.loads(raw.decode() or "{}")
                    if not isinstance(payload, dict):
                        raise ValueError("payload must be object")
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return
                on_hook(payload)
                self.send_response(204)
                self.end_headers()
                return

            if not self._auth_ok():
                self._json(401, {"error": "unauthorized"})
                return

            if u.path == "/v1/inject":
                try:
                    raw = self._read_body(256 * 1024)
                    body = json.loads(raw.decode() or "{}")
                except Exception:
                    self._json(400, {"error": "bad json"})
                    return
                result = injector.inject(
                    body, {"source_ip": self.client_address[0] if self.client_address else "local"}
                )
                code = 200 if result.get("accepted") else result.get("status", 400)
                self._json(code, result)
                return

            if u.path == "/v1/interrupt":
                result = injector.inject(
                    {"mode": "interrupt", "when": "now"},
                    {"source_ip": self.client_address[0] if self.client_address else "local"},
                )
                code = 200 if result.get("accepted") else result.get("status", 400)
                self._json(code, result)
                return

            self.send_error(404)

    httpd = _QuietThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
