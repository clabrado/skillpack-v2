---
name: solution
description: >-
  Agentic solution brief. Give it whatever context exists: a call transcript or recording link,
  a Slack DM or thread, an email, URLs, files, a prior brief, or pasted notes. It works out the
  problem behind the ask and the outcomes the customer wants. From that evidence it plans its
  own research: which questions matter, which lanes to run, and which of the available
  connectors and public sources can answer them. No fixed agent roster, no assumed product,
  integration pattern or competitor. Every lane writes cited findings and a knowledge-graph
  fragment; they merge into one graph. An Opus author then writes a Dynatrace-branded PDF in
  the /intel visual format. It has a fixed spine (bottom line, executive summary, desired outcomes, talking
  points, solution options + plan, next steps, appendices (sources, claim verdicts, coverage, QA)), and the author picks the other
  sections from what the evidence shows. Exactly ONE final adversarial QA pass, then fixes and a
  render check.
argument-hint: "<source...: call | transcript | slack-dm-with-<person> | permalink | email | url | file | \"paste\"> [--account <name>] [--target <topic>] [--goal \"...\"] [--competitor <name>] [--meeting <date>] [--out <dir>] [--send-to <slack-user>] [-clean]"
when_to_use: >-
  When the user wants a cited document that turns account context into desired outcomes,
  talking points and a verifiable solution path from any mix of sources (not tied to one call), whatever the domain (observability, security,
  AI, cost, migration, process, platform): "/solution", "build the solution brief", "what's
  our play for <account>", "how do we solve <problem> for <account>". Strictly a post-call
  write-up with a plan of action → /debrief. Multi-source call intel → /intel.
---

# /solution — agentic solution brief

Method: `references/method.md` (read it every run). Page skeleton: `assets/skeleton.html`
(markup and pattern library, not a fixed table of contents). If `private/` exists in this skill
folder, read the newest finished brief there for the quality bar, not the structure. Never copy
its facts, its research lanes or its section list.

**Requires the `/intel` skill installed next to this one** (shared build pipeline, page template
and render checker). Below, `<intel>` = the sibling `intel/` folder (normally
`~/.claude/skills/intel`) and `<skill>` = this folder.

## The one rule that makes this agentic

The evidence decides the run. The template doesn't. Each run derives its problem framing,
research lanes, sources and sections from what this context actually contains. If a lane or
section can't be traced to something in the evidence (a claim, a question, a gap, a stakeholder
need), drop it. If the plan could have been written before reading the sources, it's wrong:
redo it.

## Inputs

Any mix of the following. Ingest each with whatever connector is actually available this
session. Discover them at runtime (the tool list and ToolSearch), don't assume them.

| Input | How to ingest |
|---|---|
| Call: Teams/Stream recap link, Gong, Krisp, transcript file | as in `/intel` SKILL.md "Inputs"; for Teams/Stream recaps, `/debrief` §1 "Get the full transcript" if installed (full transcript, not a pane copy) |
| "my discussion with <person>", Slack permalink or thread | Slack connector: find the DM or thread, and take the on-topic messages plus every link in them |
| Email or thread | M365 or mail connector |
| URLs, files, prior briefs, pasted text | read directly |

