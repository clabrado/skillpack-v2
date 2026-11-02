<!-- TEMPLATE: copy to <work>/BRIEF.md and replace every <...> from THIS run's evidence. Keep
Rules and Output contract verbatim. Delete any section line that doesn't apply; never fill one
with guesses. -->

# Shared research brief — <topic> for <account or audience>

## Problem behind the ask
<What was literally asked, and what's actually at stake. Quote the line that shows it.>

## User-supplied hints (flags: hypotheses, not facts)
<--target / --goal / --competitor / --meeting values, or "none">

## Desired outcomes (ranked, customer's terms)
1. <outcome> — evidence: <source, timestamp/line>
2. <outcome> — evidence: <...>

## Stakeholders
| Who | Role | Needs to believe | Would block it |
|---|---|---|---|

## Design-deciding constraints
<budget/metering, timeline, compliance, skills, tooling, contracts, as the evidence shows>

## Source claims (hypotheses: verify or refute, never assume)
1. <claim> — <source>
2. <claim> — <source>

## Inverted read
<What would make the obvious recommendation wrong?>

## Questions the brief must answer
- <question>; would flip the recommendation if answered: <yes/no>

## Connector inventory (this session)
<connector: available | auth failed | absent>

## Run plan
| Lane | Question(s) | Evidence that prompted it | Sources to try |
|---|---|---|---|
Self-check: <answers to the method.md self-check>

## Your lane
Your prompt names your lane ID and question(s). Research ONLY that slice.

## Rules (hard)
- **Read-only everywhere.** Never send messages, never create or update records, never post anything.
- No dtctl. Do not spawn subagents.
- **No hallucination.** Every claim needs a URL (or internal record pointer) AND a verbatim quote (≤300 chars) copied from the page or record. If you couldn't open a page, say so ("FETCH FAILED: <reason>"). Never infer its contents from the URL or from memory.
- If WebFetch is blocked or returns a login wall or JS shell, retry with a browser MCP if one is available before giving up. Record exactly what was publicly visible.
- Note doc dates, "last updated", version, and beta/preview labels when present.
- On any MCP auth failure, call that MCP's `browser_login`/`login` and retry. Never ask the user.
- Internal sources: no tokens, tenant URLs or record/entity IDs in your output. Real people's names are OK (internal doc).
- Follow ≤1 hop of clearly relevant links. List every URL you opened.
- If your lane's premise turns out wrong, say so plainly. That's a finding, not a failure.

## Output contract (write BOTH files to the path given in your prompt)
1. `<id>.md`: findings. A 5-line summary; detailed findings with `[n]` citations; a verdict on
   each source claim you touched (CONFIRMED / PARTIAL / REFUTED / NOT COVERED, with quote); which
   desired outcome each finding supports or undermines; gaps and unknowns; the URL list.
2. `<id>.kg.json`: knowledge-graph fragment, strict JSON:
```json
{
  "source": {"id": "<id>", "url": "<primary url or 'internal:<system>'>", "title": "...", "kind": "web|internal", "fetched": true, "retrieved": "<YYYY-MM-DD>"},
  "nodes": [{"id": "<type>:<snake_name>", "type": "<Type>", "label": "...", "props": {}}],
  "edges": [{"src": "<node id>", "rel": "<REL>", "dst": "<node id>", "url": "...", "evidence": "<verbatim quote>"}],
  "claims": [{"id": "<id>-c1", "text": "...", "url": "...", "quote": "<verbatim>", "confidence": "Confirmed|Single-source|Unverified|Contradicted"}],
  "urls_seen": ["..."]
}
```
Node types (use what fits; add one only if none does): Outcome, Problem, Constraint, Stakeholder,
Account, Person, Product, Capability, Limitation, Integration, API, DataType, Process, Vendor,
Competitor, Doc, Opportunity, Risk, Metric.
Relationships: ACHIEVES, BLOCKS, REQUIRES, SUPPORTS, DOES_NOT_SUPPORT, LIMITED_BY, EXPOSES,
PRODUCES, INTEGRATES_WITH, COMPETES_WITH, OWNS, NEEDS, MEASURED_BY, DOCUMENTED_AT, PART_OF,
USES, MENTIONS, CONTRADICTS.
**Canonical node IDs for this run** (main thread fills these from the framing so fragments merge;
reuse them exactly):
`<outcome:...>`, `<problem:...>`, `<constraint:...>`, `<account:...>`, `<product:...>`, `<capability:...>`
