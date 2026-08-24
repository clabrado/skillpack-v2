from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Callable

from . import danger_screen, profiles
from .audit import append_audit

ENTER_DELAY_MS = 250
KEY_DELAY_MS = 100
REDIRECT_SETTLE_MS = 700  # Esc → TUI needs a beat to stop the turn and free the composer
HUMAN_ACTIVE_MS = 10_000
MAX_QUEUE = 5

# ---------------------------------------------------------------------------
# Per-item delivery deadline  (STEER-02, Fable ruling 2026-08-03)
#
# A `when="idle"` injection to a session that never goes idle parks in the
# queue forever while the POST reports accepted — the lane then looks
# supervised while nothing is steering it. The previous fix lived in the
# steerer (client/steerer.py QueuedInjectEscalator) and was structurally
# unable to work: it DIED WITH THE STEERER. Live evidence, sid 7b9313da:
# both queued items were eventually `flushed_from_queue` — after the steerer's
# log had ended, so its own 600s escalator never got to fire.
#
# Deadline enforcement therefore belongs to the QUEUE OWNER (latch), which is
# the PTY parent and outlives every supervisor attached to it.
#
# 600s: an interrupt discards the steered session's in-progress turn, and that
# protection is real for a 2-minute turn. It is not real for a 10-minute one —
# a turn that long without a single idle transition is either a wedge or a
# build so long that the steer is about coordination, not nits. The protection
# `when="idle"` was giving is preserved by the LENGTH of the deadline, not by
# the absence of one.
DEFAULT_DELIVER_BY_S = 600.0
DELIVER_BY_MIN_S = 30.0
DELIVER_BY_MAX_S = 3600.0
VALID_ON_DEADLINE = ("redirect", "expire")


