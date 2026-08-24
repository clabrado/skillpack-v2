#!/usr/bin/env python3
"""
test/test_sensitive_redaction.py — proof for ticket #1899 Vector B
(steerer digest PII leak) remediation.

Covers:
  (a) A session reading personal-data-classified content (simulated
      tool_result from mcp__imessage__*, plus a Bash sqlite3 read of
      ~/Library/Mail) produces a digest where that raw content is NOT
      present — only structural signals (tool name / ok-error / size
      bucket).
  (b) A genuinely code-only session's digest is UNAFFECTED — full tool
      names, input summaries, and tool_result previews still flow, so
      steering quality is preserved for the common case.
  (c) The generic PII scrub (redact_pii) catches email/phone fragments
      that leak into freeform assistant/user text regardless of tool
      classification (defense-in-depth), without mangling ordinary code
      prose.
  (d) The grok-CLI codebase-upload guard (latchlib/grok_upload_guard.py)
      actually writes/verifies `[harness] disable_codebase_upload = true`
      in a real config.toml, is idempotent, and always backs up before
      writing.

stdlib-only (unittest), matching this repo's existing test conventions.
No network, no real Grok/grok-CLI calls — pure unit tests against the
redaction/classification code paths.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latchlib.jsonl_tail import content_to_frames  # noqa: E402
from latchlib.redact import redact_pii, redact_string  # noqa: E402
from latchlib.sensitive import is_sensitive_tool  # noqa: E402
from latchlib.grok_upload_guard import (  # noqa: E402
    ensure_codebase_upload_disabled,
    is_codebase_upload_disabled,
)


def _run_frames(content):
    """content_to_frames() needs a mutable tool_sensitivity dict threaded
    through, mirroring what JsonlTailer.tick() does for a live transcript."""
    base = {"v": 1, "t": "evt", "ts": 0, "sid": "test"}
    rec = {"uuid": "u1"}
    tool_sensitivity: dict = {}
    return content_to_frames(content, "assistant", base, rec, tool_sensitivity)


class TestSensitiveToolClassification(unittest.TestCase):
    def test_imessage_tool_is_sensitive(self):
        self.assertTrue(is_sensitive_tool("mcp__imessage__tool_get_recent_messages"))

    def test_gmail_tool_is_sensitive(self):
        self.assertTrue(is_sensitive_tool("mcp__claude_ai_Gmail__get_message"))

    def test_mail_path_read_is_sensitive(self):
        self.assertTrue(
            is_sensitive_tool("Bash", json.dumps({"command": "sqlite3 ~/Library/Mail/V10/db"}))
        )

    def test_safari_history_path_is_sensitive(self):
        self.assertTrue(
            is_sensitive_tool("Read", json.dumps({"file_path": "~/Library/Safari/History.db"}))
        )

    def test_ordinary_code_read_not_sensitive(self):
        self.assertFalse(
            is_sensitive_tool("Read", json.dumps({"file_path": "/Users/beans/Projects/latch/client/steerer.py"}))
        )

    def test_ordinary_bash_not_sensitive(self):
        self.assertFalse(
            is_sensitive_tool("Bash", json.dumps({"command": "pytest test/ -v"}))
        )

    def test_calendar_tool_not_flagged_scope_is_deliberate(self):
        # Deliberately narrow scope (see sensitive.py docstring) — Calendar/
        # Drive were NOT named in ticket #1899's remediation list, unlike
        # iMessage/Mail/Safari/Contacts. Documented, not an oversight.
        self.assertFalse(is_sensitive_tool("mcp__claude_ai_Google_Calendar__list_events"))


class TestDigestMinimization(unittest.TestCase):
    """(a) personal-data tool_result content never reaches the digest raw."""

    def test_imessage_tool_result_scrubbed(self):
        secret_message = "Hey it's Chris, my SSN is 123-45-6789 call me at 555-867-5309"
        content = [
            {"type": "tool_use", "id": "tu1", "name": "mcp__imessage__tool_get_recent_messages",
             "input": {"limit": 5}},
        ]
        frames = _run_frames(content)
        tool_use = next(f for f in frames if f["kind"] == "tool_use")
        self.assertNotIn("limit", tool_use["input_summary"])
        self.assertIn("scrubbed", tool_use["input_summary"])

        # Now the matching tool_result, in a separate content_to_frames call
        # sharing the same tool_sensitivity dict (as jsonl_tail.py does across
        # JSONL lines/ticks).
        base = {"v": 1, "t": "evt", "ts": 0, "sid": "test"}
        tool_sensitivity = {"tu1": ("mcp__imessage__tool_get_recent_messages", True)}
        result_content = [
            {"type": "tool_result", "tool_use_id": "tu1", "is_error": False,
             "content": secret_message},
        ]
        result_frames = content_to_frames(result_content, "user", base, {"uuid": "u2"}, tool_sensitivity)
        tool_result = next(f for f in result_frames if f["kind"] == "tool_result")
        self.assertNotIn("Chris", tool_result["preview"])
        self.assertNotIn("123-45-6789", tool_result["preview"])
        self.assertNotIn("555-867-5309", tool_result["preview"])
        self.assertIn("scrubbed", tool_result["preview"])
        self.assertIn("ok", tool_result["preview"])

    def test_home_filesystem_read_of_personal_store_scrubbed(self):
        content = [
            {"type": "tool_use", "id": "tu2", "name": "Bash",
             "input": {"command": "sqlite3 ~/Library/Messages/chat.db 'select text from message'"}},
        ]
        frames = _run_frames(content)
        tool_use = next(f for f in frames if f["kind"] == "tool_use")
        self.assertNotIn("chat.db", tool_use["input_summary"])
        self.assertIn("scrubbed", tool_use["input_summary"])

    def test_unknown_tool_use_id_defaults_non_sensitive(self):
        # Documented default: a tool_result whose tool_use_id was never seen
        # (e.g. transcript truncation at a JSONL boundary) is NOT scrubbed —
        # avoids surprising regressions for the common case at the cost of a
        # rare, narrow edge case. See jsonl_tail.py content_to_frames.
        base = {"v": 1, "t": "evt", "ts": 0, "sid": "test"}
        result_content = [
            {"type": "tool_result", "tool_use_id": "never-seen", "is_error": False,
             "content": "def foo(): pass"},
        ]
        frames = content_to_frames(result_content, "user", base, {"uuid": "u3"}, {})
        tool_result = next(f for f in frames if f["kind"] == "tool_result")
        self.assertIn("def foo", tool_result["preview"])


class TestCodeOnlySessionUnaffected(unittest.TestCase):
    """(b) steering quality preserved for legitimate code-review sessions —
    full tool names/inputs/results still flow through unscrubbed."""

    def test_full_code_session_digest_unaffected(self):
        content = [
            {"type": "text", "text": "Let me check the failing test."},
            {"type": "tool_use", "id": "tu3", "name": "Bash",
             "input": {"command": "pytest test/test_foo.py -v"}},
        ]
        frames = _run_frames(content)
        tool_use = next(f for f in frames if f["kind"] == "tool_use")
        self.assertIn("pytest", tool_use["input_summary"])
        self.assertIn("test_foo.py", tool_use["input_summary"])
        self.assertNotIn("scrubbed", tool_use["input_summary"])

        base = {"v": 1, "t": "evt", "ts": 0, "sid": "test"}
        tool_sensitivity = {"tu3": ("Bash", False)}
        result_content = [
            {"type": "tool_result", "tool_use_id": "tu3", "is_error": False,
             "content": "5 passed in 0.42s"},
        ]
        result_frames = content_to_frames(result_content, "user", base, {"uuid": "u4"}, tool_sensitivity)
        tool_result = next(f for f in result_frames if f["kind"] == "tool_result")
        self.assertIn("5 passed", tool_result["preview"])
        self.assertNotIn("scrubbed", tool_result["preview"])

    def test_assistant_reasoning_text_unaffected_by_ordinary_prose(self):
        content = "I fixed the off-by-one error in the loop bound at line 42."
        frames = _run_frames(content)
        self.assertEqual(frames[0]["text"], content)  # no PII pattern hit, unchanged


class TestPiiPatternScrub(unittest.TestCase):
    """(c) generic email/phone scrub — defense-in-depth for freeform text
    that isn't cleanly tool-classified."""

    def test_email_scrubbed(self):
        out = redact_pii("contact someone@example.com about this")
        self.assertNotIn("someone@example.com", out)
        self.assertIn("redacted:pii", out)

    def test_phone_scrubbed(self):
        out = redact_pii("call 555-867-5309 tomorrow")
        self.assertNotIn("555-867-5309", out)
        self.assertIn("redacted:pii", out)

    def test_ordinary_code_prose_not_mangled(self):
        code_text = "def foo(a, b): return a + b  # sum two numbers, no PII here"
        self.assertEqual(redact_pii(code_text), code_text)

    def test_assistant_text_frame_gets_pii_scrub(self):
        content = "The user's number is 555-123-4567, noting it for later."
        frames = _run_frames(content)
        self.assertNotIn("555-123-4567", frames[0]["text"])

    def test_secret_redaction_still_works_unchanged(self):
        # Vector B fix must not regress the existing secret-pattern redaction.
        out = redact_string("key=sk-ant-abcd1234efgh5678")
        self.assertIn("redacted:sk-ant-a", out)
        self.assertNotIn("abcd1234efgh5678", out)


