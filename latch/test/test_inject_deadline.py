#!/usr/bin/env python3
"""test/test_inject_deadline.py — latch-side delivery deadlines (STEER-02).

WHY THIS EXISTS

Ticket: "steer injections park in the queue undelivered: a lane reports
supervised while nothing steers it" (01KZ4E06VH9JTTD00JVE6PKK4H).

A steer is posted `when="idle"`, so latch queues it whenever the session is
mid-turn. A session that never goes idle parks it forever while the POST
reports accepted. The previous fix lived in the steerer and died with it —
audit evidence for sid 7b9313da shows both queued items were eventually
`flushed_from_queue` AFTER the steerer's log ended, so its own 600s escalator
never once fired in the failure it existed for.

Never-idle is simulated here at the Injector unit level with a pinned fake
state and an EXPLICIT CLOCK passed to `sweep_deadlines(now=…)` — no session, no
PTY, no GX10, no ten-minute wait.

=========================================================================
ATTEMPTED BYPASSES AND THE STATED EVASION MODEL
=========================================================================

Every bypass below is an executable test in `TestAttemptedBypasses` /
`TestClassifierClosesTheHumanActiveFreeze`, not a claim that one exists:

  1. CHATTY SESSION NEVER IDLES — emit output forever so the idle heuristic
     never fires. Fails: the deadline is anchored to ENQUEUE time, not to idle.
  2. RE-POSTING TO POSTPONE — keep parking fresh items hoping the clock
     restarts. Fails: deadlines are per-item and enforced by latch; a new post
     is a new item with its own clock and cannot extend an existing one.
  3. ENV-VAR DEFANG — LATCH_INJECT_DELIVER_BY_S=999999 / "off" / "". Fails:
     clamped to 3600 or fallen back to the default. There is no "off" value.
  4. KILL THE STEERER — the historical bypass, and the one that actually
     worked. Fails now: enforcement is entirely inside the queue owner and
     needs no steerer, no bus, and no subscriber.
  5. SESSION-DRIVEN human_active FREEZE — an adversarial session payload writes
     `ESC[c` / DSR queries to its own tty so the TERMINAL answers on the
     supervisor's stdin, pinning last_human_input_at and locking the supervisor
     out of injecting. Fails: recognised replies no longer count as a human.
  6. PAYLOAD SMUGGLING VIA THE DEADLINE REDIRECT — hide a destructive payload
     in a queued item and let ageing convert it into an interrupting redirect.
     Fails: danger_screen runs at ACCEPT, before anything is queued.

WHAT STILL GETS THROUGH (stated, not hidden):

  (a) A genuinely long legitimate turn past the deadline IS interrupted and
      loses that turn's in-progress work. Bounded harm, tunable to 3600s,
      and accepted deliberately: bounded loss of one turn beats unbounded loss
      of supervision.
  (b) An UNRECOGNISED terminal reply sequence still reads as a human. The
      classifier is a denylist of known replies, and it cannot be otherwise
      without a terminal-state machine. Residual harm is now only DELAY, never
      loss: such an item is queued with a deadline instead of dropped, the
      sweep re-checks every 0.5s, and a stuck flag surfaces as
      `oldest_enqueued_ts` ageing in /v1/health.
  (c) If the latch supervisor process itself dies, nothing is delivered. But
      latch IS the PTY parent, so the session dies with it and session_exit
      fires — there is no lane left to supervise.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from latchlib import inject as I  # noqa: E402
from latchlib.stdin_classify import StdinClassifier  # noqa: E402

ESC = "\x1b"


class InjectorHarness:
    """Fake-state Injector: pinned idle/human state, captured PTY + audit + bus."""

    def __init__(self, *, idle=False, human_at=0.0, profile=None, emit=True):
        self.state = {
            "idle": idle,
            "profile": profile,
            "last_human_input_at": human_at,
        }
        self.writes: list[str] = []
        self.audits: list[dict] = []
        self.events: list[tuple[str, dict]] = []
        self.inj = I.Injector(
            write_pty=lambda d: self.writes.append(
                d.decode() if isinstance(d, bytes) else d
            ),
            get_state=lambda: self.state,
            patch_state=self.state.update,
            sid="t-steer02",
            emit=((lambda kind, **f: self.events.append((kind, f))) if emit else None),
        )

    # -- introspection helpers ------------------------------------------------
    @property
    def written(self) -> str:
        return "".join(self.writes)

    def results(self) -> list[str]:
        return [a["result"] for a in self.audits]

    def event_kinds(self) -> list[str]:
        return [k for k, _ in self.events]

    def event(self, kind: str) -> dict | None:
        for k, f in self.events:
            if k == kind:
                return f
        return None


class DeadlineTestCase(unittest.TestCase):
    """Base: captures audit writes so no test ever touches ~/.latch/audit.jsonl."""

    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("LATCH_INJECT_DELIVER_BY_S", None)
        self._real_audit = I.append_audit
        self.h: InjectorHarness | None = None

        def fake_audit(entry: dict) -> None:
            if self.h is not None:
                self.h.audits.append(entry)

        I.append_audit = fake_audit

    def tearDown(self):
        I.append_audit = self._real_audit
        os.environ.clear()
        os.environ.update(self._env)

    def harness(self, **kw) -> InjectorHarness:
        self.h = InjectorHarness(**kw)
        return self.h

    @staticmethod
    def steer_body(text="do the thing", **over) -> dict:
        body = {
            "mode": "text",
            "data": text,
            "when": "idle",
            "submit": True,
            "queue_on_human_active": True,
            "deliver_by_s": 30,
            "on_deadline": "redirect",
        }
        body.update(over)
        return body


# =========================================================================
# 1-7: the design's unit tests
# =========================================================================


class TestParkedSteerEscalation(DeadlineTestCase):
    """TEST 1 — the ticket's acceptance test. A steer parked against a session
    that NEVER goes idle must be delivered as a redirect at its deadline, by
    latch, with no steerer in the picture."""

    def test_never_idle_session_gets_the_steer_at_the_deadline(self):
        h = self.harness(idle=False)  # pinned: this session never goes idle
        r = h.inj.inject(self.steer_body("run the failing test"), {})
        self.assertTrue(r["accepted"])
        self.assertTrue(r["queued"], "a mid-turn idle steer must queue, not write")
        self.assertIn("inject_id", r)
        iid = r["inject_id"]
        self.assertEqual(h.event_kinds(), ["inject_queued"])

        t0 = h.inj.queue[0]["enqueued_at"]

        h.inj.sweep_deadlines(now=t0 + 29)
        self.assertEqual(h.written, "", "must not fire before the deadline")
        self.assertEqual(len(h.inj.queue), 1)

        h.inj.sweep_deadlines(now=t0 + 31)
        # default profile: Esc to interrupt, then the payload, then submit
        self.assertEqual(h.written, ESC + "run the failing test" + "\r")
        self.assertEqual(h.inj.queue, [], "delivered item must leave the queue")
        self.assertIn("inject_deadline_redirect", h.results())
        ev = h.event("inject_deadline_redirect")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["inject_id"], iid, "the event must carry the item's id")
        self.assertEqual(h.inj.counters["deadline_redirects_total"], 1)
        self.assertEqual(h.inj.queue_stats()["depth"], 0)

    def test_no_steerer_is_involved(self):
        """TEST/BYPASS 4 — kill the steerer. Enforcement must not need one: no
        bus subscriber, no emit callable, no marker, nothing but latch."""
        h = self.harness(idle=False, emit=False)
        h.inj.inject(self.steer_body("still delivered"), {})
        t0 = h.inj.queue[0]["enqueued_at"]
        h.inj.sweep_deadlines(now=t0 + 31)
        self.assertIn("still delivered", h.written)


class TestNewestWinsSupersede(DeadlineTestCase):
    """TEST 2 — two parked items expire together: only the NEWEST is delivered;
    the older is dropped as superseded and the drop is audited, so a vanished
    injection is always explainable."""

    def test_only_newest_delivered_older_audited_as_superseded(self):
        h = self.harness(idle=False)
        r1 = h.inj.inject(self.steer_body("stale instruction"), {})
        r2 = h.inj.inject(self.steer_body("current instruction"), {})
        t0 = h.inj.queue[0]["enqueued_at"]

        h.inj.sweep_deadlines(now=t0 + 31)

        self.assertIn("current instruction", h.written)
        self.assertNotIn("stale instruction", h.written)
        self.assertEqual(h.inj.queue, [])
        self.assertIn("dropped_superseded_by_deadline", h.results())
        drop = [a for a in h.audits if a["result"] == "dropped_superseded_by_deadline"]
        self.assertEqual(len(drop), 1)
        self.assertEqual(drop[0]["inject_id"], r1["inject_id"])
        redir = h.event("inject_deadline_redirect")
        self.assertEqual(redir["inject_id"], r2["inject_id"])
        self.assertEqual(redir["superseded"], [r1["inject_id"]])


class TestExpirePolicy(DeadlineTestCase):
    """TEST 3 — `on_deadline=expire` (the operator-CLI default). Latch never
    interrupts a turn on behalf of a human who explicitly chose queued text;
    the item dies LOUDLY instead."""

    def test_expire_writes_nothing_but_is_loud(self):
        h = self.harness(idle=False)
        r = h.inj.inject(self.steer_body("operator text", on_deadline="expire"), {})
        t0 = h.inj.queue[0]["enqueued_at"]

        h.inj.sweep_deadlines(now=t0 + 31)

        self.assertEqual(h.written, "", "expire must never touch the PTY")
        self.assertEqual(h.inj.queue, [])
        self.assertIn("expired_undelivered", h.results())
        ev = h.event("inject_expired")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["inject_id"], r["inject_id"])
        self.assertGreaterEqual(ev["waited_s"], 30)
        self.assertEqual(h.inj.counters["expired_total"], 1)
        self.assertEqual(h.inj.counters["deadline_redirects_total"], 0)

    def test_expire_default_when_policy_unspecified_or_bogus(self):
        h = self.harness(idle=False)
        h.inj.inject({"mode": "text", "data": "x", "when": "idle"}, {})
        h.inj.inject({"mode": "text", "data": "y", "when": "idle",
                      "on_deadline": "please-just-deliver-it"}, {})
        self.assertEqual([it["on_deadline"] for it in h.inj.queue],
                         ["expire", "expire"])


class TestHumanActiveDefersButNotForever(DeadlineTestCase):
    """TEST 4 — the sharpest residual: a deadline redirect must never interrupt
    a human who is genuinely at the keyboard, and must not be deferrable
    forever either."""

    def test_defer_then_deliver(self):
        h = self.harness(idle=False)
        h.inj.inject(self.steer_body("after you stop typing"), {})
        t0 = h.inj.queue[0]["enqueued_at"]

        h.state["last_human_input_at"] = t0 + 30  # a human typed a moment ago
        h.inj.sweep_deadlines(now=t0 + 31)
        self.assertEqual(h.written, "", "must defer while a human is typing")
        self.assertEqual(len(h.inj.queue), 1, "deferral must not drop the item")

        h.state["last_human_input_at"] = t0  # 31s since the last keystroke
        h.inj.sweep_deadlines(now=t0 + 31)
        self.assertIn("after you stop typing", h.written)

    def test_expire_is_not_deferred_by_a_human(self):
        """An expiry writes nothing to the PTY, so there is nothing to defer."""
        h = self.harness(idle=False)
        h.inj.inject(self.steer_body("cli text", on_deadline="expire"), {})
        t0 = h.inj.queue[0]["enqueued_at"]
        h.state["last_human_input_at"] = t0 + 30
        h.inj.sweep_deadlines(now=t0 + 31)
        self.assertIn("expired_undelivered", h.results())


class TestQueueOnHumanActive(DeadlineTestCase):
    """TEST 5 — the drop path is DELETED. A steer arriving while human_active is
    up must be QUEUED (with its deadline), never 409'd and never dropped."""

    def test_steer_queues_instead_of_409(self):
        h = self.harness(idle=True, human_at=I.time.time())  # idle AND human typing
        r = h.inj.inject(self.steer_body("queued behind the human"), {})
        self.assertTrue(r["accepted"])
        self.assertTrue(r["queued"])
        self.assertEqual(h.written, "", "must not type over a live human")
        ev = h.event("inject_queued")
        self.assertTrue(ev["queued_on_human_active"])

    def test_without_the_flag_409_is_unchanged(self):
        h = self.harness(idle=True, human_at=I.time.time())
        r = h.inj.inject({"mode": "text", "data": "x", "when": "idle"}, {})
        self.assertFalse(r["accepted"])
        self.assertEqual(r["reason"], "human_active")
        self.assertEqual(r["status"], 409)
        self.assertEqual(h.inj.counters["human_active_rejects_total"], 1)

    def test_redirect_while_human_active_is_still_409(self):
        """A redirect is when="now"; queuing has no meaning for it, so the
        human still wins the keyboard outright."""
        h = self.harness(idle=False, human_at=I.time.time())
        r = h.inj.inject({"mode": "redirect", "data": "x", "when": "now",
                          "queue_on_human_active": True}, {})
        self.assertFalse(r["accepted"])
        self.assertEqual(r["reason"], "human_active")

    def test_no_idle_signal_profile_still_bypasses_the_queue(self):
        """Ruling E: REPL/installer targets have no idle signal, so idle->now
        conversion must still win — queuing them would park forever."""
        h = self.harness(idle=False, profile="tui")
        r = h.inj.inject(self.steer_body("ls\n"), {})
        self.assertFalse(r["queued"])
        self.assertEqual(h.inj.queue, [])


