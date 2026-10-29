# /solution method

## Why this shape
A technical brief that a customer architect can verify line by line, wrapped in the
/intel debrief's account intelligence, with a fan-out + knowledge-graph research front end.
Visual patterns: `assets/skeleton.html`.

## Document structure (12–16 Letter pages)
1. Cover: kicker, headline that states the play, bottom line, 4 stat cards (sourced numbers only), 3 theme cards, 4 recommended moves
2. Executive summary: the ask, the core problem, **desired principal technical outcome(s)**, a challenges-per-signal table, a fix-before-next-meeting box (corrections to the primary source), open discovery questions
3. Introduction + glossary (vendor side | Dynatrace/open-standard side) + target-architecture ASCII diagram (every path ends in Grail)
4. Target product: architecture + telemetry surface table (signal, API, auth/role, latency/retention, limits) and what is *not* exposed
5. Competitive baseline: competitor's integration vs proposed Dynatrace coverage (parity/beyond). No bashing.
6. Solutions S1..Sn: option table (how it works · fidelity/status · verdict) + one simple ASCII flow per option; coverage matrix (signals × solutions); phased implementation plan
7. Intel sections (from /intel method): account context (SFDC/PBI), standard + inverted analysis, triangulation table (Confirmed / Corroborated / Single-source / Contradicted), next-meeting angle, POC success criteria, actions & asks
8. Summary + numbered recommendations
9. Appendices: A documentation & verification (every public URL, grouped) · B primary-source claims verdicts · C source coverage incl. failures · D adversarial QA (findings + dispositions)

## Lessons from past runs (first target: Workday)
- AI summaries in the primary source mix true and loose claims, e.g. "SDK pushes via Metrics Ingest API" (it actually goes through the local EEC). Verify each one.
- WebFetch returns summaries, so mark quotes "as returned by fetch" unless raw. Medium sites 403, and the Wayback Machine works. Vendor marketplaces sit behind logins.
- SOQL can't filter long-text fields (Description, Next Steps). Use name and subject filters and say so.
- Gong filtered search often returns 401/500; report it as a tool failure.
- Credential storage decides an extension's design. Verify what the extension framework can hold (secret fields vs. credential-vault types) before proposing OAuth refresh-token flows.