class TestGrokUploadGuard(unittest.TestCase):
    """(d) grok-CLI upload-disable setting is real and gets wired/applied."""

    def test_creates_config_with_harness_disabled_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "config.toml"
            self.assertFalse(is_codebase_upload_disabled(cfg))
            result = ensure_codebase_upload_disabled(cfg)
            self.assertTrue(result["changed"])
            self.assertTrue(is_codebase_upload_disabled(cfg))

    def test_idempotent_when_already_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "config.toml"
            cfg.write_text("[harness]\ndisable_codebase_upload = true\n")
            result = ensure_codebase_upload_disabled(cfg)
            self.assertFalse(result["changed"])

    def test_flips_existing_false_value_and_backs_up(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "config.toml"
            cfg.write_text(
                "[ui]\nyolo = true\n\n[harness]\ndisable_codebase_upload = false\n"
            )
            result = ensure_codebase_upload_disabled(cfg)
            self.assertTrue(result["changed"])
            self.assertIn("backup", result)
            self.assertTrue(Path(result["backup"]).exists())
            self.assertTrue(is_codebase_upload_disabled(cfg))
            # untouched sections survive
            self.assertIn("yolo = true", cfg.read_text())

    def test_adds_harness_section_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "config.toml"
            cfg.write_text("[ui]\nyolo = true\n")
            result = ensure_codebase_upload_disabled(cfg)
            self.assertTrue(result["changed"])
            self.assertTrue(is_codebase_upload_disabled(cfg))

    def test_real_machine_config_is_hardened(self):
        # This machine's actual ~/.grok/config.toml was hardened as part of
        # ticket #1899's remediation — verify it stayed that way.
        from latchlib.grok_upload_guard import GROK_CONFIG_PATH
        if not GROK_CONFIG_PATH.exists():
            self.skipTest("no ~/.grok/config.toml on this machine")
        self.assertTrue(is_codebase_upload_disabled())


if __name__ == "__main__":
    unittest.main()
