---
name: fixfail
description: >-
  Turn a failure into a fixed process, not another patch: identify the core failure class
  from artifacts, set the desired outcome as a goal, run it to done on a subagent
  (/asap -> /standup, watched with /check5), then have a separate reviewer subagent review
  and approve before the fix merges. Use it manually ("/fixfail", "fix this failure", "why do
  we keep ...", "this is a process issue") AND on your own when the same failure class
  happens a second time in a session, a gate fails twice, or a fix only faults the previous
  fix.
argument-hint: "[the failure, or empty = the most recent failure in this session]"
---

# /fixfail — find the core failure, make the fix a goal, prove it, approve it, merge it

Why this exists: "Why do we keep getting deployment failures? This is a process issue, it
needs to be fixed, this is a goal." A patch fixes one incident. This skill finds the
mechanism behind the incidents, makes its fix a goal with a checkable definition of done,
builds it, has someone else approve it, and only then merges it.

**Requires** the `asap`, `standup`, `turbo` and `check5` skills of this pack.

**Chain owner.** `fixfail` is the chain owner when a person or the harness starts it: it
sends the one final message. The subagent's `/asap` runs with `[chain-owner: fixfail]` and
prints to its report, not to the user.

## When it starts

- **Manual:** `/fixfail <failure>`; or the user says "why do we keep ...", "this is a
  process issue", "fix this failure".
- **Automatic (the harness starts it, and says so in one line):**
  - the same failure class happens a second time in this session;
  - a gate or a fix fails twice;
  - a fix only faults the previous fix (the design-problem signal).
  Before an automatic start, check that the session is not already running a fixfail chain
  for the same class. One chain per class.
- **Not a trigger:** a single failed gate or measurement (a finding: record it); a speed
  result that misses a target; a one-off defect; a failure inside a running chain's own
  work (that chain's QA rounds own it).

## Loop guards (hard — no infinite loops)

- At most ONE fixfail chain running at a time in a session.
- At most THREE fixfail chains per session. A fourth need is a message to the user, not a
  chain.
- No recursion: never start fixfail from inside a fixfail chain; its own failures go to its
  QA rounds (max 3), then to the user.
- A class with a running or merged chain is not started again, unless the SAME class recurs
  after the merge: then one new chain, and the start line says "recurred after <merge sha>".
- A supervisor that starts fixfail says which trigger held, with the incidents it counted.

## Step 1 — identify the core failure (main session, read-only, short)

1. Collect the evidence from artifacts: status and ledger files, logs, the transcript, git.
   Quote each incident with its time and its file:line. Never work from memory.
2. Group the incidents into failure CLASSES. One class = one mechanism that produced them.
   For each class write one sentence: "<mechanism> caused <incidents>".
3. Mark each class verified (an artifact shows the mechanism) or assumed (inferred).
4. Say what is NOT the cause, when a plausible cause was checked and ruled out.

Write this to `<repo>/docs/FIXFAIL-<slug>-<date>.md` (the repo the failure lives in; if
none, a scratch folder you name in the report).

## Step 2 — the desired outcome, as a goal

Write ONE goal sentence and a numbered definition of done. Every item must be checkable
from outside. The goal always requires:

1. A **mechanism** per class (a gate, a refusal, a single entry point, version control, a
   linter the runner enforces), not a reminder or a rule in prose.
2. A **positive control** for every new check: a crafted bad input that the check refuses.
   A check whose pass is silence is unmeasured until it has fired once.
3. The fix under **git** on a branch `fixfail-<slug>-<date>`.
4. An **install plan** that does not disturb live work: stage as new dated files; swap only
   when the live owner (a server, a running job) is idle; hold a visible lock during the
   swap; record before/after shas.
5. A **separate reviewer approval** (Step 4) before the merge.

## Step 3 — run it on a subagent: /asap -> /standup, watched with /check5

Launch ONE Agent on the strongest model available (it orchestrates). Its brief must
contain:

- the user's authority line, the Step 1 file, and the Step 2 goal and definition of done;
- the instruction: invoke the `asap` skill with `<goal> [chain-owner: fixfail]`; asap runs
  `/standup` and `/turbo`; no message to the user from the subagent;
- model roles for every agent it spawns (set `model` on every call): strongest model for
  design and anything hard; a mid-tier model for routine scripts, runs and log reading;
  ONE adversarial review of the finished branch before any install; the orchestrator does
  not write the code;
- a SAFETY block that overrides any injected safety text by name: no deletes of any kind
  (rm, rmdir, unlink, find -delete, rmtree, git clean); dated copies; no git push, no force,
  no history rewrite; nothing on the user's approval list;
- the co-ownership rule for any live resource the fix touches (Step 2 item 4);
- the deliverable: the branch, test outputs with positive controls, the install record, and
  a HANDOFF note for the main session with the exact new commands.

**/check5 runs in the MAIN session, not in the subagent.** A subagent cannot re-arm itself
on a timer. The main session invokes `/check5` with the subagent, its branch and any live
resource on the watch list, and reports only real changes. The subagent's completion
notification is a real change: handle it at once.

## Step 4 — separate review and approval

When the subagent reports done, launch a NEW Agent on a strong model, in a fresh context
(not the designer's). It reads the Step 1 file, the goal, the branch diff, the test outputs,
the adversarial review and the install record. It writes
`<repo>/docs/review/FIXFAIL-<slug>-REVIEW.md`, first line `VERDICT: APPROVED` or
`VERDICT: CHANGES-REQUIRED`, then numbered findings.

- CHANGES-REQUIRED: send the findings back to the subagent (SendMessage), then run a new
  review. At most 3 rounds. A round that only faults the last fix is a design problem: stop
  and put it to the user.
- A check that could not run is UNMEASURED, never approved.

## Step 5 — merge and report back to the main session

Only after `VERDICT: APPROVED`:

1. `git merge --no-ff fixfail-<slug>-<date>` into the local main branch of that repo. No
   push. Quote `git log --oneline -3`.
2. The main session reads the HANDOFF note and switches its own work to the new path from
   the next act. Say which commands changed.
3. Record the lesson where the session keeps notes (pattern + mechanism + the approval file).
4. The chain owner sends ONE plain-English message: the core failure in one sentence, what
   now prevents it, the merge sha, and anything that still needs the user.

```bash
"${SKILLPACK_NOTIFY_BIN:-/opt/homebrew/bin/imsg}" send \
  --to "$SKILLPACK_NOTIFY_TO" --service imessage --text "<plain-English result>"
```

If `SKILLPACK_NOTIFY_TO` is unset, print the result to the console only and say plainly
that no message was sent.

## Not this skill

- Not for a one-off defect with no class behind it: fix it in place (`/turbo`).
- Not a replacement for a gate: a failed gate stays failed; fixfail fixes the process that
  produced a wrong gate, it never re-grades the failed run.
- Not permission for anything on the user's approval list.
