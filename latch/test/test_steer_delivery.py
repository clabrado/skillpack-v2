#!/usr/bin/env python3
"""test/test_steer_delivery.py — the steerer's side of STEER-02, and the
timing-constant set ruled with it.

WHY THIS EXISTS

Two changes land here and they are coupled, which is why they are tested
together:

1. DELIVERY CONTRACT (STEER-02). The steerer no longer mirrors latch's queue
   and no longer escalates parked steers itself — that mechanism died with the
   steerer process, which is exactly how a lane ended up parked and
   unsupervised. What is left is a CONTRACT: every text steer must carry
   `queue_on_human_active`, a `deliver_by_s`, and `on_deadline=redirect`, so
   latch (which survives) can enforce delivery. The 5x409-then-DROP branch is
   deleted, not merely unreachable.

2. TIMING SET (Fable ruling §6, Chris 2026-08-03: the dead-man's-switch "300s
   is too long, shouldn't be more than 60"). The constants are expressed as
   DERIVATIONS, not independent numbers, and the invariants between them are
   asserted here so a future edit to one cannot silently break its relationship
   to another:

     sum(INJECT_RETRY_BACKOFF) <= watchdog      one retry tail <= one epoch
     HUMAN_ACTIVE_MS/1000      <= first retry   the shortest wait that can help
     deliver_by                 = 5 * watchdog   parked steers live <= 5 epochs

ATTEMPTED BYPASSES in this file:
  - env-var defang of the steerer-side deadline (LATCH_STEER_DELIVER_BY_S)
  - a `watchdog` so large or small it would push deliver_by out of range
  - the deleted drop path being reachable again via the retry planner

STATED EVASION MODEL for the quiet backoff: it re-creates a widening
not-checking window (up to 5x the watchdog) on a session where nothing is
happening. That IS superficially the complaint it answers — the distinction is
that ANY new pending event, any notification, or any non-wait decision snaps
the interval back to one watchdog, so only PROVABLY unchanged state decays.
The tests below assert both halves: that it decays, and that it snaps back.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "client"))

import steerer as S  # noqa: E402
from latchlib.inject import HUMAN_ACTIVE_MS  # noqa: E402


class TestSteerDeliveryContract(unittest.TestCase):
    """TEST 8 — what the steerer actually POSTs."""

    def test_text_steer_carries_the_delivery_contract(self):
        body = S.steer_inject_body("[steerer] do the thing", "text", watchdog=60.0)
        self.assertEqual(body["mode"], "text")
        self.assertEqual(body["when"], "idle")
        self.assertIs(body["queue_on_human_active"], True)
        self.assertEqual(body["on_deadline"], "redirect")
        self.assertEqual(body["deliver_by_s"], 300.0)

    def test_redirect_does_not_ask_for_a_deadline(self):
        """A redirect is when="now" — it is delivered or refused immediately,
        so a delivery deadline would be meaningless on it."""
        body = S.steer_inject_body("[steerer] stop", "redirect")
        self.assertEqual(body["when"], "now")
        self.assertNotIn("deliver_by_s", body)
        self.assertNotIn("on_deadline", body)
        self.assertNotIn("queue_on_human_active", body)

    def test_supersede_is_opt_in(self):
        self.assertNotIn("supersede_queued", S.steer_inject_body("x", "redirect"))
        self.assertTrue(
            S.steer_inject_body("x", "redirect", supersede=True)["supersede_queued"]
        )

    def test_the_drop_path_is_gone_for_text(self):
        """BYPASS: reach the deleted 5x409-then-DROP branch. A text steer
        carries queue_on_human_active, so a 409 on it is impossible by
        contract — and no retry may be armed for it."""
        for attempt in range(len(S.INJECT_RETRY_BACKOFF) + 2):
            self.assertIsNone(S.plan_retry_for("text", "human_active", attempt))

    def test_redirect_still_retries(self):
        """Retries survive where queuing has no meaning."""
        plan = S.plan_retry_for("redirect", "human_active", 0)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["delay"], S.INJECT_RETRY_BACKOFF[0])
        self.assertIsNone(
            S.plan_retry_for("redirect", "human_active", len(S.INJECT_RETRY_BACKOFF)),
            "retries must stay bounded",
        )

    def test_other_refusal_reasons_never_arm_a_retry(self):
        self.assertIsNone(S.plan_retry_for("redirect", "queue_full", 0))
        self.assertIsNone(S.plan_retry_for("redirect", "danger_screen:rm", 0))

    def test_the_removed_escalator_is_really_gone(self):
        """Ruling F: three overlapping mechanisms was the problem. The steerer's
        escalator is subsumed by the latch-side deadline and must not linger."""
        for gone in ("QueuedInjectEscalator", "QUEUED_ESCALATE_COUNT",
                     "QUEUED_ESCALATE_SECONDS"):
            self.assertFalse(hasattr(S, gone), f"{gone} should have been removed")
        self.assertNotIn("LATCH_ESCALATE_QUEUED_N", S._CLAMPS)
        self.assertNotIn("LATCH_ESCALATE_IDLE_S", S._CLAMPS)

    def test_autopilot_actually_fires_on_the_steer_path(self):
        """REGRESSION for a guard keyed on a value the call site never passes.

        586254e guarded on `mode == "steer"`, but `decide()` dispatches a steer
        ACTION as `send(msg, "text")` — the literal "steer" is never a value of
        `mode`, so the policy was dead code and a lane with
        LATCH_STEER_ALWAYS_REDIRECT=1 reported autopilot while steering
        when=idle. That is this ticket's own defect class: a lane reporting
        supervised while nothing steers it.
        """
        import io
        import contextlib

        saved = os.environ.get("LATCH_STEER_ALWAYS_REDIRECT")
        try:
            os.environ["LATCH_STEER_ALWAYS_REDIRECT"] = "1"
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                mode, supersede = S.resolve_send_mode(S.STEER_ACTION_SEND_MODE)
            self.assertEqual(mode, "redirect")
            self.assertTrue(supersede, "a redirect must supersede the stale backlog")
            self.assertIn(
                "[autopilot] steer -> redirect (LATCH_STEER_ALWAYS_REDIRECT=1)",
                err.getvalue(),
            )
        finally:
            os.environ.pop("LATCH_STEER_ALWAYS_REDIRECT", None)
            if saved is not None:
                os.environ["LATCH_STEER_ALWAYS_REDIRECT"] = saved

    def test_autopilot_is_coupled_to_the_real_dispatch_site(self):
        """Assert on the mode the CALL SITE actually passes, read out of the
        source — not on a constant that can drift away from it. If `decide()`
        ever dispatches a steer with a different mode, this fails."""
        import ast

        tree = ast.parse((REPO / "client" / "steerer.py").read_text())
        dispatched: list[str] = []
        for node in ast.walk(tree):
            # match:  elif act == "steer" and msg:  ->  send(msg, "<mode>")
            if not isinstance(node, ast.If):
                continue
            test = ast.dump(node.test)
            if "'steer'" not in test and '"steer"' not in test:
                continue
            if "act" not in test:
                continue
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "send"
                    and len(sub.args) >= 2
                    and isinstance(sub.args[1], ast.Constant)
                ):
                    dispatched.append(sub.args[1].value)
        self.assertEqual(
            dispatched, [S.STEER_ACTION_SEND_MODE],
            "the steer action's dispatch mode drifted from the autopilot guard",
        )

    def test_autopilot_leaves_a_plain_steer_alone_when_off(self):
        saved = os.environ.get("LATCH_STEER_ALWAYS_REDIRECT")
        try:
            os.environ.pop("LATCH_STEER_ALWAYS_REDIRECT", None)
            self.assertEqual(S.resolve_send_mode("text"), ("text", False))
            self.assertEqual(S.resolve_send_mode("redirect", True), ("redirect", True))
        finally:
            if saved is not None:
                os.environ["LATCH_STEER_ALWAYS_REDIRECT"] = saved

    def test_autopilot_lane_policy_survives(self):
        """Ruling F: LATCH_STEER_ALWAYS_REDIRECT is a lane POLICY, a different
        mechanism from the deadline BACKSTOP, and was not removed with it."""
        saved = os.environ.get("LATCH_STEER_ALWAYS_REDIRECT")
        try:
            os.environ["LATCH_STEER_ALWAYS_REDIRECT"] = "1"
            self.assertTrue(S._always_redirect())
            os.environ["LATCH_STEER_ALWAYS_REDIRECT"] = "0"
            self.assertFalse(S._always_redirect())
        finally:
            os.environ.pop("LATCH_STEER_ALWAYS_REDIRECT", None)
            if saved is not None:
                os.environ["LATCH_STEER_ALWAYS_REDIRECT"] = saved


class TestExpiryAlarmIsBoundedAndAttributed(unittest.TestCase):
    """Ruling D — an expired steer is LOUD: audit + bus event + counters + one
    iMessage. Bounded: once per inject_id, and only for items we posted.

    NOTE: no message is sent anywhere in this file. The predicate is tested;
    the sender (`notify`) is the estate-wide one and is deliberately not
    exercised — sandboxing a test does NOT sandbox iMessage.
    """

    def test_notifies_once_for_our_own_expired_steer(self):
        ours, notified = {"abc123"}, set()
        self.assertTrue(S.should_notify_expiry("abc123", ours, notified))
        notified.add("abc123")
        self.assertFalse(S.should_notify_expiry("abc123", ours, notified),
                         "one alarm per inject_id, not one per event")

    def test_does_not_notify_for_someone_elses_inject(self):
        """An operator's own `latch inject` expiring is not ours to shout about."""
        self.assertFalse(S.should_notify_expiry("cli-item", {"ours"}, set()))

    def test_missing_id_never_notifies(self):
        self.assertFalse(S.should_notify_expiry(None, {"ours"}, set()))
        self.assertFalse(S.should_notify_expiry("", {"ours"}, set()))