class TestClassifier(unittest.TestCase):
    """TEST 6 — stdin bytes are not keystrokes."""

    def setUp(self):
        self.c = StdinClassifier()

    def test_focus_reports_are_not_human(self):
        self.assertFalse(self.c.feed(b"\x1b[I"))
        self.assertFalse(self.c.feed(b"\x1b[O"))

    def test_mouse_reports_are_not_human(self):
        self.assertFalse(self.c.feed(b"\x1b[<35;10;3M"))
        self.assertFalse(self.c.feed(b"\x1b[<35;10;3m"))
        self.assertFalse(self.c.feed(b"\x1b[M\x20\x21\x22"))

    def test_dsr_and_da_replies_are_not_human(self):
        self.assertFalse(self.c.feed(b"\x1b[12;40R"))
        self.assertFalse(self.c.feed(b"\x1b[?1;2c"))
        self.assertFalse(self.c.feed(b"\x1b]11;rgb:1c1c/1c1c/1c1c\x07"))

    def test_paste_guards_are_not_human(self):
        self.assertFalse(self.c.feed(b"\x1b[200~"))
        self.assertFalse(self.c.feed(b"\x1b[201~"))

    def test_a_keystroke_is_human(self):
        self.assertTrue(self.c.feed(b"y"))
        self.assertTrue(self.c.feed(b"\r"))
        self.assertTrue(self.c.feed(b"\x1b[A"), "an arrow key IS a keystroke")

    def test_sequence_split_across_reads(self):
        """The read boundary must not manufacture a human."""
        self.assertFalse(self.c.feed(b"\x1b["))
        self.assertFalse(self.c.feed(b"I"))
        self.assertFalse(self.c.feed(b"\x1b[<35;"))
        self.assertFalse(self.c.feed(b"10;3M"))

    def test_reply_plus_real_typing_is_human(self):
        self.assertTrue(self.c.feed(b"\x1b[Ihello"))

    def test_carry_is_bounded(self):
        """An unbounded carry would be a way to make keystrokes invisible."""
        self.assertTrue(self.c.feed(b"\x1b[" + b"1;" * 40))


