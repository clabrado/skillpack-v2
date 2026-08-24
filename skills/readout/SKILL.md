---
name: readout
description: >-
  A plain-English, verified status readout of the current work — what's
  actually done, what's left, blockers, recommended next steps, and what
  Chris (the sovereign user) needs to decide or provide. Not a raw artifact
  dump (see /status) — this is the narrated synthesis, still bound to
  evidence. Triggers - "/readout", "give me a readout", "status readout",
  "where are we", "sovereign readout", "what's the state of things".
argument-hint: "[optional: focus this session/ticket/epic — default is everything in scope right now]"
---

# /readout — plain-English, verified status

Answer exactly these six questions, in this order, about the current work
(the active session's task, or the ticket/epic/topic named in the argument
if one was given). Nothing more, nothing less — this is not an invitation
to write a status novel.

1. **What is the current, verifiable, plain-English status?**
   One or two sentences. State it the way you'd say it out loud, not the
   way a dashboard would render it.
2. **What has been accomplished?**
   Short descriptions, one line each. Real deliverables only — a passing
   test, a merged commit, a ticket closed, a file written. Not "worked on."
3. **What is left to do?**
   Short, concrete list. If genuinely nothing is left, say so plainly.
4. **Any blockers or concerns?**
   Name them specifically — a permission gate, an unverified claim, a
   design fork, a dependency on something outside your control. If none,
   say "none" — don't manufacture a concern to seem thorough.
5. **Recommended next step(s), if any.**
   Zero, one, or a short list. Skip this question entirely (don't pad it)
   if there's genuinely no recommendation to make.
6. **What do you need from me as the sovereign user?**
   A decision, an approval, a credential, a piece of context only Chris
   has, or explicitly "nothing." Never leave this implicit.

## Ground rules (non-negotiable, not stylistic preference)

- **Every claim in sections 1–2 must be checked, not remembered, before you
  say it.** Re-run the check (`git log`, `git diff --stat`, a test command,
  a cortex query, an artifact's own state) rather than trusting your own
  prior summary earlier in the conversation — a claim that was true three
  tool calls ago may not be true now.
- **Calibrate.** If something is assumed rather than verified, mark it
  assumed. If you don't know, say "I don't know" in that section rather
  than filling the gap with a plausible-sounding sentence.
- **Quote the artifact**, briefly, when a claim needs backing — a commit
  SHA, a test count, a ticket state, a file path. Don't paste a full log
  dump into the readout; that's what `/status` is for. One line of
  evidence per claim is enough.
- **No unmeasured fields.** If a number wasn't actually counted this turn,
  don't state it. Omit it or say it's unmeasured.
- **Plain English over jargon.** This is for a human reading on their
  phone, not a machine parsing a schema. Short sentences. No headers-for-
  the-sake-of-headers beyond the six numbered questions above. See
  "Output language rules" below for the binding detail on how this is
  enforced.
- **Brief.** Each of the six answers is typically 1–4 lines. A "none" or
  "nothing" answer is a complete answer, not a gap to fill with prose.

## Output language rules (binding, not stylistic preference)

These apply to every section above, and to any iMessage copy of this
readout. This is a language rule, not an evidence rule — it changes how
you say things, never how much you check before saying them.

- **Plain English.** Write for someone who is competent but not inside
  this codebase. Say what a thing actually does in ordinary words before
  — or instead of — naming it. "A separate small program hands out
  permission slips that expire" beats "the warden mints TTL'd envelopes."
- **No analogies, similes, or metaphors.** No "like a...", no "think of
  it as...", no figurative comparisons of any kind. Describe the real
  mechanism, not something it resembles.
- **Jargon gets translated or dropped.** Internal/estate names (warden,
  envelope, mint, countersign, drain, lane, actuator, floor, witness,
  plane, and terms like them) are fine to use only when the same sentence
  also says plainly what the thing does. Never lead with the internal
  name alone and leave it unexplained.
- **Numbers over adjectives.** Say "105 of 223 have proof behind them,"
  not "many are unproven." If you have the count, use it; if you don't,
  say so rather than reaching for an adjective.
- **Evidence bar is unchanged.** Everything in "Ground rules" above still
  applies in full — verified vs. assumed, quote the artifact, no
  unmeasured fields, "I don't know" when that's the truth. Plainer
  language is not permission to check less or claim more.
- **iMessage copy.** When this readout goes out as an iMessage, it
  follows every rule above and additionally stays short-lined and
  phone-readable — short sentences, no wall of text, no headers.

## Not this skill

- A raw, uninterpreted artifact dump (latch sessions, board counts, git
  head, service reachability) → `/status`.
- Deep forensic reconstruction of what happened across a long session →
  read back through the conversation yourself; `/readout` synthesizes
  from what's already verified, it doesn't re-investigate from scratch
  unless a claim in sections 1–2 needs re-checking to stay honest.
