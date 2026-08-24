# Spec — /steer quota fallback (cloud-primary → local rtx4080 on engine failure)

_Status: DESIGNED, not built. Filed 2026-07-18 for later._
_Home: `~/Projects/latch` · touches `client/steerer.py` (shared — both machines' steering depends on it)._

## Problem

On the Mac Mini, `/steer`'s Tier-1 engine is **cloud Grok 4.5** (the flat SuperGrok
subscription pool). When that pool is exhausted, cloud calls return **402** (has happened
once in practice). Today the steerer **fails loud and stops making real decisions** — an
unattended run effectively goes *blind* until quota resets. That's the worst failure mode
for a walk-away tool: it reports "supervised" while no longer judging anything.

See the routing context: `docs/steer-routing.md` and `docs/steer-routing-architecture_v1.html`.

## Goal

When the cloud engine fails for a **quota/availability** reason, **degrade to the local
rtx4080 engine (gpt-oss:20b)** for the rest of the run — *degraded but still watching* —
instead of going blind. Local is a **fallback only**, never the primary tier, and never a
per-decision "easy vs hard" classifier (that three-tier idea was dropped — see
`steer-routing.md` for why it's redundant given the model-free pre-gate).

## Why this is the right and only local improvement for the Mini

- The model-free pre-gate already handles the easy decisions for free; everything reaching
  Tier-1 is a hard judgment call. So local's role is strictly "better than no judge at
  all," which only applies when cloud is unavailable.
- "Cloud spend" here is **quota, not dollars** (flat subscription) — the risk being
  mitigated is pool exhaustion, exactly the 402 case this handles.

## Design

### Trigger
Reuse the **existing engine-error classifier** in `client/steerer.py`
(`_classify_engine_error` / `_ENGINE_ERROR_PATTERNS`). It already labels failures as
`payment` (402), `auth` (401), `ratelimit` (429), `transient` (5xx/timeout).

- **Fall back to local on:** `payment` and `ratelimit` (quota/availability — won't self-heal
  within the run).
- **Do NOT fall back on:** `auth` (401 — misconfig, local won't help; keep failing loud) or
  `missing` (CLI absent). `transient` (5xx/timeout) should retry cloud a bounded number of
  times first, then fall back.

### Mechanism
- On a fall-back trigger, switch the engine for the remainder of the run to the local
  command — i.e. behave as if `LATCH_GROK_CMD='opencode run'` (pointed at rtx4080
  gpt-oss:20b at `reasoningEffort: medium` — NOT high; high is proven broken for this
  model, runaway reasoning / empty output) had been set. Make it a runtime switch inside
  the steerer's engine layer, not an env mutation.
- Config knob to opt in / point at the local engine, e.g. `LATCH_GROK_FALLBACK_CMD`
  (unset → no fallback, preserves today's fail-loud behavior exactly). Keep the default OFF
  so nothing changes for anyone who doesn't set it.
- Prefer a lean **direct HTTP** call to the local `/v1/chat/completions` (schema-enforced)
  over routing through grok-build's CLI — the CLI carries ~18–19k fixed prompt tokens per
  call (its own agent scaffolding), which dominates latency on bandwidth-limited local
  hardware. (This "lean http engine adapter" is a reusable piece; if it's built for this,
  note it in the routing doc.)

### Degraded mandate (important)
When running on the local fallback, **tighten the steerer's own mandate**: bias hard toward
`wait`/`blocked`, avoid confident `redirect`. gpt-oss:20b is a materially weaker judge than
Grok 4.5 for adversarial "is this drifting" calls — a weak judge that mostly waits is safe;
a weak judge that confidently redirects is not. Implement via a prepended instruction to the
fallback engine's prompt.

### Observability
- Log every fall-back transition with a `degraded_engine` marker + the classified reason,
  in the steerer log (`~/.latch/logs/steerer-<sid>.log`).
- Include the degraded state in the terminal iMessage so the operator knows the run
  finished on the weak judge, not cloud.

## Acceptance criteria (testable)

1. With `LATCH_GROK_FALLBACK_CMD` **unset**, behavior is byte-for-byte identical to today
   (fail-loud on 402, no fallback) — no regression for Claude `/steer` on either machine.
2. With it set, a simulated cloud **402** flips the engine to local for subsequent
   decisions and logs a `degraded_engine` transition.
3. A **401 (auth)** does NOT fall back — it still fails loud.
4. `transient` (5xx/timeout) retries cloud a bounded number of times before falling back.
5. While degraded, the fallback engine's prompt carries the tightened wait/blocked mandate.
6. The terminal notification states the run ended in degraded/local mode.
7. Fallback engine uses `reasoningEffort: medium` (verify no runaway / empty-output failure
   on a real coding-scale decision).

## Explicit non-goals

- No per-decision easy/hard routing (the dropped three-tier design).
- No change to the primary path (pre-gate → cloud) when cloud is healthy.
- No new hardware. This is purely a resilience improvement on the existing rtx4080.

## Verify before calling done

Run a real steered session, force a 402 (or stub the classifier), and confirm from the
steerer log + a live `/api/ps` on the RTX box that decisions actually routed to gpt-oss:20b
and the run stayed alive — not just that a unit test passed.