All flags are optional. `--account` (system-of-record name, resolved when a CRM connector
exists) · `--target` (the topic, product or problem, if the context doesn't make it obvious) ·
`--goal` (the outcome the user wants, in their words) · `--competitor` · `--meeting` (the next
customer touch the brief must prep) · `--out` (default cwd) · `--send-to` (one Slack DM with the
PDF attached; send once, nothing else) · `-clean` (sanitize for external sharing). Infer anything
missing from the evidence. Ask one question only if the problem itself can't be identified.

## Run

1. **Gather** (main thread). Make the work dir `<scratchpad>/<slug>/{src,lanes,kg,build}`. Save
   every primary source to `src/`. Take an inventory of available connectors: list what exists,
   check auth with `token_status` / `whoami` where offered, and call `browser_login` / `login` on
   failure. Record each as available, failed or absent. Never assume a connector because a past
   run used it.
2. **Frame** (main thread, before any fan-out). Read all of `src/`. Copy
   `<skill>/references/brief-template.md` to `<work>/BRIEF.md` and fill it from the evidence:
   - the **problem behind the ask** (what's actually at stake, which may differ from what was
     literally asked)
   - **desired outcomes**, ranked, in the customer's terms, each tied to the line of evidence
     that shows it
   - the **stakeholders** and what each one needs to hear
   - the **claims** in the sources, written as hypotheses
   - the **questions** the brief must answer, plus the unknowns that would change the
     recommendation
   - an **inverted read**: what would make the obvious answer wrong
3. **Plan lanes** (main thread). Group the questions into 3–10 research lanes. Each lane in
   BRIEF.md §Run plan names its question(s), the evidence that prompted it, and the sources it
   will try (public docs, vendor material, available internal connectors, the primary links).
   Shape the lanes to this problem. `references/method.md` §Lane patterns lists common shapes
   to adapt or reject, not a default set. Give one lane per primary-source link only when the link
   is load-bearing. Run the self-check in method.md before fanning out.
4. **Fan out**: one message, all background, `model: sonnet`. Each lane agent reads BRIEF.md and
   writes `lanes/<id>.md` + `lanes/<id>.kg.json`. Read-only everywhere.
5. **Knowledge graph**: `python3 <skill>/scripts/build_kg.py <work>` → `kg/graph.json` +
   `kg/GRAPH.md`. Add `kg/aliases.json` for duplicate IDs and rebuild. Query:
   `build_kg.py <work> q <term>`. Read the merged graph and look for gaps: an outcome with no
   evidence, or a claim with a single source. Run at most one targeted follow-up lane per
   design-critical gap.
6. **Author** (one Opus agent, background), briefed per `references/author-brief.md`. It
   chooses the sections (spine + evidence-driven), closes the remaining gaps itself (logged in
   `triangulation_notes.md`), writes `build/content.html` + `build/citations.json`, builds and
   checks the PDF, and reads every page PNG.
7. **Adversarial QA, exactly once, final**: a fresh Opus reviewer per `references/qa-brief.md`. It
   gets the PDF text, the sources, the lane files, triangulation notes, citations and page PNGs,
   but none of the author's reasoning. Send the CONFIRMED findings to the author (SendMessage) to
   fix, fill "Appendix D · Adversarial QA" with the findings and their dispositions, then rebuild.
   **No second QA round.**
8. **Verify yourself**: `python3 <intel>/scripts/check.py <pdf>` exits 0. Open the cover and at
   least 3 page PNGs, including one diagram or table-heavy page and the QA appendix. Grep the PDF
   text for tokens, tenant URLs, record IDs and emails.
9. **Deliver**: print the path, page count, bottom line, the lanes that ran (and why), and the QA
   verdict. With `--send-to`: `node <skill>/scripts/slack_post_with_file.js <dm-id> "<Name>"
   "<pdf>" <msg.txt>` (Slack desktop with `--remote-debugging-port=9222`; `DRY_RUN=1` stages
   only), then confirm the message and its `Files:` entry with the Slack connector. No
   follow-ups. If Slack isn't reachable, say so and give the path.

Output name: `<Account> Solution Brief <YYYY-MM-DD>.pdf` (without an account, `<Topic> Solution
Brief <YYYY-MM-DD>.pdf`).

## Requirements

Same as `/intel` (Chrome, Python 3 + PyMuPDF, `pdftotext`, Node 18+), plus the `/intel` skill.
Every connector is optional: the brief reports which ones it used and which were unavailable.

## Guardrails

- No hallucination. Every claim has a URL or an internal-record tag plus a verbatim quote in the
  lane files. Anything not opened is "Unverified" or "not found", never inferred.
- Source claims are hypotheses. The brief states which were confirmed, qualified or refuted.
- The user's own assertions are labeled "per account team; not in systems of record" when the
  systems don't show them.
- Internal statements are labeled "Internal — not customer-safe".
- Never include tokens, tenant URLs, environment IDs, record IDs or emails. Vendor URLs use placeholders.
- ASCII diagrams in the PDF. Mermaid only in `.md` previews.
- Report every source that returned nothing or failed.
- `-clean`: replace account, people, hostnames and internal-only statements with placeholders,
  drop internal-tagged rows, and keep the footer text check.py requires.
