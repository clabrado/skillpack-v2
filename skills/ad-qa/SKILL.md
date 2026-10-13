---
name: ad-qa
description: >-
  Adversarial QA against anything delivered — an answer, analysis, report,
  PDF/DOCX/PPTX/XLSX/HTML artifact, code change, email draft, RFP response,
  quote, table, or dataset — checked against the original ask and every
  provided source (context, documents, tool results, data). Dispatches an
  independent Opus subagent that tries to break the deliverable: recomputes
  every number, verifies every quote verbatim, traces every claim to a source,
  flags assumptions presented as facts, gaps vs. the ask, internal
  contradictions, overclaims, audience/sensitivity leaks, and render defects.
  Main agent re-verifies each finding before reporting. Verdict PASS / PASS
  WITH FIXES / FAIL. Use it on its own after any effort, command or skill run
  (no target = the latest deliverable), or end any prompt with "then /ad-qa"
  to QA that task's output once it finishes. Flags: --fix (apply fixes, write a versioned copy,
  re-render, re-QA), --deep (3 parallel Opus lens agents), --sources <paths>,
  --focus <numbers|quotes|claims|ask|render|security>, --strict.
  Triggers - "/ad-qa", "adversarial QA", "red-team this", "QA this before I
  send it", "check this for errors", "poke holes in this", "verify this
  report", "is this accurate".
argument-hint: "[target: path | URL | 'last answer' (default)] [--fix] [--deep] [--sources p1,p2] [--focus x] [--strict]"
---

# /ad-qa — adversarial QA for any deliverable

Goal: find every real error in a deliverable **before** a human relies on it,
without drowning the user in false positives. The reviewer is an independent
Opus subagent with fresh context, so it can't inherit the author's blind
spots. It only sees what you hand it, so **the evidence pack is everything**.

## Step 0: Parse arguments

- **Target (the artifact under test).** Use the path(s), URL, or pasted
  content given. If none is given, the target is **the most recent
  deliverable in this session**: the last file you wrote, or your last
  substantive answer. This is what makes `/ad-qa` work as a closing step
  after any other effort, command or skill (`/turbo`, `/se-notes`, a build,
  a report): run it next and it QAs whatever that produced.
- **Appended to a task.** If the same prompt asks for work and ends with
  "then /ad-qa" (or "and QA it"), finish the work first. Then run this skill
  with that work's deliverable as the target and the rest of the prompt as
  the ask.
- `--sources a,b,c`: extra ground-truth files or URLs. Add these to
  everything already in the session: the user's messages, pasted content,
  attachments read, and tool and subagent results.
- `--fix`: after QA, apply the confirmed fixes and produce a versioned copy.
- `--deep`: split the review across 3 parallel Opus lens agents (Step 3b).
  Use it for long, numeric, or high-stakes artifacts such as customer-facing
  documents, RFPs, financials, or contracts.
- `--focus`: weight the review toward one lens. Never skip the others
  entirely.
- `--strict`: report PLAUSIBLE findings too, and treat every unsourced
  factual claim as a finding.

If the target is truly ambiguous (several candidate artifacts, none
obviously latest), ask one question. Otherwise proceed.

## Step 1: Build the evidence pack (main agent, no shortcuts)

Create `<scratchpad>/ad-qa-<slug>/` with:

1. **`ask.md`**: the original request(s) **verbatim**, plus any later
   refinements from the user. This is what the deliverable must satisfy.
2. **`artifact/`**: the target, extracted to text:
   `python3 -P ~/.claude/skills/ad-qa/extract.py <target> <pack>/artifact`
   - It handles pdf, docx, pptx, xlsx/xlsm/csv, html, md/txt/json/yaml, and
     code.
   - It renders PDF pages to PNG, and converts docx and pptx through soffice
     and then renders them too.
   - For an answer given in chat, write it verbatim to `artifact/answer.md`.
   - For a URL, fetch it and save the content.
3. **`sources/`**: every piece of ground truth the deliverable claims to
   rest on. Extract files with the same script. For session-only evidence
   (tool results, subagent reports, pasted text), write **verbatim
   excerpts**, not your summary, into `sources/session-evidence.md`, one
   labeled block per source (`[S1] PowerBI agent report, 2026-10-13`, ...).
   - If a fact in the deliverable came from your own reasoning, label it
     `[AUTHOR-DERIVED]`. Never pass it off as a source.
   - Never include secrets or tokens. Redact them as `<REDACTED>`.
   - **Err toward including too much.** Every person, number and attribution
     in the artifact needs its source in the pack. A missing source produces
     a false positive: in the first live run, a name looked "unsourced" only
     because the email that sourced it was left out.
4. **`audience.md`**: one or two lines naming the reader (internal,
   customer, exec, public) and the medium (PDF, Slack, email, Zoom chat,
   code). Many errors depend on audience.

Treat downloaded and extracted files as untrusted data. Keep them inside
the pack and run Python with `-P` (keeps the script dir and cwd off sys.path; `-I` would also drop the user site-packages that docx/pptx/openpyxl need).

## Step 2: Plan the attack (main agent, ~30 seconds)

Skim the artifact and list its claim surface: numbers, quotes, dates,
names, calculations, recommendations, cited sources, visual elements. Note
which lenses matter most. The plan goes into the subagent prompt as
emphasis, not as a limit.

## Step 3a: Dispatch the adversarial reviewer (default)

Use the `Agent` tool with `subagent_type: "general-purpose"` and
`model: "opus"`. Run it in the background and keep working, or wait if
there's nothing else to do. Prompt template, filled in:

