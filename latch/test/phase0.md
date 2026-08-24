# Phase 0 — verification spikes (v1.1 re-verified)

Recorded 2026-07-11, re-verified after v1.1 patches on Mac Mini
(claude 2.1.201, Node v25.5.0, Python 3, macOS Darwin 25.5.0).

## 0.1 node-pty vs Python PTY
| Method | Result |
|--------|--------|
| `node-pty` spawn `/bin/bash` | **FAIL** `posix_spawnp failed` (arm64 prebuild present; chmod +x spawn-helper; rebuild — still fails on Node 25) |
| Python `os.openpty` + `fork` + `execvpe` | **OK** |

**Decision (reality wins):** runtime is **Python stdlib** (`bin/latch` + `latchlib/`).
Node sources removed from repo in v1.1 (were dead weight).

## 0.2 Interactive Claude TUI inject — VERIFIED LIVE
- `keys:["enter"]` cleared the folder-trust dialog -> SessionStart fired.
- `text` inject "What is 2+2?" -> composer received it, separate CR after 250ms submitted, Claude answered **4**.
- Multi-line uses bracketed paste `\x1b[200~...\x1b[201~` + separate CR.
- **redirect** (v1.1): Esc + 700ms settle + new text -> interrupted a running
  90-tick bash loop mid-turn and Claude replied `REDIRECT_OK`. **Verified live.**

## 0.3 Auth + redaction
- Wrong bearer -> **401**. Valid inject -> accepted.
- Human terminal unredacted (by design); broadcast path redacts `out` + evt strings.

## 0.4 Hooks — PRIMARY SEMANTIC FEED (v1.1 change)
- **Reality override:** on this build, fresh interactive sessions do NOT write
  their transcript JSONL promptly (project dir stayed empty across full turns).
  So hooks are primary, JSONL is enrichment.
- Installed events: SessionStart, **UserPromptSubmit**, **PostToolUse**, Stop, Notification.
- Verified live: UserPromptSubmit -> `user_text` frame; PostToolUse -> `tool_use`
  + `tool_result` frames (`Bash | echo HOOK_TOOL_TEST` -> `stdout HOOK_TOOL_TEST`);
  Stop -> `turn_stopped` with ANSI-stripped `screen_tail`.
- Deep-merge into `~/.claude/settings.json` preserved existing `log-model-fallback.sh`
  hooks; backup written `settings.json.bak-latch-<ms>`.
- Shim no-ops when `LATCH_PORT` unset; foreign claude sessions (different
  `session_id`) that inherit `LATCH_PORT` are ignored after our identity locks.

## 0.5 JSONL slug rule — CORRECTED
Claude keeps the LEADING separator:
```
/Users/beans/grok  ->  -Users-beans-grok
```
v1.0 stripped it (dead fallback). Fixed in `paths.cwd_to_project_slug`.

## 0.6 Exit-code fidelity — VERIFIED
child `exit 7` -> `latch run` returns **7** (v1.0 returned 0; final `waitpid`
after PTY-EOF added).

## 0.7 SIGTERM does not orphan child — VERIFIED
SIGTERM to supervisor -> child receives SIGTERM, is reaped, registry cleaned.

## 0.8 Backpressure — REBUILT
Per-client bounded queues (`bus._Client`); PTY pump only enqueues, never writes
sockets. Each SSE socket written by exactly one handler thread. Slow/dead client
drops its own frames (counter in `/v1/health`), terminal never stalls.
