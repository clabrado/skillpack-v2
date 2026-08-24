#!/usr/bin/env python3
"""
test/test_payload_gate.py — standalone coverage for latchlib/payload_gate.py,
the generalized #1899 payload-classification gate.

Unlike test/test_sensitive_redaction.py (which proves the gate works
correctly as wired into the steerer's digest path via jsonl_tail.py /
run.py), this suite proves the gate is independently usable: any future
code path that wants to forward content to a third-party model can import
`latchlib.payload_gate` directly and get the same guarantee, without going
through JsonlTailer, a transcript JSONL, or the steerer at all.

stdlib-only (unittest), matching this repo's existing test conventions.
No network, no real Grok/grok-CLI calls.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latchlib.payload_gate import (  # noqa: E402
    gate_tool_result,
    gate_tool_use,
    scrub_text,
)


class TestScrubTextStandalone(unittest.TestCase):
    """scrub_text() is the freeform-text half of the gate — usable on any
    string a caller is about to hand to a third-party model, independent
    of tool classification."""

    def test_secret_pattern_redacted(self):
        out = scrub_text("here is key=sk-ant-abcd1234efgh5678")
        self.assertNotIn("abcd1234efgh5678", out)
        self.assertIn("redacted:sk-ant-a", out)

    def test_email_and_phone_redacted(self):
        out = scrub_text("email someone@example.com or call 555-867-5309")
        self.assertNotIn("someone@example.com", out)
        self.assertNotIn("555-867-5309", out)
        self.assertIn("redacted:pii", out)

    def test_ordinary_prose_unchanged(self):
        text = "fixed the off-by-one error in the loop bound at line 42"
        self.assertEqual(scrub_text(text), text)

    def test_secret_and_pii_both_present_both_scrubbed(self):
        out = scrub_text("token=ghp_" + "a" * 25 + " sent to a@b.com")
        self.assertNotIn("a" * 25, out)
        self.assertNotIn("a@b.com", out)


class TestGateToolUseStandalone(unittest.TestCase):
    """gate_tool_use() classifies + scrubs in one call — no separate
    is_sensitive_tool() + branch required at the call site."""

    def test_personal_data_tool_returns_sensitive_and_structural_summary(self):
        sensitive, summary = gate_tool_use(
            "mcp__imessage__tool_get_recent_messages", '{"limit": 5}'
        )
        self.assertTrue(sensitive)
        self.assertIn("scrubbed", summary)
        self.assertNotIn("limit", summary)

    def test_personal_data_path_in_generic_tool_flagged(self):
        sensitive, summary = gate_tool_use(
            "Bash", '{"command": "sqlite3 ~/Library/Messages/chat.db select"}'
        )
        self.assertTrue(sensitive)
        self.assertNotIn("chat.db", summary)

    def test_ordinary_tool_not_sensitive_secret_scrub_still_applies(self):
        sensitive, summary = gate_tool_use(
            "Bash", '{"command": "curl -H \\"Authorization: Bearer ' + "x" * 20 + '\\""}'
        )
        self.assertFalse(sensitive)
        self.assertIn("redacted", summary)
        self.assertNotIn("x" * 20, summary)

    def test_ordinary_tool_no_secret_passes_through(self):
        sensitive, summary = gate_tool_use("Bash", '{"command": "pytest test/ -v"}')
        self.assertFalse(sensitive)
        self.assertIn("pytest", summary)


class TestGateToolResultStandalone(unittest.TestCase):
    """gate_tool_result() takes the sensitivity classified at the matching
    tool_use (sensitivity is a property of the call, not re-derivable from
    the result text alone) and gates the result accordingly."""

    def test_sensitive_result_scrubbed_to_structural_only(self):
        secret = "Hey it's Chris, SSN 123-45-6789, call 555-867-5309"
        preview = gate_tool_result(True, True, secret)
        self.assertNotIn("Chris", preview)
        self.assertNotIn("123-45-6789", preview)
        self.assertIn("scrubbed", preview)
        self.assertIn("ok", preview)

    def test_non_sensitive_result_passes_through_redacted(self):
        preview = gate_tool_result(False, True, "5 passed in 0.42s")
        self.assertEqual(preview, "5 passed in 0.42s")

    def test_non_sensitive_result_still_gets_secret_scrub(self):
        preview = gate_tool_result(False, True, "key=sk-ant-abcd1234efgh5678")
        self.assertNotIn("abcd1234efgh5678", preview)

    def test_sensitive_result_size_bucket_reflects_full_raw_length(self):
        # Size bucket must be computed over the full string passed in, not
        # a caller-side truncation — a future call site that (correctly)
        # passes the untruncated result gets an accurate bucket.
        preview_small = gate_tool_result(True, True, "x" * 50)
        preview_large = gate_tool_result(True, True, "x" * 3000)
        self.assertIn("small", preview_small)
        self.assertIn("large", preview_large)

    def test_error_result_reflected_in_structural_summary(self):
        preview = gate_tool_result(True, False, "some error detail")
        self.assertIn("error", preview)
        self.assertNotIn("some error detail", preview)


class TestGateReusableOutsideSteererContext(unittest.TestCase):
    """Proves the gate has no dependency on JsonlTailer, transcripts, or
    the steerer — a hypothetical new third-party-model call site (e.g. a
    future grok-consult-style integration) could import and use it as-is."""

    def test_full_pipeline_no_steerer_imports_required(self):
        import latchlib.payload_gate as gate_module

        self.assertNotIn("steerer", dir(gate_module))
        # Simulate a brand-new call site building a payload for some other
        # third-party model, using only the gate's public functions.
        tool_name = "mcp__claude_ai_Gmail__get_message"
        input_str = '{"id": "abc123"}'
        sensitive, tool_use_summary = gate_tool_use(tool_name, input_str)
        result_preview = gate_tool_result(sensitive, True, "Subject: reset your password")
        reasoning = scrub_text("Summarizing the email from a@b.com now.")

        self.assertTrue(sensitive)
        self.assertIn("scrubbed", tool_use_summary)
        self.assertIn("scrubbed", result_preview)
        self.assertNotIn("a@b.com", reasoning)


if __name__ == "__main__":
    unittest.main()