class TestClampsAndKnobs(DeadlineTestCase):
    """TEST 7 / BYPASS 3 — no env var and no request field may switch the
    backstop off."""

    def test_request_field_is_clamped_both_ways(self):
        self.assertEqual(I.clamp_deliver_by(999999), 3600.0)
        self.assertEqual(I.clamp_deliver_by(1), 30.0)
        self.assertEqual(I.clamp_deliver_by(300), 300.0)

    def test_clamp_applies_end_to_end(self):
        h = self.harness(idle=False)
        h.inj.inject(self.steer_body("x", deliver_by_s=999999), {})
        it = h.inj.queue[0]
        self.assertAlmostEqual(it["deliver_by"] - it["enqueued_at"], 3600.0, places=3)
        h.inj.inject(self.steer_body("y", deliver_by_s=1), {})
        it = h.inj.queue[1]
        self.assertAlmostEqual(it["deliver_by"] - it["enqueued_at"], 30.0, places=3)

    def test_env_var_cannot_defang(self):
        os.environ["LATCH_INJECT_DELIVER_BY_S"] = "999999"
        self.assertEqual(I.env_deliver_by(), 3600.0)
        os.environ["LATCH_INJECT_DELIVER_BY_S"] = "0"
        self.assertEqual(I.env_deliver_by(), 30.0)

    def test_garbage_env_falls_back_not_open(self):
        for junk in ("off", "", "never", "-1e999"):
            os.environ["LATCH_INJECT_DELIVER_BY_S"] = junk
            self.assertLessEqual(I.env_deliver_by(), 3600.0)
            self.assertGreaterEqual(I.env_deliver_by(), 30.0)

    def test_unparseable_request_field_falls_back(self):
        self.assertEqual(I.clamp_deliver_by("banana"), I.env_deliver_by())
        self.assertEqual(I.clamp_deliver_by(float("nan")), I.env_deliver_by())
        self.assertEqual(I.clamp_deliver_by(float("inf")), I.env_deliver_by())


