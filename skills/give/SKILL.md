---
name: give
description: >-
  Collect every decision that is genuinely the user's to make — across the live
  session, the project docs, the tracker and the checks — and put them to them
  in plan mode: the fork, the real options, what each costs, a recommendation,
  and what happens if they do nothing. Read-only. Triggers: "/give", "give me
  my decisions", "what am I deciding", "what needs my ruling", "what's waiting
  on me".
---

# /give — the decisions waiting on the user

**Give them their decisions, in plan mode.**

They are asking one question: *what is sitting on me right now?* Answer it with
a short list of real forks, each one ready to rule on. Nothing else.

## Do this

**1. Enter plan mode first.** Call `EnterPlanMode` before gathering. This is a
read-only act by construction, and it is where the answer belongs.

**2. Gather, checking rather than remembering.** Sweep these, in order. Skip a
source with nothing in it — do not narrate empty sources.

- **This session.** Every fork you raised and they have not ruled on. These
  are the freshest and usually the most important.
- **The plan docs.** Roadmap, `NEXT*`, `TODO`, ADR or design files in the
  repo, newest first. Look for items marked "decision", "needs ruling",
  "owner decides", or "open question". Confirm each is still open before
  listing it.
- **The tracker.** Issues or tickets in a blocked, suspended or needs-human
  state — those states exist because a person has to look. Read-only queries
  only.
- **The checks.** CI or verification rows that are policy questions rather
  than defects — a live grant, a deliberate skip, a documented residual.
- **Anything needing a password.** `sudo`, a deploy or service restart, a file
  with a protection flag set. Only the user can do these, so they are
  decisions by default.

**3. Filter hard. This is the part that makes the skill worth having.**

Drop anything that is not actually theirs:

- **If you can decide it from the code, decide it — do not hand it over.**
  A routine judgement call dressed up as a decision wastes their attention.
- **Drop anything already ruled.** Check the session and the docs. Re-asking a
  settled question is the failure this skill exists to avoid.
- **Drop anything with no consequence either way.** If both branches lead to
  the same place, it is not a fork.
- **Never invent one to pad the list.** Zero decisions is a complete answer.

Keep it if, and only if: it needs their authority, their password, their
taste, or a fact only they hold — or it trades off two things they value and
the code cannot weigh them.

**4. Write each decision in this shape.** Four lines, no more:

- **The fork**, in one sentence, in plain words.
- **The options** — the real ones, usually two or three, each with what it costs.
- **Your recommendation**, and why, in one line. Always give one; "your call"
  with no view is an abdication. If you genuinely have no view, say why.
- **What happens if they do nothing** — the default is always an option and is
  frequently the right one. Name it, do not leave it implicit.

Order by consequence, not by how recently it came up. Security and anything
irreversible go first.

**5. PUT THEM TO THE USER WITH `AskUserQuestion`. This step is not optional.**

A list of forks is not a plan to approve — it is a set of questions to answer.
Handing over a decision list and asking "approve?" means nothing: approving a
question is not ruling on it.

- One question per decision. Real options, each with what it costs, and a
  recommendation. `AskUserQuestion` takes four questions per call, so more than
  four decisions means a SECOND call — never drop one to fit.
- **When a ruling needs a number — a cadence, a cap, an expiry, a limit — ask
  for the number as its own separate question.** State the ceiling, and say
  plainly which parts are unmeasured. Never pick it for them.
- A "do nothing" option belongs in every question, because it is always
  available and is often right.

**6. Only now call `ExitPlanMode`** — and the plan it presents is **what you
will now do about the rulings**, not the questions. Say which rulings mean
work, which mean deliberately doing nothing, and which need their password.

**A decision list is never the thing you ask approval for.**

**7. After they rule.** Act on what they ruled and nothing adjacent. If they
rule on three of five, the other two stay open — do not quietly action them,
and do not re-ask about them in the same breath. A ruling of "leave it" is a
real ruling: record it as deliberate so it does not come back later as a
finding.

## Rules

- **Read-only while gathering. No writes, no builds, no messages, no sudo.**
  Plan mode is the guard; do not work around it. `AskUserQuestion` IS permitted
  in plan mode — that is why step 5 fits before the plan is presented.
- **Verify each item is still open before listing it.** A decision settled an
  hour ago must not reappear. Check, do not recall.
- **Quote the artifact** behind each fork — a path, a check id, a ticket, a
  measured number. A decision without evidence is a rumour.
- **Plain English:** say what the thing does before naming it, no analogies,
  numbers rather than adjectives.
- **Never pick a limit, cap, or expiry for them.** State the ceiling and the
  trade-off; the number is theirs.
- **Say the count.** "Three decisions" up front, so they know the size before
  they read.
- **If there are none, say so in one line** and stop. Do not fill the space.

## Not this skill

- Verified status of work in flight → `/readout`.
- A raw dump of sessions, counts and reachability → a status command.
