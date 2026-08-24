---
name: turbo
description: >-
  Sets the supplied goal as this session's standing directive, then works it
  autonomously — analyze, code, verify, repeat — until every technical task
  the goal requires is genuinely complete, real artifacts checked, not
  claimed. Finishes with a full /readout printed to console and the same
  readout texted to Chris via iMessage. Triggers - "/turbo", "turbo mode",
  "go turbo on X", "turbo <goal>".
argument-hint: "<goal description>"
---

# /turbo — standing goal + autonomous build loop + readout finish

Composes three things that already exist separately in this estate into one
command: a standing goal (the persistence model `/goal` uses), the
self-paced work loop `/loop` uses in dynamic mode, and the six-question
`/readout` format — plus a text to Chris at the end so he doesn't have to be
watching the terminal.

**Honest limitation, stated up front:** `/goal` is a built-in CLI primitive
(same family as `/clear`, `/compact`) — not a skill, not invocable
programmatically from inside another skill's instructions. Turbo does not
literally call it. It reproduces the same *effect* — a standing directive
this session will not abandon or quietly drop until satisfied — through its
own explicit narration plus the real, working `ScheduleWakeup` dynamic-loop
mechanism (the same one `/loop`'s no-interval mode uses). If a future
version of the harness exposes `/goal` as an invocable skill, prefer calling
it directly instead of this workaround — check the available-skills listing
each time this runs, don't assume today's limitation is permanent.

## Step 1 — parse the goal

Everything after `/turbo` (or `turbo:`) is the goal, verbatim. If it's
empty or too thin to act on (no concrete deliverable, no way to tell when
it's done), ask one real question rather than inventing scope.

## Step 2 — establish the standing directive

State plainly, once, before doing anything else:

> Turbo goal set: `<goal, verbatim>`. Working until every technical task
> this requires is genuinely complete — will not stop, hand back, or ask
> "what next" before then.

This is the persistence contract for the rest of the session on this task:
- A tool-blocking or Stop-hook-style condition is not available here (see
  the limitation note above) — the discipline is self-imposed. Hold to it
  the same way: don't declare done on a plausible-sounding claim, don't
  quietly drop the goal because something else came up, don't ask
  Chris "should I continue?" once he's already said `/turbo`.
- If Chris sends something clearly unrelated mid-loop, handle it as an
  interruption (per the local-command-caveat / mid-turn-message handling
  already built into this environment), but the turbo goal remains active
  underneath unless he explicitly says to drop it or gives a new `/turbo`.
- If real, external circumstances block progress (missing credential, a
  decision only Chris can make, a resource he told you not to touch right
  now — see the H15/GX10 precedent from 2026-08-21: he can pause a turbo
  loop the same way he paused that drain, and the loop must honor it, not
  push through), text Chris the blocker via iMessage and hold — this is
  not the same as the loop being "done."

## Step 3 — work the loop

Each iteration:
1. Assess what's actually left against the goal — re-check state (git log,
   test output, ticket/board state, whatever the goal's domain is), never
   trust your own memory of a prior iteration's result.
2. Do the next real unit of work: write/fix code, run the actual command
   that proves it, read the actual output. No stubs, no "should work",
   no unmeasured claims — this estate's whole engineering bar (CLAUDE.md
   §3) applies here same as anywhere else.
3. Decide: is every technical task the goal requires now genuinely done?
   - **Not yet** → call `ScheduleWakeup` to continue: `prompt` is
     `/turbo <goal, verbatim>` so a resumed session re-enters this same
     skill; `delaySeconds` per the tool's own cache-aware guidance
     (1200–1800s for an idle-style tick with nothing specific to watch;
     shorter and matched to the real cadence if you're actively polling a
     specific external thing — a drain, a build, a CI run; arm a `Monitor`
     with `persistent: true` first if one isn't already running and the
     next step is genuinely event-gated, so the event itself wakes you
     rather than a blind poll). This ends the turn — the harness re-invokes
     you on the wakeup or the monitor's notification.
   - **Genuinely done** → proceed to Step 4. Do not loop past completion
     just to "double check" — that's its own kind of unverified busywork.
   - **Genuinely, externally blocked** (not just difficult) → text Chris
     the specific blocker via iMessage (see Step 4's send command), then
     `ScheduleWakeup` with a delay appropriate to how fast that block might
     clear, `noop: true` if nothing new happened this tick.

## Step 4 — finish: readout to console AND to Chris

Once the goal is verifiably complete, produce a `/readout`-format report —
same six questions, same ground rules (every claim in 1–2 re-checked this
turn, not remembered; calibrate assumed vs verified; quote the artifact
briefly; no unmeasured fields; plain English; brief):

1. Current, verifiable, plain-English status
2. What was accomplished (real deliverables only)
3. What's left to do (should be "nothing" if you're calling this done)
4. Blockers or concerns (name them, or say "none")
5. Recommended next steps, if any
6. What's needed from Chris, if anything (or "nothing")

Print this to the console as your normal response text — this is the
"console" delivery. Then send the SAME readout text to Chris via iMessage
so he gets it even if he's not watching the terminal:

```bash
"${SKILLPACK_NOTIFY_BIN:-/opt/homebrew/bin/imsg}" send \
  --to "$SKILLPACK_NOTIFY_TO" --service imessage \
  --text "<the six-question readout, plain text>"
```

If `SKILLPACK_NOTIFY_TO` is unset, deliver the readout to the console
ONLY and say plainly that no message was sent — never silently skip the
delivery, and never guess a recipient.

Keep the iMessage version tight (phone-readable — short lines, no heavy
markdown) even if the console version has more room to breathe; both must
say the same thing, just formatted for their medium.

## Step 5 — stop cleanly

Call `ScheduleWakeup` with `stop: true` (no other fields) to end the loop.
If a `Monitor` was armed anywhere in the loop, `TaskStop` it too. This is
the normal, successful ending — not a failure state.

## Not this skill

- Doesn't replace `/goal`'s real Stop-hook enforcement if that ever becomes
  callable — see the limitation note in the header.
- Doesn't replace `/loop <interval> <prompt>` for genuinely periodic,
  indefinite monitoring (e.g. "check the deploy every 20m forever") — turbo
  is for a goal with a real finish line, not an unbounded watch.
- Doesn't replace a plain `/readout` when the ask is just "what's the
  status" on work already in flight — that's a status check, not a new
  autonomous loop.
- Doesn't skip the offer-cloud-first behavior `/loop` has for genuinely
  long-cadence work — if the goal is realistically going to take many
  hours or span session restarts, say so plainly and suggest `/schedule`
  instead of silently running a session-bound loop that dies when the
  terminal closes.
