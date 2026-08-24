"""
latchlib/payload_gate.py — generalized external-model payload-classification
gate (ticket #1899 follow-up).

Ticket #1899 fixed the Grok-digest leak by combining latchlib.sensitive's
tool-class classification with latchlib.redact's secret/PII scrub. The fix
landed at its two call sites (jsonl_tail.py's content_to_frames, run.py's
PostToolUse/UserPromptSubmit/Stop/Notification handlers) as inline,
duplicated orchestration — each site had to independently remember to call
is_sensitive_tool(), then branch to structural_tool_use_summary() /
structural_tool_result_preview() vs. redact_string(), then also run
redact_pii() over freeform text. That duplication is exactly how a *future*
third-party-model call site ends up forgetting a step.

This module is that orchestration, factored out once, so any code path
about to forward content to a third-party model (Grok or otherwise) gets
the full guarantee — secret redaction, PII scrub, personal-data-source
tool classification — by calling one function instead of re-deriving the
combination. It does not reimplement sensitive.py/redact.py; it composes
them. Existing call sites were migrated to call through here with no
behavior change (see test/test_sensitive_redaction.py, unchanged and
still green, and test/test_payload_gate.py for standalone coverage).
"""

from __future__ import annotations

from .redact import redact_pii, redact_string
from .sensitive import (
    is_sensitive_tool,
    structural_tool_result_preview,
    structural_tool_use_summary,
)


def scrub_text(text: str) -> str:
    """Generic freeform-text gate for anything about to be forwarded to a
    third-party model: secret-pattern redaction, then PII scrub. Safe on
    assistant/user reasoning text, notification bodies, screen tails —
    anything not scoped to a specific tool call."""
    return redact_pii(redact_string(text))


def gate_tool_use(tool_name: str | None, input_str: str) -> tuple[bool, str]:
    """Classify + gate a tool_use payload before it reaches a third-party
    model. Returns (is_sensitive, summary): summary is a structural-only
    stand-in when the tool is a personal-data source, otherwise the
    secret-redacted raw input. Callers that need to gate the matching
    tool_result later must retain the `is_sensitive` flag themselves
    (sensitivity is a property of the tool CALL, not re-derivable from the
    result alone)."""
    sensitive = is_sensitive_tool(tool_name, input_str)
    summary = (
        structural_tool_use_summary(tool_name)
        if sensitive
        else redact_string(input_str)
    )
    return sensitive, summary


def gate_tool_result(sensitive: bool, ok: bool, raw: str, preview_cap: int = 500) -> str:
    """Gate a tool_result payload given the sensitivity already classified
    at its matching tool_use. `raw` should be the FULL result string (not
    pre-truncated) — the sensitive branch's size bucket is computed over
    len(raw) in full; only the non-sensitive redacted preview is capped
    to `preview_cap` chars. Pass an already-truncated `raw` (and matching
    `preview_cap=len(raw)`) if the size bucket itself should reflect a
    caller-side truncation instead."""
    if sensitive:
        return structural_tool_result_preview(ok, len(raw))
    return redact_string(raw[:preview_cap])
