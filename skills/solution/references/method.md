# /solution method

## Why this shape
The brief is a document a seller can talk from and a customer architect can check line by line.
The talking points and outcomes come first, then the solution, then the proof. The research front
end (lanes → knowledge graph → author → one adversarial QA) is fixed. **What** gets researched and
**which** sections appear is decided fresh from each run's evidence.

## Framing (before any research)
Work through these against the sources, in writing, in BRIEF.md:
1. **Literal ask vs. real problem.** What did they ask for, and what's actually at stake (risk,
   revenue, safety, cost, time, reputation)? Quote the line that shows the stake.
2. **Desired outcomes**, ranked. Phrase each as a change the customer would notice, not a feature
   we ship. Tie each to evidence.
3. **Stakeholders.** For each: what they need to believe, and what would stop them.
4. **Constraints that decide the design**: budget or metering, timeline or freezes, security or
   compliance, skills, existing tooling, contracts. These often matter more than capability.
5. **Inverted read.** Assume the obvious recommendation is wrong. What would explain that? Look
   for silence, deferrals, absent stakeholders, claims nobody checked.
6. **Questions** the brief must answer, plus the unknowns that would flip the recommendation.

## Lane patterns (a menu to adapt or reject, never a default set)
Pick, merge, split or invent lanes so each one answers framing questions *this* evidence raised.
Common shapes:
- **Source-link lane**: verify a load-bearing link from the primary source.
- **Capability-truth lane**: what our product can and can't do for outcome X (docs, release
  notes, GA/preview status).
- **Counterpart-surface lane**: what the third party (vendor, platform, process, data source)
  exposes, and how (APIs, exports, events, limits, auth, cost).
- **Constraint lane**: verify a design-deciding constraint (pricing, metering, regulation, data
  residency, change windows).
- **Alternatives lane**: how others solve it today: incumbent tools, DIY, competitors, the
  customer's own team. Parity and gaps only, no bashing.
- **Account-context lane**: whatever internal connectors exist (CRM, usage, mail, chat, call
  recordings): history, commitments, consumption, prior asks.
- **Precedent lane**: references, community or hub examples, prior briefs, similar customers.
- **Outcome-proof lane**: how success would be measured, and whether that's feasible.

**Self-check before fan-out** (write the answers in BRIEF.md §Run plan):
- Does every lane cite the evidence line or question that created it?
- Does every top-ranked outcome have at least one lane gathering proof for it?
- Is there a lane that tries to break the leading hypothesis?
- Could this plan have been written without reading the sources? If yes, redo it.
- Did you assume a connector, product or integration pattern the evidence doesn't point to? Remove it.

## Document structure (Letter pages; length follows the evidence, typically 8–16)
**Fixed spine**, always present, in this order:
1. **Cover**: kicker, a headline that states the play, the bottom line, up to 4 stat cards
   (sourced numbers only; fewer is fine), up to 3 theme cards, recommended moves.
2. **Executive summary**: the problem behind the ask, ranked desired outcomes, the play, the main
   threat to it, "fix before the next touch" (corrections to the source claims), open questions.
3. **Talking points**: for each stakeholder or outcome, what to say, the proof behind it
   (citation), and the likely objection with its answer. Include "say instead" lines for any claim
   that needs correcting.
4. **Solution options** S1..Sn: how each works, its status or fidelity, what it costs or needs, and
   a verdict, plus a simple ASCII flow where a flow exists. Then outcomes × options coverage and a
   phased plan with measurable exit criteria.
5. **Next steps**: actions with owners, asks of each side, and success criteria for any pilot or POC.
6. **Appendices**: sources (every public URL, grouped, so the customer can verify) · source-claim
   verdicts · source coverage, including failures and unavailable connectors · adversarial QA
   (findings + dispositions).

**Evidence-driven sections**: the author adds only what this evidence warrants, e.g. introduction
and glossary, the counterpart's surface (what it exposes and what it doesn't), target
architecture, alternatives baseline, account context, standard and inverted analysis,
triangulation table, constraint or economics analysis, risk register, timeline, next-meeting
angle. A section with no evidence behind it is cut, not padded.

## Talking-point rules
- Lead with the customer's outcome, then the capability, then the proof. Never lead with a feature list.
- Each point is short enough to say aloud, with a citation or internal tag.
- Every claim our side has made or will make is checked. Overclaims get a corrected line.

## Lessons from past runs (generalized: watch for the class, not the instance)
- AI summaries in a primary source mix true and loose claims (e.g. getting the data path wrong).
  Verify each one.
- WebFetch returns summaries, so mark quotes "as returned by fetch" unless raw. Some sites block
  fetchers, and the Wayback Machine or a browser MCP often works. Portals behind logins: record
  exactly what was publicly visible.
- CRM queries often can't filter long-text fields. Filter by name or subject and say so.
- Connector searches fail intermittently (401/500). Report it as a tool failure, not as "nothing found".
- Some constraint usually decides the design (credential storage, API metering, component
  co-location, change windows). Find and verify it before proposing options that depend on it.
