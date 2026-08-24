# LATCH — Session Supervisor for Claude Code

PTY wrapper around Claude Code that:

1. Passes the terminal through to you unchanged  
2. Streams output + semantic events to a loopback HTTP/SSE API  
3. Accepts keyboard-equivalent injects for a steerer process  

Remote Control (Anthropic phone/browser mirror) continues to work under the wrap.  
The steerer never uses Playwright or the RC relay.

**Latch and `/steer` are engine-agnostic.** The reference steerer defaults to
`claude -p` (Opus, pinned — STEER-01, 2026-07-31), with `grok -p` and any
generic CLI as first-class alternatives — see
[Engine-agnostic decision engine](#engine-agnostic-decision-engine).

## Important: how sessions become steerable

You do **not** hand the steerer a bare Remote Control URL.

```bash
# Terminal A
~/Projects/latch/bin/latch run --name gym -- claude
# banner: [latch] sid=a1b2c3d4  port=…

# Terminal B — always pass exact sid when multiple Claudes may be live
python3 ~/Projects/latch/client/steerer.py \
  --goal ~/Projects/latch/client/goalpack.example.md \
  --sid a1b2c3d4
```

Unwrapped `claude` sessions are **not** injectable.

### Multiple Claude sessions on the same box

This machine often runs several Claudes at once.

| Rule | Behavior |
|------|----------|
| Isolation | Each `latch run` = own sid, port, registry file |
| Listing | `latch ls` shows all live supervised sessions |
| Targeting | Prefer **exact sid** from the start banner |
| Ambiguity | `newest` / bare default **refused** if >1 live session |
| Names | `--name` only if unique; else require sid or `--cwd` |
| JSONL | Discovery skips transcripts claimed by other latch sessions |
| Unwrapped | Bare `claude` is invisible to latch |

```bash
latch ls
latch inject a1b2c3d4 "stay on the failing test only"
latch health a1b2c3d4
```

## Install

```bash
cd ~/Projects/latch
chmod +x bin/latch hooks/latch-hook.sh client/steerer.py
latch hooks install    # deep-merges hooks; keeps existing hooks
latch skills install   # symlinks skills/steer -> ~/.claude/skills/steer (the /steer skill)
# alias claude-g='~/Projects/latch/bin/latch run -- claude'
```

`skills/steer/SKILL.md` is the **only** skill latch requires — it's what the user
invokes (`/steer`) to hand a latched session to the steerer. It has no
further skill dependencies of its own; it only shells out to the `latch` CLI.
`latch skills install` symlinks it in rather than copying, so edits to
`skills/steer/SKILL.md` in this repo take effect immediately. `latch skills
uninstall` removes the symlink.

## Bootstrapped steer-guided sessions

You don't have to launch Claude, wait for it to come up, then type `/steer`
yourself. `latch run` execs its trailing args directly, and `claude "<text>"`
submits `<text>` as the session's first prompt — so a single command launches
a session that is steer-guided **from message one**:

```bash
latch run -- claude "/steer build the retry queue described in TICKET-42; \
stop when the integration test suite is green"
```

That one line: starts the latch-wrapped session, has Claude read `/steer`'s
own instructions, write the goalpack from your one-liner, and launch the
steerer — all before you type anything else. Useful for kicking off unattended
runs (cron, a script, `/workstream`, another orchestrator) where nobody is
sitting at the keyboard to type `/steer` after the fact.

If you're driving interactively and want to review Claude's first move before
handing off, use the two-step flow instead: `latch run -- claude`, then type
`/steer <goal notes>` once you're satisfied with the direction.

## Engine-agnostic decision engine

The steerer's "brain" is a pluggable engine (`EngineSession` in
`client/steerer.py`): send a prompt, get back JSON matching `DECISION_SCHEMA`
(`action`/`message`/`reasoning`/`evidence`). Every engine gets the same three
first-class properties — schema-or-fail-loud parsing, session continuity, and
engine-error classification. (STEER-01, 2026-07-31: Grok was dropped as the
default on cost — `grok -p` carried ~18-19K fixed input tokens per call from
its own agent scaffolding; the stripped `claude -p` engine measured ~700.)

Select with `LATCH_STEER_ENGINE` (`claude` | `grok` | `cmd`):

