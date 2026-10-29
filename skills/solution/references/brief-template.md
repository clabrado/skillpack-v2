<!-- TEMPLATE: copy to <work>/BRIEF.md and replace every <...>. Keep Rules and Output contract
verbatim. Adjust the canonical node IDs to the target product. -->

# Shared research brief — <Target> observability for Dynatrace (<Account>)

## Mission
Dynatrace wants to observe **<Target>** (<one-line description of the product>) for **<Account>**
(<industry>; SFDC type <Customer|Prospect>, AE <name>) and displace **<Competitor>**, which today
<how the competitor covers it>. The end product is a cited technical solution brief proposing
<candidate paths, e.g. (a) a credentialed Dynatrace Extension that polls <Target> APIs, (b) an
OTel / log-export path>. Your job is ONE narrow slice of research.

Primary source that started this (<channel/DM> from <person, role>, <date time TZ>) claims:
1. <claim>
2. <claim>
3. <claim>
Treat every one of these as a **hypothesis to verify or refute**, not as fact.

## Rules (hard)
- **Read-only everywhere.** Never send Slack/email/Teams messages, never create/update records, never post anything.
- No dtctl. Do not spawn subagents.
- **No hallucination.** Every claim needs a URL (or internal record pointer) AND a verbatim quote (≤300 chars) copied from the page/record. If you could not open a page, say so ("FETCH FAILED: <reason>") — never infer its contents from the URL or memory.
- If WebFetch is blocked / returns a login wall or JS shell, retry with Playwright MCP (`mcp__playwright__browser_navigate` + `browser_snapshot`) before giving up. Vendor developer portals may require login; record exactly what was publicly visible.
- Note doc dates / "last updated" / version / beta-preview labels when present.
- On any MCP auth failure call that MCP's `browser_login`/`login` and retry. Never ask the user.
- Internal sources: no tokens, tenant URLs, or entity IDs in your output. Real people names are OK (internal doc).
- Follow ≤1 hop of links that are clearly relevant (e.g. the API reference page a guide links to). List every URL you opened.

## Output contract (write BOTH files to the path given in your prompt)
1. `<id>.md` — findings: summary (5 lines), detailed findings with `[n]` citations, a verdict on each of the primary-source
   claims you touched (CONFIRMED / PARTIAL / REFUTED / NOT COVERED with quote), gaps/unknowns, and the URL list.
2. `<id>.kg.json` — knowledge-graph fragment, strict JSON:
```json
{
  "source": {"id": "<id>", "url": "<primary url or 'internal:<system>'>", "title": "...", "kind": "web|internal", "fetched": true, "retrieved": "<YYYY-MM-DD>"},
  "nodes": [{"id": "<type>:<snake_name>", "type": "<Type>", "label": "...", "props": {}}],
  "edges": [{"src": "<node id>", "rel": "<REL>", "dst": "<node id>", "url": "...", "evidence": "<verbatim quote>"}],
  "claims": [{"id": "<id>-c1", "text": "...", "url": "...", "quote": "<verbatim>", "confidence": "Confirmed|Single-source|Unverified|Contradicted"}],
  "urls_seen": ["..."]
}
```
Node types: Product, API, Endpoint, DataType, Field, AuthMethod, Role, Scope, Vendor, Integration, Protocol,
Capability, Limitation, Account, Person, Doc, Opportunity.
Relationships (use these): EXPOSES, PRODUCES, REQUIRES, AUTHENTICATES_WITH, INTEGRATES_WITH, BUILT_BY, COMPETES_WITH,
DOCUMENTED_AT, SUPPORTS, DOES_NOT_SUPPORT, LIMITED_BY, INGESTS, EXPORTS_TO, PART_OF, USES, OWNS, MENTIONS.
**Canonical node IDs** (reuse exactly when the thing appears, so fragments merge). Fill in for the target, e.g.:
`product:<target>`, `product:dynatrace`, `product:<competitor>`, `api:<target>_<api_name>`,
`datatype:<target>_<event_type>`, `authmethod:<method>`, `role:<vendor_role>`, `scope:<vendor_scope>`,
`capability:dt_extensions_2`, `capability:dt_python_extension`, `capability:dt_metrics_ingest_api`,
`capability:dt_log_ingest_api`, `capability:dt_otlp_ingest`, `capability:dt_otel_collector`, `capability:dt_openpipeline`,
`capability:dt_synthetic_browser`, `capability:dt_rum`, `capability:dt_workflows`, `protocol:otlp`, `account:<account>`.
