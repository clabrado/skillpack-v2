"""
latchlib/sensitive.py — sensitive-tool classification for the steerer digest.

Ticket #1899 (Vector B): the steerer forwards a per-decision digest of the
live Claude session to `grok -p` — full assistant/user reasoning text, plus
up to 500-char raw previews of every tool_use input and tool_result. Only
secret-*pattern* redaction existed (redact.py) — nothing stripped PII or
message-like content read from personal-data sources (iMessage, Mail,
Safari, Contacts, generic $HOME file reads of those stores).

This module answers ONE question: "did this tool call touch a personal-data
source?" — used by jsonl_tail.py and run.py to decide whether a tool_use /
tool_result frame gets its normal (rich) content, or a structural-only
summary (tool name + ok/error + size bucket, no raw text).

Deliberately narrow scope (chosen over a blanket "no $HOME reads" rule,
which would gut steering quality for the common case — coding sessions
whose repos also live under $HOME): classification only fires for
identifiable personal-data MCP tools/paths, not code/project files. See
test/test_sensitive_redaction.py for the code-session-unaffected proof.
"""

from __future__ import annotations

import re

# MCP tool-name prefixes that are inherently personal-data sources — any
# call through them is sensitive regardless of arguments.
_SENSITIVE_TOOL_PREFIXES = (
    "mcp__imessage__",
    "mcp__claude_ai_gmail__",
)

# Filesystem / generic-tool (Read, Bash, Grep, Glob, WebFetch, etc.) inputs
# that reference known personal-data stores on this Mac. Matched against the
# tool's JSON-serialized input, not its output — catches `Bash: sqlite3
# ~/Library/Messages/chat.db ...`, `Read: ~/Library/Mail/...`, etc.
_SENSITIVE_PATH_PATTERNS = tuple(
    re.compile(p, re.I)
    for p in (
        r"Library/Messages",
        r"chat\.db",
        r"Library/Mail\b",
        r"Library/Safari\b",
        r"History\.db",
        r"Bookmarks\.plist",
        r"Library/Application Support/AddressBook",
        r"Contacts\.sqlite",
        r"Library/Calendars\b",
        r"Photos Library\.photoslibrary",
    )
)


def is_sensitive_tool(tool_name: str | None, tool_input_str: str | None = None) -> bool:
    """True if this tool call is a personal-data source (iMessage, Mail,
    Safari/Contacts/Calendar file stores) that should never forward raw
    content to the Grok digest — structural signal only."""
    name = (tool_name or "").lower()
    for prefix in _SENSITIVE_TOOL_PREFIXES:
        if name.startswith(prefix):
            return True
    if tool_input_str:
        for pat in _SENSITIVE_PATH_PATTERNS:
            if pat.search(tool_input_str):
                return True
    return False


def structural_tool_use_summary(tool_name: str | None) -> str:
    return f"«sensitive tool_use scrubbed — tool={tool_name or '?'}»"


def structural_tool_result_preview(ok: bool, raw_len: int) -> str:
    status = "ok" if ok else "error"
    bucket = (
        "empty" if raw_len == 0 else
        "small" if raw_len < 200 else
        "medium" if raw_len < 2000 else
        "large"
    )
    return f"«sensitive tool_result scrubbed — {status}, size={bucket}»"