def clamp_deliver_by(value) -> float:
    """Clamp a requested deadline into [30, 3600]s.

    Deliberately CLAMPS rather than rejects, and has no "off" value: an env var
    or a request field must never be a way to switch a safety backstop off,
    which is exactly what an honoured `deliver_by_s=999999` would be.
    Unparseable input falls back to the default, never to "never expire".
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return env_deliver_by()
    if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
        return env_deliver_by()
    return max(DELIVER_BY_MIN_S, min(DELIVER_BY_MAX_S, v))


def env_deliver_by() -> float:
    raw = os.environ.get("LATCH_INJECT_DELIVER_BY_S")
    if raw is None:
        return DEFAULT_DELIVER_BY_S
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_DELIVER_BY_S
    return max(DELIVER_BY_MIN_S, min(DELIVER_BY_MAX_S, v))

VALID_MODES = ("text", "keys", "interrupt", "redirect")

# NEVER add a general "char"/"text" key here. The danger screen (danger_screen.py)
# only inspects `text` mode; a generic character key would let `keys` mode spell
# an arbitrary command one keystroke at a time and walk straight past it. The
# literals below are deliberately limited to prompt answers (y/n) and navigation.
KEY_MAP = {
    "enter": "\r",
    "esc": "\x1b",
    "tab": "\t",
    "shift-tab": "\x1b[Z",
    "space": " ",
    "backspace": "\x7f",
    # navigation — driving menus, pagers and ncurses installers
    "up": "\x1b[A",
    "down": "\x1b[B",
    "left": "\x1b[D",
    "right": "\x1b[C",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "page-up": "\x1b[5~",
    "page-down": "\x1b[6~",
    # control codes — interrupt, EOF, suspend, reverse-search, redraw
    "ctrl-c": "\x03",
    "ctrl-d": "\x04",
    "ctrl-z": "\x1a",
    "ctrl-r": "\x12",
    "ctrl-l": "\x0c",
    "ctrl-u": "\x15",
    # prompt answers
    "y": "y",
    "n": "n",
    "q": "q",
}


class Injector:
    def __init__(
        self,
        write_pty: Callable[[str | bytes], None],
        get_state: Callable[[], dict],
        patch_state: Callable[[dict], None],
        sid: str,
        emit: Callable[..., None] | None = None,
    ):
        self.write_pty = write_pty
        self.get_state = get_state
        self.patch_state = patch_state
        self.sid = sid
        # semantic-event publisher, run.py's `evt(kind, **fields)`. Optional so
        # the injector stays unit-testable and usable without a bus.
        self.emit = emit
        self.queue: list[dict] = []
        # REENTRANT, and that is load-bearing — a plain Lock DEADLOCKED THE
        # WHOLE SUPERVISOR, found by a live `latch run` test on 2026-08-03, not
        # by any unit test: `_write` holds this lock for its whole body and ends
        # with `patch_state({"idle": False, ...})`, which run.py answers with
        # `persist()`, which now projects `queue_stats()` into the session file
        # — re-acquiring this same lock on the same thread. The sweep runs in
        # the select loop, so the deadlock froze the PTY pump and the HTTP
        # server with it: the session went dark and `/v1/health` stopped
        # answering. Regression: test_persist_callback_reentrancy_does_not_deadlock.
        self._lock = threading.RLock()
        # DELIVERY runs under its OWN lock, never under _lock. `_write` sleeps
        # (key delays, redirect settle) and drives the PTY, so holding _lock for
        # its duration blocks every _lock taker — including sweep_deadlines and
        # queue_stats, both of which run in run.py's select loop, the ONLY
        # drainer of the PTY master. On 2026-08-04 that produced a three-way
        # deadlock that wedged manager session 6cac7849 permanently: delivery
        # thread blocked writing a full PTY buffer while holding the lock, select
        # loop blocked on the lock, child blocked writing to the undrained PTY.
        # Separating the locks keeps the drain running no matter how long a
        # delivery takes. Concurrent deliveries still serialize on _write_lock.
        self._write_lock = threading.RLock()
        self.counters = {
            "delivered_total": 0,
            "expired_total": 0,
            "deadline_redirects_total": 0,
            "human_active_rejects_total": 0,
            "dropped_total": 0,
        }
        self.last_delivery_ts: float | None = None
        self.last_reject: str | None = None

    def human_typed(self) -> None:
        self.patch_state({"last_human_input_at": time.time()})

    # -- delivery-state projection (health, session file) --------------------

    def queue_stats(self) -> dict:
        with self._lock:
            depth = len(self.queue)
            oldest_enq = min((it["enqueued_at"] for it in self.queue), default=None)
            oldest_due = min((it["deliver_by"] for it in self.queue), default=None)
            return {
                "depth": depth,
                "oldest_enqueued_ts": oldest_enq,
                "oldest_deliver_by": oldest_due,
                "last_delivery_ts": self.last_delivery_ts,
                "last_reject": self.last_reject,
                **self.counters,
            }

    def _emit(self, kind: str, **fields) -> None:
        if not self.emit:
            return
        try:
            self.emit(kind, **fields)
        except Exception:
            pass  # observability must never break delivery

    def _human_active(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        last_h = self.get_state().get("last_human_input_at") or 0
        return bool(last_h) and (now - last_h) < (HUMAN_ACTIVE_MS / 1000)

    def on_turn_stopped(self) -> None:
        threading.Thread(target=self._flush_queue, daemon=True).start()

    def inject(self, body: dict, meta: dict | None = None) -> dict:
        meta = meta or {}
        mode = body.get("mode") or "text"
        when = body.get("when") or "idle"
        # Minted at ACCEPT, returned in every response and carried on every
        # audit record and bus event for this item. Without it a queued item
        # and its eventual delivery/expiry are two unrelated log lines.
        inject_id = uuid.uuid4().hex[:12]

        deliver_by_s = (
            clamp_deliver_by(body["deliver_by_s"])
            if body.get("deliver_by_s") is not None
            else env_deliver_by()
        )
        on_deadline = body.get("on_deadline")
        if on_deadline not in VALID_ON_DEADLINE:
            # Default `expire`: latch never interrupts a turn on behalf of a
            # human who explicitly chose queued text. Steerer-sourced items opt
            # in to `redirect` (see client/steerer.py steer_inject_body).
            on_deadline = "expire"

        if mode not in VALID_MODES:
            return {"accepted": False, "reason": f"unknown_mode:{mode}", "status": 400}

        if mode == "keys":
            data = body.get("data")
            if not isinstance(data, list):
                return {"accepted": False, "reason": "keys_data_must_be_array", "status": 400}
            for k in data:
                if k not in KEY_MAP:
                    return {"accepted": False, "reason": f"unknown_key:{k}", "status": 400}

        # Destructive-text screen. THERE IS NO OVERRIDE — Chris's ruling
        # 2026-08-01: "no destructive commands should be allowed with the
        # solution". A `force` field is deliberately NOT honoured; if one ever
        # reappears in this function it is a regression, and
        # test_danger_screen.py asserts against it.
        #
        # Applied only to payloads carrying free text: `keys` mode cannot spell
        # a command because KEY_MAP holds no general character key, by design.
        if mode in ("text", "redirect"):
            allowed, why = danger_screen.screen(body.get("data") or "")
            if not allowed:
                self._audit(meta, mode, body, when, f"rejected_danger_screen:{why}")
                return {
                    "accepted": False,
                    "reason": f"danger_screen:{why}",
                    "hint": "destructive payloads are refused with no override; run it yourself if intended",
                    "status": 403,
                }

        # redirect always acts now — that is its purpose
        if mode == "redirect":
            when = "now"
            # An escalating supervisor needs its redirect to REPLACE the stale
            # when=idle payloads it already parked, not to be followed by them
            # at the next idle. Opt-in (`supersede_queued`) so an unrelated
            # redirect never silently eats an operator's queued text; the drop
            # is audited so a vanished injection is always explainable.
            if body.get("supersede_queued"):
                with self._lock:
                    superseded, self.queue = self.queue, []
                for item in superseded:
                    self._drop(item, "dropped_superseded_by_redirect")

        # Targets with no idle signal (a REPL, an installer, a pager — anything
        # that is not Claude) never emit a turn-stopped event, so an "idle"
        # injection would sit in the queue forever while reporting accepted.
        # Treat idle as now for them. See profiles.py:has_idle_signal.
        if when == "idle" and not profiles.get(self.get_state().get("profile"))["has_idle_signal"]:
            when = "now"

        state = self.get_state()
        # `queue_on_human_active`: QUEUE instead of 409 when the human-active
        # flag is up. Opt-in, and only meaningful for queueable items
        # (when=idle text). Rationale: the classifier in stdin_classify.py
        # closes the known false-positive sources, but an UNRECOGNISED terminal
        # reply still reads as a human — so the honest fallback is to DELAY the
        # instruction (queue + deadline), never to discard it. The old
        # 5×409-then-DROP path in the steerer is what turned a false positive
        # into an unsupervised run.
        force_queue = False
        if self._human_active():
            if body.get("queue_on_human_active") and when == "idle" and mode == "text":
                force_queue = True
            else:
                self.counters["human_active_rejects_total"] += 1
                self.last_reject = "human_active"
                self._audit(meta, mode, body, when, "rejected_human_active", inject_id)
                return {
                    "accepted": False,
                    "reason": "human_active",
                    "status": 409,
                    "inject_id": inject_id,
                }

        if when == "idle" and (force_queue or not state.get("idle", True)):
            now = time.time()
            item = {
                "body": body,
                "meta": meta,
                "inject_id": inject_id,
                "enqueued_at": now,
                "deliver_by": now + deliver_by_s,
                "on_deadline": on_deadline,
            }
            with self._lock:
                if len(self.queue) >= MAX_QUEUE:
                    full = True
                else:
                    full = False
                    self.queue.append(item)
            if full:
                self.last_reject = "queue_full"
                self._audit(meta, mode, body, when, "rejected_queue_full", inject_id)
                return {
                    "accepted": False,
                    "reason": "queue_full",
                    "status": 409,
                    "inject_id": inject_id,
                }
            self._audit(meta, mode, body, when, "queued", inject_id)
            self._emit(
                "inject_queued",
                inject_id=inject_id,
                deliver_by=item["deliver_by"],
                on_deadline=on_deadline,
                queued_on_human_active=force_queue,
            )
            return {
                "accepted": True,
                "mode": mode,
                "queued": True,
                "inject_id": inject_id,
                "deliver_by": item["deliver_by"],
                "on_deadline": on_deadline,
            }

        self._write(body)
        self._audit(meta, mode, body, when, "written", inject_id)
        self._mark_delivered()
        self._emit("inject_delivered", inject_id=inject_id, via="direct")
        return {"accepted": True, "mode": mode, "queued": False, "inject_id": inject_id}

    def _flush_queue(self) -> None:
        while True:
            state = self.get_state()
            if not state.get("idle", True):
                break
            # NOTE: this `break` leaves the item IN the queue, undelivered. It
            # is correct (the human owns the keyboard right now) but it used to
            # be invisible: the steerer's mirror cleared its pending list on the
            # same idle transition, so it believed delivered while latch still
            # held the item. The mirror is gone (STEER-02); latch's queue is the
            # only authority, and sweep_deadlines() bounds how long this break
            # can hold an item.
            if self._human_active():
                break
            with self._lock:
                if not self.queue:
                    break
                item = self.queue.pop(0)
            self._write(item["body"])
            self._audit(
                item.get("meta", {}),
                item["body"].get("mode") or "text",
                item["body"],
                "idle",
                "flushed_from_queue",
                item.get("inject_id"),
            )
            self._mark_delivered()
            self._emit("inject_delivered", inject_id=item.get("inject_id"), via="flush")

    # -- deadline enforcement ------------------------------------------------

    def sweep_deadlines(self, now: float | None = None) -> None:
        """Enforce per-item delivery deadlines. Cheap no-op on an empty queue.

        Called from the supervisor's select loop (~0.5s cadence) — the SAME
        thread that reads the PTY, so the redirect write here is not a new
        race; `_write` is lock-guarded and already runs from flush threads.

        Anti-bypass: the deadline is anchored to each item's ENQUEUE time and
        enforced by latch. A chatty session that never idles cannot outlast it,
        and re-posting cannot extend an existing item's deadline (a new post is
        a new item with its own clock; supersede happens only AT delivery).
        """
        now = time.time() if now is None else now
        human = self._human_active(now)
        with self._lock:
            if not self.queue:
                return
            expired = [it for it in self.queue if it["deliver_by"] <= now]
            if not expired:
                return
            wants_redirect = any(it["on_deadline"] == "redirect" for it in expired)
            if wants_redirect and human:
                # Never interrupt a human who is genuinely at the keyboard.
                # Deferral cannot be permanent: real typing is bursty and the
                # stdin classifier no longer counts focus/mouse noise, so the
                # flag clears and the next sweep fires. A stuck flag surfaces as
                # `oldest_enqueued_ts` ageing in /v1/health.
                return
            if wants_redirect:
                # The newest queued item is the operative instruction; older
                # ones are stale by construction. Deliver it as an interrupting
                # redirect and drop the rest as superseded.
                target = self.queue[-1]
                dropped = self.queue[:-1]
                self.queue = []
                to_expire: list[dict] = []
            else:
                target = None
                dropped = []
                to_expire = [it for it in expired if it["on_deadline"] == "expire"]
                keep = [it for it in self.queue if it not in to_expire]
                self.queue = keep

        # everything below runs OUTSIDE the lock (_write re-acquires it)
        if target is not None:
            body = dict(target["body"])
            body["mode"] = "redirect"
            body["when"] = "now"
            # NOTE: no re-screen needed — danger_screen ran at accept time
            # (before queuing), so ageing in the queue cannot smuggle a
            # destructive payload past it. Re-screening here would also be a
            # second, divergent policy point.
            self._write(body)
            self.counters["deadline_redirects_total"] += 1
            self._mark_delivered()
            self._audit(
                target.get("meta", {}),
                "redirect",
                body,
                "now",
                "inject_deadline_redirect",
                target.get("inject_id"),
            )
            self._emit(
                "inject_deadline_redirect",
                inject_id=target.get("inject_id"),
                waited_s=round(now - target["enqueued_at"], 1),
                superseded=[it.get("inject_id") for it in dropped],
            )
            for it in dropped:
                self._drop(it, "dropped_superseded_by_deadline")

        for it in to_expire:
            self.counters["expired_total"] += 1
            self._audit(
                it.get("meta", {}),
                it["body"].get("mode") or "text",
                it["body"],
                "idle",
                "expired_undelivered",
                it.get("inject_id"),
            )
            # LOUD by contract: audit + bus event + counter. The steerer turns
            # this event into one iMessage per inject_id; if the steerer is dead
            # the event still stands in the audit log and /v1/health.
            self._emit(
                "inject_expired",
                inject_id=it.get("inject_id"),
                waited_s=round(now - it["enqueued_at"], 1),
                preview=_preview(it["body"]),
            )

    def _drop(self, item: dict, reason: str) -> None:
        self.counters["dropped_total"] += 1
        self._audit(
            item.get("meta", {}),
            item["body"].get("mode") or "text",
            item["body"],
            "idle",
            reason,
            item.get("inject_id"),
        )
        self._emit("inject_dropped", inject_id=item.get("inject_id"), reason=reason)

    def _mark_delivered(self) -> None:
        self.counters["delivered_total"] += 1
        self.last_delivery_ts = time.time()

    def _write(self, body: dict) -> None:
        # _write_lock, NOT _lock — see the comment in __init__. The trailing
        # patch_state -> persist -> queue_stats still takes _lock briefly from
        # this thread; that is the 2026-08-03 reentrancy path and stays correct.
        with self._write_lock:
            mode = body.get("mode") or "text"
            if mode == "interrupt":
                # A bare Esc with no text payload to fall back to. Targets whose
                # profile disables esc_interrupt (e.g. grok-build, where Esc at a
                # modal kills the session) have no proven-safe mid-generation
                # interrupt, so no-op rather than risk it; the caller degrades to
                # waiting for a turn boundary. See latchlib/profiles.py.
                if not profiles.get(self.get_state().get("profile"))["esc_interrupt"]:
                    return
                self.write_pty(KEY_MAP["esc"])
                return
            if mode == "keys":
                for k in body["data"]:
                    self.write_pty(KEY_MAP[k])
                    time.sleep(KEY_DELAY_MS / 1000)
                return
            if mode == "redirect":
                # interrupt the current turn, let the composer come back, then
                # type the new priority and submit — shifting priorities live.
                # Only send the interrupting Esc for targets whose profile allows
                # it: on a target that binds Esc to cancel/quit (esc_interrupt
                # False, e.g. grok-build — live-tested, Esc at a modal kills the
                # session) redirect degrades to an immediate type+submit with no
                # interrupt step. Default profile keeps the Claude-tuned behavior.
                # See latchlib/profiles.py.
                if profiles.get(self.get_state().get("profile"))["esc_interrupt"]:
                    self.write_pty(KEY_MAP["esc"])
                    time.sleep(REDIRECT_SETTLE_MS / 1000)
            text = str(body.get("data") or "")
            submit = body.get("submit", True)
            if "\n" in text:
                self.write_pty(f"\x1b[200~{text}\x1b[201~")
            else:
                self.write_pty(text)
            if submit:
                time.sleep(ENTER_DELAY_MS / 1000)
                self.write_pty("\r")
            self.patch_state({"idle": False, "idle_source": "inject"})

    def _audit(
        self,
        meta: dict,
        mode: str,
        body: dict,
        when: str,
        result: str,
        inject_id: str | None = None,
    ) -> None:
        append_audit(
            {
                "sid": self.sid,
                "source_ip": meta.get("source_ip", "local"),
                "mode": mode,
                "data_preview": _preview(body),
                "when": when,
                "result": result,
                "inject_id": inject_id,
            }
        )


def _preview(body: dict) -> str:
    d = body.get("data")
    if isinstance(d, str):
        return d[:200]
    import json

    return json.dumps(d)[:200]
