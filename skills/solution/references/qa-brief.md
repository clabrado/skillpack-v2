# Adversarial QA brief (single, final pass), template

Spawn ONE fresh Opus agent. Don't share the author's reasoning. Give it:
- the brief text (`pdftotext -layout`), the PDF path, page PNGs (`<work>/build/png/pNN.png`; check.py `--png-dir`)
- `build/citations.json`, `BRIEF.md` (framing, source claims, run plan), every lane `.md`,
  `triangulation_notes.md`, `kg/GRAPH.md`, and the primary sources in `src/`
- context the user asserted that the systems of record don't show (the brief must label it)

It must try to falsify:
1. Every number, date, name, field, version and limit traces to evidence. Re-fetch the 15+ highest-stakes claims live.
2. Citation integrity: does [n] actually say that?
3. Over-promise: a capability that isn't evidenced and isn't labeled Unverified, or a talking point stronger than its proof
4. Outcome fidelity: are the desired outcomes the customer's (as the sources show), or ones we projected onto them?
5. Evidence-driven structure: does every non-spine section rest on evidence? Is the run plan
   traceable to the sources, or was it boilerplate? Is anything the evidence demanded missing?
6. Internal vs. customer-safe labeling; no tokens, tenant URLs, environment IDs, record IDs or emails
7. Contradictions between pages
8. Technical and commercial soundness of each option against the design-deciding constraints
9. Render: view every page PNG

Output `qa/QA_FINDINGS.md`. For each finding give the ID, severity, CONFIRMED or PLAUSIBLE verdict,
page, quote, evidence and exact fix. Add a summary and the claims that passed.
The author fixes CONFIRMED findings, and fixes or labels PLAUSIBLE ones. The QA appendix records
every finding and its disposition. No second round.

## Defect classes caught on past runs (look for the class in whatever domain this is)
- **Placement or co-location rules**: two components proposed on one host, or in one role, that the platform forbids.
- **Permissions copied from the wrong source**: a scope or role list taken from a third party's
  doc. The real requirements differ per endpoint or feature.
- **Success criteria that contradict the design**: e.g. a latency target that's tighter than the
  proposed collection cadence.
- **Incremental-read gaps**: "since last run" cursors miss long-running items. Re-read an overlap window and dedupe.
- **Uniform error or limit semantics assumed**: different API families signal throttling or failure differently.
- **Cost or metering ignored**: a design that's technically right but trips the customer's stated budget constraint.
