# Adversarial QA brief (single, final pass), template

Spawn ONE fresh Opus agent. Do not share the author's reasoning. Give it:
- the brief text (`pdftotext -layout`), the PDF path, page PNGs (`<work>/build/png/pNN.png`; check.py `--png-dir`)
- `build/citations.json`, `BRIEF.md` (primary-source claims), every research `.md`, `triangulation_notes.md`, `kg/GRAPH.md`
- context the user asserted that systems of record don't show (the brief must label it)

It must try to falsify:
1. Every number, date, name, field, endpoint, version and limit traces to evidence. Re-fetch the 15+ highest-stakes technical claims live.
2. Citation integrity: does [n] actually say that?
3. Over-promise: any capability that isn't evidenced and isn't labeled Unverified
4. Internal vs customer-safe labeling; no tokens, tenant URLs, environment IDs, SFDC IDs or emails
5. Contradictions between pages
6. Technical soundness of each design (auth, scopes, pagination, polling vs retention, throttling, component placement, and module co-location rules such as Synthetic ActiveGate exclusivity)
7. Required structure present; glossary correct
8. Render: view every page PNG

Output `qa/QA_FINDINGS.md`. For each finding give the ID, severity, CONFIRMED or PLAUSIBLE verdict, page, quote, evidence and exact fix. Add a summary and the claims that passed.
The author fixes CONFIRMED findings, and fixes or labels PLAUSIBLE ones. Appendix D records every finding and its disposition. No second round.

## Defects caught on past runs (watch for them again)
- A Synthetic private location placed on the same ActiveGate as an extension. Not allowed: the Synthetic module must run alone.
- An API-client scope list copied from one competitor's doc ("System" only). Real requirements differ per endpoint (System, Integration, Tenant Non-Configurable, System Health Dashboard).
- POC latency criteria that contradict the proposed polling cadence
- Polling on "last poll" timestamps misses long-running jobs. Re-read an overlap window and dedupe.
- Throttle semantics differ per API family (REST/RaaS return 429; SOAP returns 500).