# =========================================================================
# Attempted bypasses (see the module docstring for the evasion model)
# =========================================================================


class TestAttemptedBypasses(DeadlineTestCase):
    def test_bypass_chatty_session_never_idles(self):
        """BYPASS 1: keep the session busy forever so the idle heuristic never
        fires and the queue never flushes. This is the observed failure."""
        h = self.harness(idle=False)
        h.inj.inject(self.steer_body("you are stuck — change approach"), {})
        t0 = h.inj.queue[0]["enqueued_at"]
        for t in range(0, 30, 5):  # session stays busy the whole time
            h.inj.sweep_deadlines(now=t0 + t)
            self.assertEqual(h.written, "")
        h.inj.sweep_deadlines(now=t0 + 30.1)
        self.assertIn("change approach", h.written)

    def test_bypass_reposting_cannot_postpone(self):
        """BYPASS 2: park a fresh item every few seconds hoping the clock
        restarts. Deadlines are per-item; the oldest expires on its own clock."""
        h = self.harness(idle=False)
        h.inj.inject(self.steer_body("oldest"), {})
        t0 = h.inj.queue[0]["enqueued_at"]
        for i in range(1, 4):
            h.inj.inject(self.steer_body(f"refresh {i}"), {})
            h.inj.sweep_deadlines(now=t0 + i * 5)
            self.assertEqual(h.written, "", "no delivery before the OLDEST deadline")
        h.inj.sweep_deadlines(now=t0 + 31)
        self.assertNotEqual(h.written, "", "re-posting must not postpone escalation")

    def test_bypass_supersede_does_not_reset_a_deadline(self):
        """A `supersede_queued` redirect clears the queue at DELIVERY time —
        it must not be usable as a way to launder an old item into a new
        deadline."""
        h = self.harness(idle=False)
        h.inj.inject(self.steer_body("first"), {})
        t0 = h.inj.queue[0]["enqueued_at"]
        h.inj.inject({"mode": "redirect", "data": "now", "when": "now",
                      "supersede_queued": True}, {})
        self.assertEqual(h.inj.queue, [], "supersede drops, it does not re-time")
        self.assertIn("dropped_superseded_by_redirect", h.results())
        h.inj.sweep_deadlines(now=t0 + 31)  # nothing left to escalate
        self.assertEqual(h.inj.counters["deadline_redirects_total"], 0)

    def test_bypass_destructive_payload_cannot_age_into_a_redirect(self):
        """BYPASS 6: smuggle a destructive payload past the screen by having it
        AGE into a redirect. The screen runs at accept, before queuing."""
        h = self.harness(idle=False)
        r = h.inj.inject(self.steer_body("rm -rf /Users/beans/Projects"), {})
        self.assertFalse(r["accepted"])
        self.assertEqual(r["status"], 403)
        self.assertEqual(h.inj.queue, [], "a refused payload must never be queued")
        h.inj.sweep_deadlines(now=I.time.time() + 10_000)
        self.assertEqual(h.written, "")

    def test_bypass_queue_full_is_still_bounded(self):
        """MAX_QUEUE is the count bound that replaced the removed count-based
        escalator. It must still hold with queue_on_human_active in play."""
        h = self.harness(idle=False)
        for i in range(I.MAX_QUEUE):
            self.assertTrue(h.inj.inject(self.steer_body(f"m{i}"), {})["accepted"])
        r = h.inj.inject(self.steer_body("overflow"), {})
        self.assertFalse(r["accepted"])
        self.assertEqual(r["reason"], "queue_full")
        self.assertIn("inject_id", r)