- **`claude` (default):** `claude -p` with engine-side `--json-schema`
  enforcement (decision read from the JSON envelope's `structured_output`),
  real continuity via `--session-id`/`--resume` (verified live 2026-07-31: a
  later `--resume` call recalled a token planted in turn 1), and structural
  error classification via the envelope's `is_error`/`api_error_status`
  (401/403→auth, 402→payment, 429→ratelimit, 5xx→transient, other 4xx→config).
  Cost-stripped by construction: `--system-prompt` replaces Claude Code's
  default scaffolding, `--tools ""`, `--setting-sources ""`,
  `--strict-mcp-config` — no CLAUDE.md, no MCP, no hooks. The latch session
  vars are scrubbed from the subprocess env so the engine can never feed
  events back into the session bus it is judging.
  Knobs: `LATCH_CLAUDE_MODEL` (default **opus** — pinned explicitly on every
  call, never inherited), `LATCH_CLAUDE_EFFORT` (`--effort`), `LATCH_CLAUDE_BIN`
  (default `~/.local/bin/claude-stable` if present, else `claude` on PATH).
- **`grok`:** the legacy engine, kept intact — `grok -p --json-schema` +
  `--session-id`/`--resume` (verified 2026-07-12). Knobs: `LATCH_GROK_MODEL`,
  `LATCH_GROK_EFFORT`.
- **`cmd`:** any CLI, via `LATCH_STEER_CMD='opencode run --model gpt-5.1-codex'`
  (`LATCH_GROK_CMD` still works as a back-compat alias; setting either implies
  `cmd`). The command is shlex-split (quoted args work) and the prompt appended
  as the final argv item. Parsing is strict-first: whole stdout as JSON, then a
  fenced ```json block; the legacy first-`{...}` scrape is a tagged last
  resort, and a failed parse is a classified `malformed` engine error, not a
  silent `wait`. Nonzero exits are classified against the error signatures. A
  cmd engine is **stateless**, so the steerer re-primes it every call with the
  full goalpack + a tail of its own recent decisions (honest approximate
  memory, vs. the resume-backed engines' genuine history).

Engine-failure detection fails LOUD for **all** engines: a persistent failure
(missing binary, auth, payment, rate limit, 5xx, malformed output) stops the
steerer and sends the "STEERER BLIND" notification instead of reporting
"supervised" while running blind.

Heterogeneity note (on the claude default): the steerer and the session it
steers share a vendor. Separation is role + context + pinned tier (an Opus
judge in its own conversation with a decision-only system prompt), not a
different model family — logged at startup, worth knowing when weighing how
much independent course-correction you're actually getting.

Token: `~/.latch/token` (path via `latch token`).

## CLI

| Command | Purpose |
|---------|---------|
| `latch run [--name N] -- claude …` | Start supervised session |
| `latch ls` | All live sessions (multi-session safe) |
| `latch tail <sid> [--raw\|--evt]` | SSE client |
| `latch inject [--cwd DIR] <sid\|name> "text"` | One-shot steer |
| `latch idle <sid>` | Exit 0 if idle |
| `latch health <sid>` | JSON health |
| `latch token` | Print token **path** only |

API (Bearer token, `127.0.0.1` only): `/v1/health`, `/v1/stream`, `/v1/inject`, `/v1/interrupt`, `/v1/hook`.

### Injection delivery contract (STEER-02, 2026-08-03)

`POST /v1/inject` accepts three optional fields and always returns an
`inject_id`:

| Field | Default | Meaning |
|---|---|---|
| `deliver_by_s` | `LATCH_INJECT_DELIVER_BY_S` else 600 | Per-item delivery deadline, **clamped 30–3600**. There is no "off" value; unparseable falls back to the default. |
| `on_deadline` | `expire` | `redirect` = at the deadline, deliver the newest queued item as an interrupting redirect and drop the rest as superseded. `expire` = drop it, loudly. |
| `queue_on_human_active` | `false` | Queue behind a typing human instead of returning 409. Only honoured for `when=idle` text. |

Deadlines are enforced by **latch**, in the supervisor's select loop — not by
any steerer. A steerer-side escalator dies with the steerer, which is how a
lane came to report supervised while nothing steered it. The sweep defers
(never cancels) while a human is genuinely typing.

Five semantic frames ride the existing bus and land in `~/.latch/audit.jsonl`,
each carrying the `inject_id`: `inject_queued`, `inject_delivered`,
`inject_deadline_redirect`, `inject_expired`, `inject_dropped`.

`GET /v1/health` and `~/.latch/sessions/<sid>.json` both carry an
`inject_queue` block (`depth`, `oldest_enqueued_ts`, `oldest_deliver_by`,
`delivered_total`, `expired_total`, `deadline_redirects_total`,
`human_active_rejects_total`, `dropped_total`, `last_delivery_ts`,
`last_reject`).

**"Supervised" is a predicate, not an assumption** — check all three: the
steerer PID is alive, its marker heartbeat (`latch steer --list`, flagged
`SUPERVISION STALE` past 120s) is fresh, and health shows nothing queued past
its `deliver_by`. A live PID alone proves nothing; the observed failure was a
steerer process that had stopped deciding.

Stdin bytes are classified before they set the human-active flag
(`latchlib/stdin_classify.py`): focus/mouse/DSR/DA/OSC replies from a
focused-but-idle terminal are not keystrokes. This also closes an
injection-DoS path — a session emitting `ESC[c` makes the terminal answer on
the supervisor's stdin, which used to pin the flag and lock the supervisor
out.

## Security

Inject = root-on-that-repo for the session cwd. Loopback + bearer + audit log + broadcast redaction.

## Runtime note

v1 supervisor is **Python** (`bin/latch`). `node-pty` fails on this host's Node 25; Phase 0 switched to stdlib PTY.

---

## v1.1 amendments (2026-07-11, post-live-review)

Hardened after real interactive-TUI verification. Changes:

1. **Hooks are the primary semantic feed.** This Claude build writes transcript
   JSONL lazily for fresh sessions, so the steerer can't rely on it. Added
   `UserPromptSubmit` + `PostToolUse` hooks; they publish `user_text` /
   `tool_use` / `tool_result` frames directly. `Stop` carries an ANSI-stripped
   `screen_tail`. JSONL tail remains as enrichment. Re-run `latch hooks install`.
2. **Mid-turn redirect.** New `redirect` inject mode + `latch redirect` +
   steerer `redirect` action: Esc-interrupt the running turn, settle, then type
   new priorities. Lets Grok shift direction without waiting for turn end.
   Verified live (interrupted a 90s task; Claude complied).
3. **Steerer watchdog.** `--watchdog N`: during a long turn with fresh activity,
   re-consult Grok mid-turn so it can redirect or let it ride. (Superseded in
   v1.2 — see below — this is now a dead-man's-switch backstop, not the primary
   trigger, and defaults to 300s.)
4. **Human-active retry fires on ticks, not just frames.** SSE yields a `_tick`
   each chunk (heartbeat every 15s); the human-active retry is checked there,
   so a silent session still gets its queued steer flushed and still notifies
   on `session_exit`. (No wall-clock/steer cap by default as of v1.2 — see below.)
5. **Non-blocking bus.** Per-client bounded queues; the PTY pump never writes a
   socket. A slow/dead SSE consumer drops only its own frames — the human
   terminal can never stutter. One writer thread per socket (no frame tearing).
6. **Exit-code fidelity.** `latch run` returns the child's real exit status
   (final `waitpid` after PTY EOF).
7. **No orphans.** SIGTERM/SIGHUP to the supervisor propagates to the child.
8. **JSONL slug fix.** Keeps the leading `-` (`-Users-beans-grok`); the fallback
   discovery path now actually resolves.
9. **Node implementation removed.** Python (`latchlib/`) is the only runtime.
10. **Foreign-session guard.** Hook events from a different `session_id` that
    inherited `LATCH_PORT` are ignored after identity locks.

`LATCH_NOTIFY=0` suppresses iMessage (for tests). Decision-engine selection:
`LATCH_STEER_ENGINE=claude|grok|cmd` (default `claude`; `LATCH_STEER_CMD` /
back-compat `LATCH_GROK_CMD` implies `cmd`) — see "Engine-agnostic decision
engine" above.

---

## v1.2 amendments (2026-07-12, calibration)

1. **SteerGate: materiality gate replaces clock-driven decisions.** A live
   multi-worktree run showed decisions firing every 20-60s because every turn
   boundary triggered one, with no memory of the prior verdict — produced
   back-to-back near-duplicate steers and a self-contradiction. Decisions are
   now gated on materiality (commit/test/error/distinct-targets score) with
   rising hysteresis after ungrounded steers, resetting on real progress. Time
   is a 300s dead-man's-switch backstop only.
2. **GrokSession: real continuing conversation, not hand-rolled memory.**
   Verified live that `grok -p --session-id` then `--resume` genuinely recalls
   prior turns, composed cleanly with `--json-schema`. One persistent session
   per steering run; full rules+goalpack sent once, later calls send only the
   new-events delta plus a compact goalpack reminder (dilution insurance, not
   a rebuild). Falls back to a fresh session if `--resume` ever fails.
3. **No default budget.** The steerer no longer auto-parses "max wall-clock
   minutes"/"max steer count" from the goalpack, no longer defaults to 45min/30
   steers, and never tells Grok a "budget remaining" figure — the operator
   decides duration, not the steerer. `--max-minutes`/`--max-steers` remain as
   explicit, off-by-default CLI flags for when a hard cap is genuinely wanted;
   otherwise a run continues until the engine calls `done`/`blocked` or you
   `latch steer --stop <sid>` yourself.

Validated with a real dual-session run (one design-heavy, one execution-heavy,
both patched): zero repeated/duplicate steers, zero self-contradictions, two
well-targeted single-shot redirects (a sleep-loop stall, a batching-rule
violation), both independently verified against real git history.

---

## v1.3 amendments (2026-07-31, STEER-01: engine swap)

1. **`claude -p` (Opus, pinned) replaces `grok -p` as the default decision
   engine.** Grok was dropped on cost — ~18-19K fixed input tokens per call
   from its own agent scaffolding; the stripped claude engine measured ~700
   input tokens (~$0.022/decision on Opus) with `--system-prompt`,
   `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`.
2. **The engine layer is first-class, not an override.** `EngineSession`
   replaces `GrokSession`: every engine (claude/grok/cmd) gets schema-or-fail
   parsing, session continuity, and engine-error classification. The old
   `LATCH_GROK_CMD` override — no schema, no memory, no error detection, naive
   `.split()` — was itself the bug; it survives only as a back-compat alias
   for the promoted `cmd` engine.
3. **Malformed engine output fails LOUD.** A failed decision parse is now a
   classified `malformed` engine error counting toward the fail-loud streak
   (stop + notify at 3 consecutive), instead of silently becoming `wait`
   forever.
4. **Continuity bug fixes** (latent in the grok path too): goalpack priming is
   keyed on whether a live engine session actually holds the goalpack
   (`session_id` set) — a failed first call, failed resume, or failed re-prime
   all cause the next call to re-send the FULL goalpack plus recent decisions,
   never a bare reminder.
5. **`latch steer` rejects unknown flags** instead of silently dropping them
   (`--open-prompt` is now passed through).

Validated with a real end-to-end acceptance run (throwaway latched session):
engine issued a `steer` (initial tasking), two `redirect`s on a planted
fibonacci drift signal — the second correctly escalating after the first was
ignored — then `done` with verified file-content evidence; all injects present
in `~/.latch/audit.jsonl`. Session recall verified live (`--resume` recalled a
turn-1 token with `--json-schema` still enforced); engine-error classification
verified live (bogus model → in-envelope 404 → `config`; dead resume id →
re-prime; 402-emitting cmd engine → `payment`; garbage output → `malformed`).

**Heterogeneity residual (stated, not solved):** with the claude engine the
steerer shares a vendor with the session it steers. Separation is role +
context + pinned Opus tier, not a different model family — less checker
independence than the Grok era nominally provided (though Grok's adversarial
value had measured at zero findings across 13 rounds with fabricated
citations). Enforcement of steerer-model ≠ session-model is NOT implemented:
latch does not know the interactive session's model. If vendor-level
heterogeneity is wanted later, `LATCH_STEER_ENGINE=cmd` + any external CLI is
the hook.
