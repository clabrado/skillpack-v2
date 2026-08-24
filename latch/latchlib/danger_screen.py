"""Destructive-text screen for injected payloads.

A TRIPWIRE, NOT A BOUNDARY — state this plainly wherever it is referenced.
Content filtering cannot make arbitrary text injection safe. The actual
boundary is four structural properties, and this module is none of them:

  1. TARGET SCOPING  — only latch-spawned PTYs are reachable at all. An
     unwrapped terminal is invisible to latch (see README).
  2. HUMAN INVOCATION — injection happens because Chris typed /drive.
  3. AUDIT           — every inject lands in ~/.latch/audit.jsonl.
  4. INTERRUPT       — Esc / ctrl-c / killing the supervisor.

What this screen buys is a stop on the ACCIDENT case: a well-formed
destructive command typed by mistake, or a model that helpfully "fixes"
something by removing it. It stops none of the deliberate cases, and the
bypasses are documented below so nobody mistakes it for defence.

DESIGN NOTES
- **Case-insensitive by construction.** macOS APFS is case-insensitive, and a
  denylist that misses `RM -RF` is a denylist that does not exist. This estate
  has been bitten by exactly that.
- **Scans the FULL NORMALISED PAYLOAD, never line-anchored.** A multiline
  bracketed-paste that smuggles a denied command onto line 7 must be caught.
- **Whitespace is collapsed** before matching so `rm    -rf` and `rm\t-rf` are
  the same string.

KNOWN BYPASSES (bypass attempts ship with the gate — estate rule):
  a) Obfuscation: `$IFS`, `base64 -d | sh`, variable indirection, homoglyphs.
     WILL DEFEAT THIS. Documented, not fixed — unfixable at this layer.
  b) Semantic laundering: inject benign text that INSTRUCTS the target agent
     to run the destructive command itself. Uncatchable here; the residual is
     carried by the target session's own permission model.
  c) Spelling a command via `keys` mode. Currently impossible — KEY_MAP holds
     no general character keys, only named keys plus the literals y/n. If a
     generic "char" key is ever added, THIS SCREEN IS BYPASSED. Do not add one.
"""
from __future__ import annotations

import re

# Patterns are matched case-insensitively against the whitespace-collapsed
# payload. Keep them narrow: a false positive is a refusal Chris must override,
# and an over-broad screen trains people to pass --force reflexively.
DENY_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+(-[a-z]*\s+)*-[a-z]*r[a-z]*f", "recursive force delete (rm -rf)"),
    (r"\brm\s+(-[a-z]*\s+)*-[a-z]*f[a-z]*r", "recursive force delete (rm -fr)"),
    (r"\bsudo\s+rm\b", "sudo rm"),
    (r"\bfind\b.*-delete\b", "find -delete"),
    (r"\bdd\s+.*\bof=/dev/", "dd to a device"),
    (r"\bmkfs(\.[a-z0-9]+)?\b", "filesystem format (mkfs)"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+push\s+.*--force\b(?!-with-lease)", "git push --force"),
    (r"\bgit\s+clean\s+-[a-z]*f", "git clean -f"),
    (r">\s*/dev/(sd|nvme|disk)", "redirect onto a raw device"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b", "host power state change"),
    (r":\(\)\s*\{.*\|.*&\s*\}\s*;", "fork bomb"),
    (r"\bchmod\s+(-[a-z]*\s+)*777\s+/", "chmod 777 on an absolute root path"),
    (r"\bcurl\b.*\|\s*(sudo\s+)?(ba)?sh\b", "curl pipe to shell"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(ba)?sh\b", "wget pipe to shell"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in DENY_PATTERNS]


def _normalise(text: str) -> str:
    """Collapse whitespace so `rm    -rf` and `rm\\t-rf` match the same pattern."""
    return re.sub(r"\s+", " ", text)


def screen(text: str) -> tuple[bool, str]:
    """Screen an injected TEXT payload.

    Returns (allowed, reason). `allowed=False` means refuse unless the caller
    passed an explicit override. Only ever applied to `text` mode — `keys` mode
    cannot spell a command (see KNOWN BYPASSES c).
    """
    if not text:
        return True, ""
    hay = _normalise(text)
    for rx, why in _COMPILED:
        if rx.search(hay):
            return False, why
    return True, ""
