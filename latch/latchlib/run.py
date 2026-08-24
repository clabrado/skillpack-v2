from __future__ import annotations

import base64
import errno
import fcntl
import os
import secrets
import select
import shutil
import signal
import struct
import sys
import termios
import time
import tty
from datetime import datetime, timezone
from pathlib import Path

from .bus import EventBus
from .http_api import start_server
from .inject import Injector
from .jsonl_tail import JsonlTailer
from .paths import LOGS_DIR, ensure_latch_home
from .payload_gate import gate_tool_result, gate_tool_use, scrub_text
from .redact import redact_bytes, redact_string
from .registry import claimed_transcript_paths, remove_session, write_session
from .stdin_classify import StdinClassifier
from .token import ensure_token

# Hard ceiling on any single PTY-master write. Generous enough that a busy but
# healthy child always drains inside it, short enough that a wedged child cannot
# park a latch thread — and the injector's lock — indefinitely. See write_pty().
PTY_WRITE_TIMEOUT_S = 10.0

# Ceilings for the OTHER direction — PTY output forwarded to the human tty.
# The terminal is a VIEW; raw.log is the record. A Terminal.app that beachballs
# (or a window that was closed, revoking the tty) must never stall the select
# loop: on 2026-08-04 manager session 3896ac3c froze permanently because writes
# to its revoked tty hung in the kernel — macOS revoke(2) does not wake tty
# writers — and everything else queued behind them. When the tty cannot take a
# chunk inside TTY_WRITE_TIMEOUT_S, the rest of that chunk is DROPPED and
# forwarding pauses for TTY_STALL_COOLOFF_S so the drain loop keeps full speed.
TTY_WRITE_TIMEOUT_S = 5.0
TTY_STALL_COOLOFF_S = 10.0


