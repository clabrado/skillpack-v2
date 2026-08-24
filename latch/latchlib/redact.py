from __future__ import annotations

import re

PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}", re.I),
    re.compile(r"xai-[A-Za-z0-9]{8,}", re.I),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        re.I,
    ),
    re.compile(r"Bearer [A-Za-z0-9._~+/=-]{16,}", re.I),
]


def redact_string(s: str) -> str:
    if not s:
        return s
    out = s
    for re_pat in PATTERNS:
        out = re_pat.sub(lambda m: f"«redacted:{m.group(0)[:8]}»", out)
    return out


def redact_bytes(b: bytes) -> bytes:
    try:
        text = b.decode("utf-8")
    except UnicodeDecodeError:
        text = b.decode("utf-8", errors="replace")
    red = redact_string(text)
    if red == text:
        return b
    return red.encode("utf-8")


# ---------------------------------------------------------------------------
# PII pattern scrub (ticket #1899, Vector B) — defense-in-depth for content
# that reaches the Grok digest OUTSIDE a cleanly-classified sensitive tool
# call: assistant/user reasoning text and terminal screen_tail. Those are
# freeform prose, so they can't be scoped by tool name the way tool_use/
# tool_result frames are (see latchlib/sensitive.py) — if Claude's reasoning
# quotes a phone number or email it just read from iMessage/Mail, this is
# the only net that catches it.
#
# Deliberately narrow: emails + phone numbers only. Broader "message-shaped
# text" heuristics were considered and rejected — too fragile (false
# positives on ordinary code/log prose would degrade steering quality for
# legitimate code-only sessions, which is the failure mode ticket #1899
# explicitly warned against). This is a supplement to, not a replacement
# for, the structural tool-level scrub — that's the primary, more reliable
# control.
PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
]


def redact_pii(s: str) -> str:
    if not s:
        return s
    out = s
    for pat in PII_PATTERNS:
        out = pat.sub("«redacted:pii»", out)
    return out
