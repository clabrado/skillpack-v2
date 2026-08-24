# /steer decision routing — where filtering runs, where judgment escalates

_Last verified: 2026-07-18 (live, against the running code + logs on the Mac Mini)._

This documents **how a `/steer` decision is routed** — what gets handled locally for
free, what escalates to an LLM, and which LLM — and why the Mac Mini and the MacBook
Pro are deliberately configured differently. It also records the standing
recommendation for the Mini so we stop re-deriving it.

## The tiers

A steerer (`client/steerer.py`) watches a latched session's live event stream and, on
each materiality-gated tick, must decide: **wait / steer / redirect / done / blocked**.
That decision passes through up to two tiers:

- **Tier 0 — the pre-gate (`_pregate_escalate`). Local, model-free, on-box, free.**
  Pure Python heuristic — *no LLM at all*. It answers one narrow question: "is this an
  obvious mid-work no-op I can just `wait` on?" It escalates (spends an LLM call) on
  anything that might need judgment — a turn boundary, a tool error, an error/traceback
  signal in the events, a goalpack drift-signal keyword, or a stall (same tool call ≥3×).
  Otherwise it auto-`wait`s for free. **It can ONLY ever choose `wait`** — it is
  structurally incapable of `steer`/`redirect`/`done`/`blocked`. Validated against 237
  real logged decisions: escalates 100% of actions and turn boundaries, skips only clean
  mid-work waits (~63% of calls). Controlled by `LATCH_PREGATE` (`on` default / `shadow`
  / `off`).

- **Tier 1 — the decision engine. One LLM, whichever is configured.**
  Everything Tier 0 escalates goes here for a real, schema-constrained judgment
  (`{action, message, reasoning, evidence}`). The engine is **cloud Grok 4.5 by
  default** (`grok -p` against the SuperGrok pool), or **any CLI** via the
  `LATCH_GROK_CMD` override (e.g. `LATCH_GROK_CMD='opencode run'` → a local model).
  The swap is **wholesale** — it redirects *all* Tier-1 judgment, not per-decision.

**Key point:** Tier 0 is not an LLM and does not "route easy decisions to a small
model." It's a free filter that removes obvious no-ops. Every *real* judgment costs a
Tier-1 LLM call.

## Where each tier physically runs

The pre-gate is **library code inside the steerer process**, not a shared service. It
runs on **whatever machine hosts the session being steered** — the same machine that ran
`latch steer`. The Mac Mini and the MacBook Pro each have their own independent latch
install, their own steerer, and their own copy of the pre-gate.

| Machine | Tier 0 (pre-gate) runs | Tier 1 (judgment) escalates to |
|---|---|---|
| **Mac Mini** (this box) | On the Mini | **Cloud Grok 4.5** (no `LATCH_GROK_CMD` set) |
| **MacBook Pro** | On the MacBook Pro | **Local rtx4080** — gpt-oss:20b via `LATCH_GROK_CMD='opencode run'` (zero cloud) |

There is no shared state between them. "The filtering happens on this computer" is true
*for sessions steered from this computer*.

## Standing recommendation for the Mac Mini — keep cloud primary, do NOT add a local judge tier

**Verdict: the current Mini setup (pre-gate → cloud Grok) is correct. Leave the primary
path alone.** Reasoning:

1. **The pre-gate already owns the "easy" tier — for free.** By the time a decision
   reaches Tier 1, it's there *because* the pre-gate couldn't auto-wait it: a turn
   boundary, an error, a drift signal, a stall. Those are the **hard** calls. Inserting
   a local gpt-oss:20b tier would hand the weak judge *only the decisions it's worst at*,
   while the free heuristic keeps the easy ones. That's backwards — there is no
   "easy-but-needs-a-model" band left for a local model to profitably fill.

2. **This is why gpt-oss:20b is "too weak to be a judge/router" *here specifically*.**
   The only work available to a Tier-1 model on the Mini is the adversarial
   "is-this-drifting / should-I-intervene" judgment — exactly the subtle call gpt-oss:20b
   is weakest at (20.9B, ~3.6B active MoE) and cloud Grok 4.5 is strongest at.
   (Separately verified this session: gpt-oss:20b at `reasoning_effort: high` is broken —
   runaway reasoning consumes the whole completion budget, empty output — `medium` is the
   only usable setting.)

3. **"Cloud spend" here is quota, not dollars.** The default engine uses the **SuperGrok
   subscription pool** (grok.com OAuth), *not* the metered console.x.ai API — so a cloud
   steer call costs **$0 marginal** until the weekly pool is exhausted. The pre-gate's
   ~63% call reduction already stretches that pool. The real risk is pool exhaustion (a
   402 has happened once), not per-call cost.

### The one improvement worth making: local as a *quota fallback*, not a tier

Add local rtx4080 **only** as a fallback for when cloud is unavailable (402/401/429/5xx —
which the steerer already classifies and fails loud on). On that failure, fall back to
gpt-oss:20b at `medium` with a **tightened mandate** (bias to `wait`/`blocked`, avoid
confident `redirect` when degraded). This converts the known real failure — steerer goes
*blind* on quota exhaustion — into *degraded-but-still-watching*. Weak judge beats no
judge, **as a fallback only, never as primary.** (Status: designed, not yet built.)

### What is explicitly NOT recommended for the Mini

- Inserting gpt-oss:20b as a *middle* tier between the pre-gate and cloud (it would only
  ever get the hard calls — see reason 1).
- Swapping Tier 1 wholesale to local (the MacBook Pro's config) — that gives up cloud
  Grok's judgment on the hard calls too, which is the opposite of what the Mini wants.

## The never-built third design (for the record)

A true three-tier split — pre-gate (free) → local rtx4080 for *easy* real judgments →
cloud Grok only for *hard/ambiguous* ones — was floated once (2026-07-17) as a
quota-fallback idea, then dropped in favor of the MacBook Pro's full local swap. It was
never built, and per reason 1 above it offers little on the Mini, because the pre-gate
already captures the free easy-decision savings without a model.