def run_supervisor(
    cmd: list[str], name: str | None = None, no_log: bool = False, profile: str | None = None
) -> int:
    if not cmd:
        print("usage: latch run [--name N] [--no-log] [--profile P] -- <command> [args...]", file=sys.stderr)
        return 2

    ensure_latch_home()
    ensure_token()

    # Capture operator-set LATCH_* config knobs (LATCH_GROK_MODEL,
    # LATCH_GROK_EFFORT, LATCH_PREGATE, LATCH_NOTIFY, ...) from the launching
    # shell, BEFORE this session's own synthetic sid/port exist. A Bash-tool-call
    # subshell spawned later *inside* the running Claude session is not
    # guaranteed to inherit arbitrary vars exported in the original terminal —
    # confirmed empirically 2026-07-12: the detached `latch steer --self`
    # steerer subprocess did not see a LATCH_* var even though this
    # supervisor's own process had it. Persisting the operator's LATCH_* env
    # into the session registry lets steer_launch.py explicitly re-inject it at
    # spawn time instead of trusting ambient inheritance through whatever shell
    # layers sit in between.
    launch_env = {
        k: v for k, v in os.environ.items()
        if k.startswith("LATCH_") and k not in ("LATCH_SID", "LATCH_PORT")
    }

    sid = secrets.token_hex(4)
    cwd = os.getcwd()
    name = name or Path(cwd).name
    started_at = time.time()

    state: dict = {
        "sid": sid,
        "pid": os.getpid(),
        "child_pid": None,
        "port": None,
        "cwd": cwd,
        "name": name,
        "status": "starting",
        "idle": True,
        "idle_source": "init",
        "last_human_input_at": 0.0,
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at,
        "claude_session_id": None,
        "transcript_path": None,
        "profile": profile,
    }

    bus = EventBus(5000)

    def on_unknown():
        bus.unknown_jsonl += 1

    jsonl = JsonlTailer(publish=bus.publish, sid=sid, on_unknown=on_unknown)

    # Late-bound: persist() is a closure defined before the Injector exists, but
    # the session file must carry delivery state (STEER-02 ruling B — "supervised"
    # has to be a verifiable predicate readable without touching the port).
    injector_ref: dict = {}

    def persist():
        write_session(
            {
                "sid": sid,
                "pid": os.getpid(),
                "child_pid": state.get("child_pid"),
                "port": state["port"],
                "cwd": state["cwd"],
                "name": state["name"],
                "claude_session_id": state.get("claude_session_id"),
                "transcript_path": state.get("transcript_path"),
                "started_at": datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
                "status": state["status"],
                "idle": state["idle"],
                "idle_source": state.get("idle_source"),
                "last_activity_at": state.get("last_activity_at"),
                "launch_env": launch_env,
                "profile": state.get("profile"),
                "inject_queue": (
                    injector_ref["obj"].queue_stats() if injector_ref.get("obj") else None
                ),
            }
        )

    def patch_state(patch: dict):
        state.update(patch)
        if "idle" in patch or "last_human_input_at" in patch:
            persist()

    # Screen-tail ring: last raw PTY bytes, ANSI-stripped on demand.
    # Reality override (v1.1): on claude 2.1.201 fresh interactive sessions do
    # NOT write their transcript JSONL promptly — hooks are the PRIMARY
    # semantic feed, JSONL is enrichment, and this ring is the only source of
    # assistant prose until the transcript materialises.
    screen_ring = bytearray()
    SCREEN_RING_CAP = 16384

    def evt(kind: str, **fields):
        bus.publish(
            {"v": 1, "t": "evt", "ts": int(time.time() * 1000), "sid": sid, "kind": kind, **fields}
        )

    def on_hook(payload: dict):
        event = payload.get("hook_event_name") or payload.get("event") or ""
        psid = payload.get("session_id")

        # Identity: first SessionStart wins; afterwards ignore events from any
        # OTHER claude session that happens to inherit LATCH_PORT.
        if not state.get("claude_session_id") and psid:
            state["claude_session_id"] = psid
            if payload.get("transcript_path"):
                state["transcript_path"] = payload["transcript_path"]
                jsonl.set_path(payload["transcript_path"])
            if payload.get("cwd"):
                state["cwd"] = payload["cwd"]
            evt(
                "session_start",
                claude_session_id=psid,
                transcript_path=state.get("transcript_path"),
            )
            persist()
        elif psid and psid != state.get("claude_session_id"):
            return  # not our session (foreign/unwrapped claude on same env)

        if event == "SessionStart" and payload.get("transcript_path"):
            if state.get("transcript_path") != payload["transcript_path"]:
                state["transcript_path"] = payload["transcript_path"]
                jsonl.set_path(payload["transcript_path"])
                persist()

        if event == "UserPromptSubmit":
            # authoritative busy signal + the prompt text itself (incl. injected steers)
            state["idle"] = False
            state["idle_source"] = "hook"
            state["last_activity_at"] = datetime.now(timezone.utc).isoformat()
            evt(
                "user_text",
                text=scrub_text(str(payload.get("prompt") or ""))[:2000],
                source="hook",
            )
            persist()

        if event == "PostToolUse":
            tool = payload.get("tool_name") or "?"
            ti = payload.get("tool_input")
            tr = payload.get("tool_response")
            input_str = json_safe(ti)[:500]
            # ticket #1899 Vector B: personal-data tool classes (iMessage,
            # Mail, Safari/Contacts/Calendar file stores) get a structural
            # summary in the steerer digest, never raw content — see
            # latchlib/payload_gate.py. Both frames known at the same call
            # site here, so no cross-event id-tracking needed (unlike
            # jsonl_tail, which sees tool_use/tool_result on separate lines).
            sensitive, input_summary = gate_tool_use(tool, input_str)
            evt("tool_use", tool=tool, input_summary=input_summary, source="hook")
            ok = True
            if isinstance(tr, dict) and (tr.get("is_error") or tr.get("error")):
                ok = False
            result_str = json_safe(tr)[:500]
            preview = gate_tool_result(sensitive, ok, result_str)
            evt("tool_result", ok=ok, preview=preview, source="hook")
            state["last_activity_at"] = datetime.now(timezone.utc).isoformat()

        if event == "Stop":
            state["idle"] = True
            state["idle_source"] = "hook"
            state["last_activity_at"] = datetime.now(timezone.utc).isoformat()
            tail = ansi_strip(bytes(screen_ring[-8192:]))
            evt(
                "turn_stopped",
                hook_event=event,
                screen_tail=scrub_text(tail[-1500:]),
            )
            persist()
            injector.on_turn_stopped()

        if event == "Notification":
            evt(
                "notification",
                message=scrub_text(
                    str(payload.get("message") or payload.get("title") or json_safe(payload)[:300])
                ),
            )

        if payload.get("transcript_path") and not state.get("transcript_path"):
            state["transcript_path"] = payload["transcript_path"]
            jsonl.set_path(payload["transcript_path"])
            persist()

    # Bind ephemeral port via OS
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    state["port"] = port

    # Resolve executable
    file = cmd[0]
    args = cmd[1:]
    resolved = shutil.which(file) or file
    if not os.path.isabs(resolved) and not Path(resolved).exists():
        for c in (
            Path.home() / ".local/bin" / file,
            Path("/opt/homebrew/bin") / file,
            Path("/usr/local/bin") / file,
            Path("/bin") / file,
            Path("/usr/bin") / file,
        ):
            if c.exists():
                resolved = str(c)
                break

    master_fd, slave_fd = os.openpty()
    # set winsize
    cols, rows = shutil.get_terminal_size((80, 24))
    _set_winsize(slave_fd, rows, cols)

    pid = os.fork()
    if pid == 0:
        # child
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
        env = os.environ.copy()
        env["LATCH_PORT"] = str(port)
        env["LATCH_SID"] = sid
        env["TERM"] = env.get("TERM") or "xterm-256color"
        env["COLORTERM"] = env.get("COLORTERM") or "truecolor"
        os.chdir(cwd)
        try:
            os.execvpe(resolved, [resolved, *args], env)
        except OSError as e:
            sys.stderr.write(f"exec failed: {resolved}: {e}\n")
            os._exit(127)

    # parent
    os.close(slave_fd)
    state["child_pid"] = pid
    state["status"] = "running"

    # The PTY master is NON-BLOCKING from here on, and that is load-bearing.
    # A blocking os.write() here WEDGED THE WHOLE ESTATE on 2026-08-04 (manager
    # session 6cac7849, diagnosed from a live specimen): the injector's delivery
    # thread held Injector._lock across this write, the write blocked because the
    # PTY input buffer (~1 KB) was full, the select loop below — the ONLY drainer
    # of the PTY master — blocked acquiring that same lock in sweep_deadlines, so
    # the child's stdout buffer filled and the child blocked in its own write().
    # Three-way cycle, permanent, SIGTERM-immune. Bounding this write breaks it.
    #
    # The old body also ignored os.write's return value, so any partial write
    # silently TRUNCATED the injected text — an inject could land half-typed and
    # be indistinguishable from a delivered one.
    os.set_blocking(master_fd, False)

    def write_pty(data: str | bytes) -> bool:
        """Write to the PTY master, bounded. True iff every byte landed."""
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        view = memoryview(data)
        deadline = time.monotonic() + PTY_WRITE_TIMEOUT_S
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # Loud, and deliberately not silent: the caller's text did NOT
                # fully land. Absence of a delivery audit record plus this event
                # is how an undelivered inject is told from a delivered one.
                evt("pty_write_timeout", dropped_bytes=len(view))
                return False
            try:
                _, w, _ = select.select([], [master_fd], [], min(0.25, remaining))
            except (OSError, ValueError):
                return False
            if not w:
                continue
            try:
                n = os.write(master_fd, view)
            except BlockingIOError:
                continue
            except OSError:
                return False
            view = view[n:]
        return True

    injector = Injector(
        write_pty=write_pty,
        get_state=lambda: state,
        patch_state=patch_state,
        sid=sid,
        emit=evt,
    )
    injector_ref["obj"] = injector

    httpd = start_server(
        port=port,
        host="127.0.0.1",
        bus=bus,
        sid=sid,
        get_state=lambda: state,
        injector=injector,
        on_hook=on_hook,
    )
    persist()
    jsonl.start(200)

    # Human-visible latch identity (multi-session disambiguation)
    banner = (
        f"\r\n[latch] sid={sid}  port={port}  name={name}\r\n"
        f"[latch] steer with: latch inject {sid} \"…\"  |  "
        f"steerer --sid {sid}\r\n"
        f"[latch] list all: latch ls\r\n"
    )
    try:
        sys.stderr.write(banner)
        sys.stderr.flush()
    except Exception:
        pass

    # From here on, NOTHING in this process may write the human tty through a
    # Python file object. A hung tty write from a background thread holds that
    # object's io lock forever (the 3896ac3c wedge: an http.server handle_error
    # traceback to sys.stderr on a revoked tty), convoying every other printer.
    # The tty is written ONLY via forward_tty() below, on the select loop, on a
    # private dup'd fd. Tracebacks and stray prints go to a per-sid log instead
    # — which also stops losing them when the window is gone.
    tty_fd = os.dup(sys.stdout.fileno())
    os.set_blocking(tty_fd, False)
    supervisor_log = open(LOGS_DIR / f"{sid}.supervisor.log", "a", buffering=1)
    sys.stdout = supervisor_log
    sys.stderr = supervisor_log

    tty_state = {"dead": False, "stalled_until": 0.0, "dropped": 0}

    def forward_tty(data: bytes) -> None:
        """Best-effort, bounded forward of PTY output to the human terminal.

        Never blocks the select loop: drops on a stalled tty (with cooloff),
        goes permanently headless on EIO/EBADF/ENXIO (revoked device). The
        session itself — child, raw.log, bus, injector — is unaffected.
        """
        if tty_state["dead"]:
            return
        now = time.monotonic()
        if now < tty_state["stalled_until"]:
            tty_state["dropped"] += len(data)
            return
        view = memoryview(data)
        deadline = now + TTY_WRITE_TIMEOUT_S
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                tty_state["stalled_until"] = time.monotonic() + TTY_STALL_COOLOFF_S
                tty_state["dropped"] += len(view)
                evt("tty_stalled", dropped_bytes=tty_state["dropped"])
                return
            try:
                _, w, _ = select.select([], [tty_fd], [], min(0.25, remaining))
            except (OSError, ValueError):
                tty_state["dead"] = True
                evt("tty_dead", reason="select")
                return
            if not w:
                continue
            try:
                n = os.write(tty_fd, view)
            except BlockingIOError:
                continue
            except OSError as e:
                # EIO/EBADF/ENXIO: the terminal is gone (window closed, tty
                # revoked). Run headless from now on; raw.log stays the record.
                tty_state["dead"] = True
                evt("tty_dead", reason=f"errno_{e.errno}")
                return
            view = view[n:]

    # Fallback JSONL discovery — never steal another session's transcript
    def discover_later():
        time.sleep(3)
        if not state.get("transcript_path"):
            claimed = claimed_transcript_paths(except_sid=sid)
            found = jsonl.discover(cwd, claimed=claimed)
            if found:
                state["transcript_path"] = str(found)
                jsonl.set_path(str(found))
                persist()

    import threading

    threading.Thread(target=discover_later, daemon=True).start()

    raw_log = None
    if not no_log:
        raw_log = open(LOGS_DIR / f"{sid}.raw.log", "ab")

    # Human stdin raw mode
    stdin_fd = sys.stdin.fileno()
    old_tty = None
    is_tty = sys.stdin.isatty()
    stdin_open = True
    if is_tty:
        old_tty = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

    def restore_tty():
        if is_tty and old_tty is not None:
            try:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
            except termios.error:
                pass
        # tty_fd shares its open file description with the shell's terminal;
        # leave it in blocking mode so zsh isn't handed O_NONBLOCK on exit.
        try:
            os.set_blocking(tty_fd, True)
        except OSError:
            pass
        try:
            os.close(tty_fd)
        except OSError:
            pass

    def on_sigwinch(signum, frame):
        try:
            cols, rows = shutil.get_terminal_size((80, 24))
            _set_winsize(master_fd, rows, cols)
        except Exception:
            pass

    signal.signal(signal.SIGWINCH, on_sigwinch)

    # SIGTERM/SIGHUP on the supervisor must not orphan the claude child
    # (child is in its own session via setsid, so it would survive us).
    term_sig = {"n": None}

    def on_term(signum, frame):
        term_sig["n"] = signum

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGHUP, on_term)

    exit_code = 0
    reaped = False
    last_out = time.time()
    # Bytes on stdin are NOT the same thing as keystrokes — see
    # latchlib/stdin_classify.py. Counting terminal-protocol replies as a human
    # is what pinned `human_active` and got steer injections refused.
    stdin_classifier = StdinClassifier()
    last_queue_sig: tuple = ()

    try:
        while True:
            if term_sig["n"] is not None:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                term_sig["n"] = None  # keep looping until the child actually exits
            rlist = [master_fd]
            if is_tty and stdin_open:
                rlist.append(stdin_fd)
            try:
                r, _, _ = select.select(rlist, [], [], 0.5)
            except select.error:
                break

            if master_fd in r:
                try:
                    data = os.read(master_fd, 8192)
                except BlockingIOError:
                    # master_fd is non-blocking (see write_pty). select said
                    # readable, but a racing reader can leave nothing to take.
                    continue
                except OSError as e:
                    if e.errno == errno.EIO:
                        break
                    raise
                if not data:
                    break
                # human view — bounded, droppable; the tty must never stall
                # the drain (raw.log below is the source of truth)
                forward_tty(data)
                screen_ring.extend(data)
                if len(screen_ring) > SCREEN_RING_CAP:
                    del screen_ring[: len(screen_ring) - SCREEN_RING_CAP]
                if raw_log:
                    raw_log.write(data)
                    raw_log.flush()
                red = redact_bytes(data)
                bus.publish(
                    {
                        "v": 1,
                        "t": "out",
                        "ts": int(time.time() * 1000),
                        "sid": sid,
                        "b64": base64.b64encode(red).decode("ascii"),
                    }
                )
                state["last_activity_at"] = datetime.now(timezone.utc).isoformat()
                last_out = time.time()
                if state.get("idle_source") in ("init", "heuristic"):
                    state["idle"] = False
                    state["idle_source"] = "heuristic"

            if is_tty and stdin_open and stdin_fd in r:
                try:
                    data = os.read(stdin_fd, 8192)
                except OSError:
                    data = b""
                if not data:
                    # EOF or a revoked tty. Stop selecting on stdin, or the
                    # loop spins hot on a permanently-readable dead fd.
                    stdin_open = False
                if data:
                    # classify first, then forward the ORIGINAL bytes untouched:
                    # classification gates the human-active flag only, never the
                    # data path to the child.
                    if stdin_classifier.feed(data):
                        injector.human_typed()
                    try:
                        os.write(master_fd, data)
                    except OSError:
                        pass

            # Per-item delivery deadlines (STEER-02). Enforced HERE, in the queue
            # owner, because a steerer-side escalator dies with the steerer —
            # which is exactly how sid 7b9313da ended up parked and unsupervised.
            injector.sweep_deadlines()

            # Project delivery state into the session file too (ruling B), so
            # `latch ls` / an auditor can check it WITHOUT touching the port.
            # Enqueue happens on an HTTP thread, so persist() is driven from
            # here on change rather than from the injector — at most 0.5s stale,
            # and it never writes the file on an unchanged queue.
            qsig = tuple(
                sorted(
                    (k, v)
                    for k, v in injector.queue_stats().items()
                    if k not in ("oldest_enqueued_ts", "oldest_deliver_by",
                                 "last_delivery_ts")
                )
            )
            if qsig != last_queue_sig:
                last_queue_sig = qsig
                persist()

            # heuristic idle (fallback when hooks are absent)
            if state.get("idle_source") != "hook":
                if not state.get("idle") and (time.time() - last_out) > 15:
                    state["idle"] = True
                    state["idle_source"] = "heuristic"
                    evt(
                        "turn_stopped",
                        hook_event="heuristic",
                        screen_tail=redact_string(ansi_strip(bytes(screen_ring[-8192:]))[-1500:]),
                    )
                    persist()
                    injector.on_turn_stopped()

            # child reaped?
            try:
                wpid, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                reaped = True
                break
            if wpid == pid:
                exit_code = _decode_status(status)
                reaped = True
                break
    finally:
        # PTY EOF (EIO) usually breaks the loop BEFORE the child is reaped —
        # collect the real exit code here or `latch run` always returns 0.
        if not reaped:
            try:
                _, status = os.waitpid(pid, 0)
                exit_code = _decode_status(status)
            except ChildProcessError:
                pass
        restore_tty()
        jsonl.stop()
        if raw_log:
            raw_log.close()
        try:
            os.close(master_fd)
        except OSError:
            pass

    state["status"] = "exited"
    bus.publish(
        {
            "v": 1,
            "t": "evt",
            "ts": int(time.time() * 1000),
            "sid": sid,
            "kind": "session_exit",
            "code": exit_code,
        }
    )
    persist()

    grace = float(os.environ.get("LATCH_GRACE_MS", "0") or 0)
    if grace <= 0:
        grace = 60_000 if bus.client_count() > 0 else 2_000
    # Drain window so a subscribed client (e.g. an attached steerer) sees the
    # session_exit event before we tear the bus down. With a steerer attached
    # this is the 60s branch, not the 2s one — so it is long enough that a human
    # will ^C through it, and an unguarded sleep answered that with a
    # KeyboardInterrupt traceback and demanded a THIRD ^C to actually leave
    # (reported 2026-07-31). A second ^C means "I want out now": honour it,
    # skip the rest of the drain, and still run the cleanup below.
    try:
        time.sleep(grace / 1000.0)
    except KeyboardInterrupt:
        print("\n[latch] exiting — drain window skipped", file=sys.stderr)
    remove_session(sid)
    httpd.shutdown()
    return exit_code


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


def _decode_status(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 1


_ANSI_RE = None


def ansi_strip(b: bytes) -> str:
    """Best-effort readable text from raw TUI bytes (screen_tail fallback only —
    steerer decisions should prefer hook/jsonl events when present)."""
    global _ANSI_RE
    import re

    if _ANSI_RE is None:
        _ANSI_RE = re.compile(
            rb"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI
            rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
            rb"|\x1b[@-_]"  # other escapes
            rb"|[\x00-\x08\x0b\x0c\x0e-\x1f]"  # control chars (keep \t \n \r)
        )
    s = _ANSI_RE.sub(b"", b).replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    text = s.decode("utf-8", errors="replace")
    lines = [ln.rstrip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def json_safe(o) -> str:
    import json

    try:
        return json.dumps(o)
    except Exception:
        return str(o)