class TestTimingConstantSet(unittest.TestCase):
    """The ruled constants and the invariants BETWEEN them."""

    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("LATCH_STEER_DELIVER_BY_S", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_watchdog_default_is_60(self):
        """Chris, 2026-08-03: '300s is too long, shouldn't be more than 60.'"""
        self.assertEqual(S.DEFAULT_WATCHDOG_S, 60.0)

    def test_watchdog_default_reaches_the_cli(self):
        """A constant nothing reads is not a default. Check the real parser."""
        out = subprocess.run(
            [sys.executable, str(REPO / "client" / "steerer.py"), "--help"],
            capture_output=True, text=True, timeout=60,
        ).stdout
        self.assertIn("--watchdog", out)
        self.assertIn("default 60s", out)

    def test_retry_tail_fits_in_one_decision_epoch(self):
        """A retry tail longer than one epoch delivers a redirect STALER than
        the next decision, which re-derives it for free."""
        self.assertLessEqual(sum(S.INJECT_RETRY_BACKOFF), S.DEFAULT_WATCHDOG_S)

    def test_first_retry_step_is_at_least_the_human_active_window(self):
        """Retrying sooner than HUMAN_ACTIVE_MS cannot possibly succeed — the
        flag has not had time to clear."""
        self.assertLessEqual(HUMAN_ACTIVE_MS / 1000.0, S.INJECT_RETRY_BACKOFF[0])

    def test_retry_schedule_is_monotonic_and_finite(self):
        self.assertEqual(list(S.INJECT_RETRY_BACKOFF), sorted(S.INJECT_RETRY_BACKOFF))
        self.assertTrue(all(d > 0 for d in S.INJECT_RETRY_BACKOFF))

    def test_deliver_by_is_derived_from_the_watchdog(self):
        self.assertEqual(S._deliver_by(60.0), 300.0)
        self.assertEqual(S._deliver_by(120.0), 600.0)
        self.assertEqual(S.DELIVER_BY_EPOCHS, 5)

    def test_deliver_by_derivation_is_still_clamped(self):
        """BYPASS: defang the deadline through the watchdog instead of through
        its own knob."""
        self.assertEqual(S._deliver_by(100000.0), S.STEER_DELIVER_BY_MAX_S)
        self.assertEqual(S._deliver_by(1.0), S.STEER_DELIVER_BY_MIN_S)

    def test_deliver_by_env_override_is_clamped(self):
        os.environ["LATCH_STEER_DELIVER_BY_S"] = "999999"
        self.assertEqual(S._deliver_by(60.0), S.STEER_DELIVER_BY_MAX_S)
        os.environ["LATCH_STEER_DELIVER_BY_S"] = "1"
        self.assertEqual(S._deliver_by(60.0), S.STEER_DELIVER_BY_MIN_S)

    def test_deliver_by_garbage_env_falls_back_not_open(self):
        os.environ["LATCH_STEER_DELIVER_BY_S"] = "off"
        self.assertEqual(S._deliver_by(60.0), 300.0)

    def test_idle_heuristic_stays_well_under_one_epoch(self):
        """Turn boundaries must be observable BETWEEN deadman fires (15 < 60)."""
        src = (REPO / "latchlib" / "run.py").read_text()
        self.assertIn("(time.time() - last_out) > 15", src)
        self.assertLess(15.0, S.DEFAULT_WATCHDOG_S)


class TestQuietStateBackoff(unittest.TestCase):
    """The deadman path BYPASSES SteerGate's hysteresis — `elapsed >= deadman`
    fires regardless of score. At a 60s watchdog that turns a session sitting at
    a turn boundary into a fixed 60s poller re-judging unchanged state (and,
    with autopilot on, potentially one interrupt per minute). The same-state
    backoff is what keeps materiality primary at 60s."""

    EVENT = {"kind": "tool_use", "tool": "Read", "input_summary": "run.py"}

    def gate(self):
        return S.SteerGate(deadman_s=60.0)

    def test_decay_60_120_240_then_capped(self):
        g = self.gate()
        self.assertEqual(g.effective_deadman(), 60.0)
        expected = [120.0, 240.0, 300.0, 300.0, 300.0]
        for want in expected:
            g.record_decision("wait", [], notification_pending=False)
            self.assertEqual(g.effective_deadman(), want)

    def test_cap_is_derived_not_a_second_constant(self):
        g = S.SteerGate(deadman_s=30.0)
        for _ in range(10):
            g.record_decision("wait", [], notification_pending=False)
        self.assertEqual(g.effective_deadman(), 5 * 30.0)

    def test_fires_at_the_backed_off_interval_not_before(self):
        import time as _t

        g = self.gate()
        for _ in range(2):
            g.record_decision("wait", [], notification_pending=False)
        self.assertEqual(g.effective_deadman(), 240.0)
        g.last_decision_ts = _t.time() - 239
        self.assertFalse(g.should_decide([], notification_pending=False)[0])
        g.last_decision_ts = _t.time() - 241
        fire, why = g.should_decide([], notification_pending=False)
        self.assertTrue(fire)
        self.assertIn("dead-man", why)
        self.assertIn("quiet backoff", why)

    def test_any_new_event_snaps_it_back(self):
        """The load-bearing half: a decayed lane must not stay decayed once
        something actually happens."""
        g = self.gate()
        for _ in range(4):
            g.record_decision("wait", [], notification_pending=False)
        self.assertEqual(g.effective_deadman(), 300.0)
        g.should_decide([self.EVENT], notification_pending=False)
        self.assertEqual(g.effective_deadman(), 60.0)

    def test_a_notification_snaps_it_back(self):
        g = self.gate()
        for _ in range(4):
            g.record_decision("wait", [], notification_pending=False)
        g.should_decide([], notification_pending=True)
        self.assertEqual(g.effective_deadman(), 60.0)

    def test_a_non_wait_decision_snaps_it_back(self):
        g = self.gate()
        for _ in range(4):
            g.record_decision("wait", [], notification_pending=False)
        g.record_decision("steer", [], notification_pending=False)
        self.assertEqual(g.effective_deadman(), 60.0)

    def test_a_wait_with_events_does_not_decay(self):
        """Waiting on state that CHANGED is not the same as waiting on state
        that did not — only the latter may decay."""
        g = self.gate()
        g.record_decision("wait", [self.EVENT], notification_pending=False)
        self.assertEqual(g.effective_deadman(), 60.0)

    def test_materiality_still_wins_over_the_backoff(self):
        """Even fully decayed, a material burst fires a decision immediately —
        the backoff only ever governs the deadman path."""
        g = self.gate()
        for _ in range(4):
            g.record_decision("wait", [], notification_pending=False)
        pending = [
            {"kind": "tool_result", "ok": False, "preview": "Traceback (most recent"},
        ]
        fire, why = g.should_decide(pending, notification_pending=False)
        self.assertTrue(fire)
        self.assertIn("error signal", why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
