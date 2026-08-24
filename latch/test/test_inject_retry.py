#!/usr/bin/env python3
"""test/test_inject_retry.py — the human_active retry policy.

WHY THIS EXISTS

Human keystrokes win the keyboard: latch refuses an inject with 409
`human_active`, and that is correct. But a BOOTSTRAPPED steer is guaranteed to
lose the first race — the `/steer ...` invocation IS the human typing — so a
single retry can never survive it.

Verified live 2026-07-31 (sid 458c3245): the opening inject and both follow-up
steers were refused 409, the one available retry was spent on a race it could
not win, and the session sat idle waiting on a human who was waiting on it. The
steerer was attached, healthy, and deciding correctly the whole time; none of
its decisions could land.

The old cap of exactly one retry existed because re-arming "looped forever,
burning --max-steers". That was a symptom of counting every retry as a NEW
steer. The fix separates the two: retries are bounded by the backoff schedule,
and a retry never counts against the steer budget.

These assert the properties that failure needed:
  - a first refusal always yields a retry (the bootstrap case)
  - retries are BOUNDED (no infinite re-arm)
  - the schedule is monotonic and finite (backoff, not a hot loop)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client.steerer import INJECT_RETRY_BACKOFF, plan_inject_retry  # noqa: E402


class TestInjectRetryPolicy(unittest.TestCase):

    def test_first_refusal_always_retries(self):
        """The bootstrap case. attempt=0 is the paste race — it MUST retry."""
        plan = plan_inject_retry(0)
        self.assertIsNotNone(plan, "a bootstrapped steer must not be dropped on "
                                   "its first refusal — that is the guaranteed race")
        self.assertEqual(plan["attempt"], 1)
        self.assertEqual(plan["delay"], INJECT_RETRY_BACKOFF[0])

    def test_more_than_one_retry_is_available(self):
        """The specific regression: one retry could never survive a paste."""
        self.assertGreater(len(INJECT_RETRY_BACKOFF), 1,
                           "a single retry is exactly what failed live on 458c3245")
        self.assertIsNotNone(plan_inject_retry(1),
                             "the second refusal must still retry")

    def test_retries_are_bounded(self):
        """No infinite re-arm — that is what burned --max-steers originally."""
        self.assertIsNone(plan_inject_retry(len(INJECT_RETRY_BACKOFF)))
        self.assertIsNone(plan_inject_retry(len(INJECT_RETRY_BACKOFF) + 5))

    def test_walks_the_whole_schedule_then_stops(self):
        """Drive it exactly as send() does: each plan feeds the next attempt."""
        attempt, delays = 0, []
        while (plan := plan_inject_retry(attempt)) is not None:
            delays.append(plan["delay"])
            attempt = plan["attempt"]
            self.assertLess(attempt, 100, "retry loop failed to terminate")
        self.assertEqual(delays, list(INJECT_RETRY_BACKOFF))
        self.assertEqual(attempt, len(INJECT_RETRY_BACKOFF))

    def test_backoff_is_non_decreasing_and_not_a_hot_loop(self):
        """Backoff, not a hot loop.

        SUPERSEDED ASSERTION (STEER-02, 2026-08-03): this used to require
        `sum(INJECT_RETRY_BACKOFF) >= 120` — "long enough to outlast a human
        pasting a long prompt". Its PRECONDITION no longer holds. Retries then
        covered TEXT steers refused for human_active, so the tail had to outlive
        a long paste or the steer was DROPPED. Text steers now carry
        `queue_on_human_active`: they queue behind the human with a
        latch-enforced deadline and are never dropped, so retries survive only
        for `redirect` (when="now"), where queuing has no meaning.

        The ruled invariant for that narrower job is the OPPOSITE bound —
        `sum <= watchdog`, asserted in test/test_steer_delivery.py — because a
        retry tail longer than one decision epoch delivers a redirect staler
        than the next decision, which re-derives it for free. Keeping both
        bounds would be unsatisfiable at a 60s watchdog.
        """
        self.assertEqual(list(INJECT_RETRY_BACKOFF), sorted(INJECT_RETRY_BACKOFF))
        self.assertGreaterEqual(INJECT_RETRY_BACKOFF[0], 10,
                                "first retry must not fire while the human is still typing")
        self.assertGreater(sum(INJECT_RETRY_BACKOFF), INJECT_RETRY_BACKOFF[0],
                           "more than one retry, or the bounded-retry policy is a no-op")


if __name__ == "__main__":
    unittest.main(verbosity=2)