class TestSupervisorReentrancy(DeadlineTestCase):
    """REGRESSION, found by a LIVE `latch run` test and by nothing else.

    `_write` holds the injector lock for its whole body and ends with
    `patch_state({"idle": False, ...})`. run.py answers that with `persist()`,
    which projects `queue_stats()` into the session file — re-acquiring the same
    lock on the same thread. With a plain Lock that deadlocked the SELECT LOOP,
    which is the PTY pump, so the session went dark and /v1/health stopped
    answering: a supervisor that hangs the thing it supervises.

    Every unit test passed while this was broken, because none of them wired
    patch_state to a callback that reads back through the injector.
    """

    def test_persist_callback_reentrancy_does_not_deadlock(self):
        h = self.harness(idle=False)
        seen: list[int] = []
        # exactly run.py's shape: persist() on an idle patch, reading queue_stats
        h.inj.patch_state = lambda patch: (
            h.state.update(patch),
            seen.append(h.inj.queue_stats()["depth"]),
        )
        h.inj.inject(self.steer_body("reentrant"), {})
        t0 = h.inj.queue[0]["enqueued_at"]
        h.inj.sweep_deadlines(now=t0 + 31)  # would hang forever under a plain Lock
        self.assertIn("reentrant", h.written)
        self.assertEqual(seen, [0], "persist must observe the drained queue")


class TestClassifierClosesTheHumanActiveFreeze(unittest.TestCase):
    """BYPASS 5 — the injection-DoS. An adversarial session payload writes
    device queries to its own tty; the TERMINAL answers on the supervisor's
    stdin. Under the old rule (any stdin byte == a human) that pinned
    last_human_input_at and locked the supervisor out of injecting."""

    def test_a_flood_of_terminal_replies_never_reads_as_a_human(self):
        c = StdinClassifier()
        adversarial = (
            b"\x1b[?1;2c"                    # DA reply to ESC[c
            b"\x1b[24;80R"                   # DSR reply
            b"\x1b]11;rgb:0000/0000/0000\x07"  # OSC colour reply
            b"\x1b[I\x1b[O"                  # focus churn
            b"\x1b[<0;1;1M\x1b[<0;1;1m"      # mouse
        )
        for _ in range(200):
            self.assertFalse(c.feed(adversarial), "no human is present here")

    def test_the_real_human_still_wins_the_keyboard(self):
        """The guard must not be so eager it stops noticing actual typing —
        that would be a worse defect than the one being fixed."""
        c = StdinClassifier()
        self.assertFalse(c.feed(b"\x1b[I"))
        self.assertTrue(c.feed(b"\x1b[Istop\r"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
