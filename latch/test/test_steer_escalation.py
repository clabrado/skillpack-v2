#!/usr/bin/env python3
"""test/test_steer_escalation.py — the deterministic supervisor backstops.

WHY THIS EXISTS

Observed live 2026-08-02: a session looped ~20 turns emitting a near-identical
sentence with NO tool call. A steerer was attached the whole time and produced
ZERO decisions. Three injections sat queued and undelivered because the steerer
posts steers with when="idle" and latch queues those while the session is
mid-turn — and a looping session never goes idle. The supervisor was
structurally unable to intervene in exactly the failure it exists to catch.
`redirect` (interrupt-now) already existed in the decision schema and was never
chosen: the engine prompt biases hard toward `wait` ("every steer/redirect
costs real time").

So the fix is HARNESS LOGIC, not prompt guidance. These tests assert the
properties that failure needed, plus the bypasses each gate must survive:

  - the loop detector fires on tool-less near-duplicate turns
  - the loop detector NEVER fires when a tool call is in the window
    (a false positive that interrupts real work is worse than the bug)
  - BYPASS: cosmetic variation (a changing counter) does not evade it
  - BYPASS: an escalated redirect still passes through the danger screen
  - env knobs cannot disable the gate

NOTE: QueuedInjectEscalator was removed (STEER-02, 2026-08-03). Its
deadline-enforcement responsibility moved to latch's Injector.sweep_deadlines()
(latchlib/inject.py) because the steerer-side escalator died with the steerer
process, leaving sessions parked and unsupervised.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "client"))

import steerer as S  # noqa: E402
from latchlib import danger_screen  # noqa: E402

LOOP_TEXT = (
    "I will now continue implementing the change described in the plan and "
    "make sure the tests pass before reporting back to you."
)


class TestLoopDetector(unittest.TestCase):
    def test_fires_on_toolless_repeat(self):
        d = S.LoopDetector()
        self.assertIsNone(d.check(now=100.0))
        d.observe_assistant(LOOP_TEXT)
        self.assertIsNone(d.check(now=100.0))
        d.observe_assistant(LOOP_TEXT)
        self.assertIsNone(d.check(now=100.0), "two turns is a restatement, not a loop")
        d.observe_assistant(LOOP_TEXT)
        self.assertIsNotNone(d.check(now=100.0))

    def test_does_not_fire_when_a_tool_call_is_in_the_window(self):
        """THE load-bearing false-positive guard: repeated tool calls are real
        work (a poll loop, a retried test run) and must never be interrupted."""
        d = S.LoopDetector()
        for _ in range(10):
            d.observe_assistant(LOOP_TEXT)
            d.observe_tool()
            self.assertIsNone(d.check(now=100.0))

    def test_does_not_fire_on_distinct_narrative(self):
        d = S.LoopDetector()
        for s in (
            "Reading the configuration file to find where the timeout is set, "
            "because the failure mentions a socket timeout in the client path.",
            "The timeout is set in latchlib/http_api.py; now editing the "
            "heartbeat constant and re-running the integration suite for it.",
            "All eighteen tests pass now, so I am committing the change to the "
            "feature branch and pushing it up for review by the operator.",
        ):
            d.observe_assistant(s)
        self.assertIsNone(d.check(now=100.0))

    def test_does_not_fire_on_short_turns(self):
        d = S.LoopDetector()
        for _ in range(5):
            d.observe_assistant("Done.")
        self.assertIsNone(d.check(now=100.0))

    def test_bypass_cosmetic_variation_still_detected(self):
        """BYPASS ATTEMPT: vary a counter/timestamp inside an otherwise
        identical sentence to slip under the similarity threshold."""
        d = S.LoopDetector()
        for i in range(3):
            d.observe_assistant(LOOP_TEXT + f" (attempt {i + 1} at 12:0{i}:0{i})")
        self.assertIsNotNone(d.check(now=100.0), "cosmetic variation must not evade")

    def test_cooldown_prevents_thrash(self):
        d = S.LoopDetector()
        for _ in range(3):
            d.observe_assistant(LOOP_TEXT)
        self.assertIsNotNone(d.check(now=100.0))
        for _ in range(3):
            d.observe_assistant(LOOP_TEXT)
        self.assertIsNone(d.check(now=101.0), "must not re-fire inside the cooldown")
        for _ in range(3):
            d.observe_assistant(LOOP_TEXT)
        self.assertIsNotNone(d.check(now=100.0 + S.LOOP_COOLDOWN_S + 1))

    def test_reset_on_new_direction(self):
        d = S.LoopDetector()
        for _ in range(2):
            d.observe_assistant(LOOP_TEXT)
        d.reset()
        d.observe_assistant(LOOP_TEXT)
        self.assertIsNone(d.check(now=100.0))

    def test_constants_are_named_and_sane(self):
        self.assertEqual(S.LOOP_WINDOW_TURNS, 3)
        self.assertEqual(S.LOOP_SIMILARITY_THRESHOLD, 0.90)


class TestEscalationCannotBypassDangerScreen(unittest.TestCase):
    """BYPASS ATTEMPT: escalation re-sends payloads as mode=redirect. That path
    must not become a way around the no-override destructive-text screen."""

    def test_loop_break_message_is_clean(self):
        allowed, _ = danger_screen.screen(S.LOOP_BREAK_MESSAGE)
        self.assertTrue(allowed)

    def test_destructive_payload_still_refused_as_redirect(self):
        allowed, why = danger_screen.screen("[steerer] rm -rf /Users/beans/Projects")
        self.assertFalse(allowed, f"danger screen must refuse this; got {why}")


class TestEnvKnobsCannotDisableTheGate(unittest.TestCase):
    """BYPASS ATTEMPT: turn a safety backstop off through its tuning knob."""

    def setUp(self):
        self._saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_similarity_above_one_is_clamped(self):
        os.environ["LATCH_LOOP_SIMILARITY"] = "2.0"
        self.assertEqual(
            S._clamped_env("LATCH_LOOP_SIMILARITY", S.LOOP_SIMILARITY_THRESHOLD), 0.90
        )

    def test_garbage_falls_back_not_open(self):
        os.environ["LATCH_LOOP_WINDOW"] = "off"
        self.assertEqual(S._clamped_env("LATCH_LOOP_WINDOW", S.LOOP_WINDOW_TURNS), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)