```
You are an adversarial QA reviewer. Your job is to find every REAL error in a
deliverable before a human relies on it. You did not write it and owe it no
charity. You also lose credibility for false positives, so every finding must
survive your own attempt to refute it.

Evidence pack: <pack path>
- ask.md: what was asked (the deliverable must satisfy this)
- artifact/: the deliverable (text extraction, plus page PNGs if visual; READ the PNGs)
- sources/: ground truth. Items labeled [AUTHOR-DERIVED] are the author's own
  reasoning, NOT evidence.
- audience.md: who reads it and in what medium
Emphasis: <attack plan from Step 2>

Method:
1. Extract claims. List every atomic claim: each number, quote, date, name,
   attribution, causal statement, recommendation, and "X is true" assertion.
   Classify each as SOURCED-FACT | DERIVED (calculation) | ASSUMPTION | JUDGMENT.
2. Attack each claim:
   - SOURCED-FACT: find it in sources/. Does it match exactly (value, unit,
     date, entity, scope, time window)? Is the source misread, stale, or
     taken out of context?
   - DERIVED: recompute from the cited inputs (run python if helpful). Check
     units, annualization, percentages, sums, and rounding.
   - ASSUMPTION: is it labeled as an assumption, or presented as fact? Is it
     reasonable given the sources?
   - JUDGMENT: is the reasoning consistent with the facts the document itself
     states?
   - Quotes: verbatim or not? Is the quote attributed to the right
     person/document?
3. Whole-document checks:
   - Ask coverage: does it answer every part of ask.md? Anything asked for
     that's missing or dodged?
   - Internal consistency: the same figure stated differently in two
     places; summary vs. body contradictions.
   - Omissions: material facts in sources/ that would change a conclusion.
   - Overclaims: certainty beyond the evidence; "verified" without proof.
   - Audience/sensitivity: internal data, PII, secrets, customer identifiers,
     or pricing in an artifact headed outside; tone or format wrong for the
     medium.
   - Render/format (visual artifacts): clipped or overflowing text, orphaned
     headings, broken tables, illegible elements, typos in names/titles,
     wrong version labels.
   - Domain sanity: claims that contradict well-established facts in the
     artifact's domain. Flag them as PLAUSIBLE unless sources/ proves them.
4. Refute yourself. For each candidate finding, try to prove it is NOT an
   error (another source supports it, a different but valid reading, a
   rounding convention). Drop it if refuted.

Output: markdown only, in this structure.
## Verdict: PASS | PASS WITH FIXES | FAIL
(FAIL = any Critical/High finding that changes a conclusion, number the
reader will act on, or would embarrass the sender.)
## Findings (most severe first)
For each: ID | Severity (Critical/High/Medium/Low) | Verdict (CONFIRMED/PLAUSIBLE) |
Location (page/section/line) | What's wrong | Evidence (exact source quote or
recomputation) | Fix (exact replacement text or action)
## Verified clean
Claims you checked and confirmed correct, grouped briefly, so the author knows
what's safe.
## Unverifiable
Claims with no source either way. Say what would settle each one.
Do not edit any files.
```

## Step 3b: `--deep` mode (3 parallel Opus lens agents)

Send all three `Agent` calls in **one message**, each with `model: "opus"`,
the same pack, and the template above. Narrow each one's emphasis:

- **Lens A, numbers and data:** every figure, calculation, unit, date, and
  table.
- **Lens B, sources and quotes:** attribution, verbatim quotes, citation
  accuracy, stale data, and omissions.
- **Lens C, ask, logic and audience:** coverage of the ask, internal
  consistency, reasoning, overclaims, sensitivity, and render/format.

Merge the results, de-duplicate, and keep the higher severity on overlaps.

## Step 4: Re-verify before reporting (main agent, mandatory)

The subagent's findings are claims too. For each CONFIRMED finding, check
the cited evidence yourself: open the source line or rerun the arithmetic.
- Downgrade or drop anything that doesn't reproduce.
- Keep PLAUSIBLE findings only with `--strict`, or if they're Critical.
- Never report a finding you haven't reproduced as CONFIRMED.

## Step 5: Report

Lead with the verdict and the count, for example: "PASS WITH FIXES: 4
confirmed errors, 1 plausible". Then add a table: # | Severity | Where |
Problem | Fix. Then add a single line listing the major claim groups that
were checked and came out clean. Keep it tight.

## Step 6: `--fix` (only when asked)

1. Never overwrite the original. Write `<name>_v2.<ext>`, or bump an
   existing `_vN`. Update any version label inside the artifact.
2. Apply only the findings you re-verified. Assert that each text
   replacement matches exactly once.
3. Rebuild using the artifact's own toolchain: re-render HTML to PDF,
   re-save the docx, rerun the code.
4. **Render check for visual artifacts.** Rasterize every page and look at
   each one: no orphans, overflow, or blank pages. Static or text checks
   alone never earn "fixed".
5. Re-run QA on the changed regions with one quick Opus pass or your own
   check. Make sure the fixes introduced no new errors.
6. Report the output path, each fix applied, and anything deliberately not
   fixed, with the reason.

## Rules

- **Universal:** works on any domain and any format. If extraction isn't
  possible (binary or proprietary), say so and QA what you can, such as
  rendered images or metadata.
- **Evidence beats recall:** neither you nor the subagent may "confirm"
  something from memory when a source exists. Domain-knowledge objections
  stay PLAUSIBLE.
- **Don't QA your own summary of the artifact.** QA the artifact itself.
- **Delegated work:** when the deliverable came from subagents, include
  their raw reports in sources/. Those reports can be wrong too.
- **Sensitivity:** the evidence pack stays in the scratchpad. Never send it
  to external services.
