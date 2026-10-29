---
name: solution
description: >-
  Agentic technical solution brief. Starting from a primary source (a Slack DM/thread with
  someone, a URL list, an email, or pasted notes), fan out one Sonnet agent per link plus
  domain agents (vendor developer docs, MCP/AI, log/telemetry export paths, UX, Dynatrace
  product truth, public account intel) and internal agents (Salesforce + Power BI, M365 +
  broad Slack + Gong). Every agent writes a cited findings file and a knowledge-graph
  fragment; fragments merge into one graph. An Opus author then writes a Dynatrace-branded
  PDF in the /intel visual format: cover with bottom line, executive summary, desired
  principal technical outcome, introduction + glossary, product architecture and telemetry
  surface, competitive baseline, solution options with ASCII flow diagrams, intel sections
  (account context, standard/inverted analysis, triangulation, next-meeting angle, POC,
  actions), summary + recommendations, and an appendix of every public doc so the customer
  can verify. Exactly ONE final adversarial QA pass, then fixes and a render check.
argument-hint: "<slack-dm-with-<person> | slack-permalink | url... | file | \"paste\"> --account <name> --target <product/tech> [--competitor <name>] [--goal \"...\"] [--meeting <date>] [--out <dir>] [--send-to <slack-user>] [-clean]"
when_to_use: >-
  When the user wants a cited, customer-verifiable solution design for observing a third-party
  product/platform with Dynatrace (custom extension, OTel/log export, API polling,
  synthetic/UX), usually to displace a competitor at an account: "/solution", "build the
  solution brief", "how do we observe <SaaS> with Dynatrace for <account>".
---

# /solution — agentic technical solution brief

Method detail: `references/method.md` (read it every run). Page skeleton (markup, ASCII
diagram and appendix patterns): `assets/skeleton.html`. If `private/` exists in this skill
folder, it holds the user's own finished briefs; read the newest one as the quality bar
(internal only, never copy another account's content).

**Requires the `/intel` skill installed next to this one.** The build pipeline, page
template and render checker are shared. Below, `<intel>` = the sibling `intel/` folder
(normally `~/.claude/skills/intel`) and `<skill>` = this folder.

## Inputs

| Input | How to ingest |
|---|---|
| "my discussion with <person>" | Slack connector: find the user, read the DM. Take the message(s) on the topic plus every link in them. |
| Slack permalink / thread | Slack connector: read the thread |
| URLs / file / pasted text | read directly |

Flags: `--account` (SFDC account name; resolve with SOQL `Name LIKE`), `--target` (the product to
observe, e.g. Workday), `--competitor` (e.g. Datadog), `--goal`, `--meeting` (next customer
touch the brief must prep), `--out` (default cwd), `--send-to` (one Slack DM + attached PDF,
signed as the user asks; send once, nothing else), `-clean` (sanitize for external sharing).

## Run

1. **Gather** (main thread). Make a work dir `<scratchpad>/<slug>/{src,links,web,internal,kg,build}`.
   Save the primary source to `src/`. Check auth up front: `sf org list` (org = `$INTEL_SF_ORG`,
   else the `sf` default org), Power BI and Gong `token_status`; on failure call the MCP's
   `browser_login`/`login`. A connector that isn't installed is reported as "not available".
   Resolve the account in SFDC. Copy `<skill>/references/brief-template.md` to `<work>/BRIEF.md`
   and fill in the mission, primary-source claims (as hypotheses) and canonical KG node IDs.
2. **Fan out, one message, all background, `model: sonnet`**, each told to read BRIEF.md and write
   `<id>.md` + `<id>.kg.json`:
   - `L1..Ln`: **one agent per link** in the primary source.
   - `W1` vendor developer docs / API surface + auth + throttling · `W2` vendor MCP / AI agents ·
     `W3` log/audit/telemetry egress + how other tools (SIEMs, competitors) ingest it + OTel receivers ·
     `W4` end-user experience (synthetic/RUM feasibility, vendor status/maintenance) ·
     `W5` public account intel (vendor + competitor footprint, leaders, news) ·
     `D1` Dynatrace product truth for every ingest path (Extensions 2.0, logs/OTLP/bizevents APIs,
     Collector receivers, Workflows, credential vault, Synthetic, Hub/community precedent).
   - `I1` Salesforce + Power BI · `I2` M365 + broad Slack (all channels) + Gong. Read-only.
3. **Knowledge graph**: `python3 <skill>/scripts/build_kg.py <work>` → `kg/graph.json` + `kg/GRAPH.md`.
   Add `kg/aliases.json` for duplicate IDs and rebuild. Query: `build_kg.py <work> q <term>`.
4. **Author** (one Opus agent, background): brief per `references/author-brief.md`. It closes the
   design-critical gaps itself (logged in `triangulation_notes.md`), writes `build/content.html`
   and `build/citations.json`, builds and checks the PDF, and reads every page PNG.
5. **Adversarial QA — exactly once, final**: a fresh Opus reviewer gets the PDF text
   (`pdftotext -layout`), the primary source, every research `.md`, `triangulation_notes.md`,
   `citations.json` and the page PNGs, but none of the author's reasoning. It re-fetches cited URLs to
   check claims, and returns CONFIRMED / PLAUSIBLE findings with evidence (brief: `references/qa-brief.md`). Send the CONFIRMED findings to the
   author (SendMessage) to fix, fill "Appendix · Adversarial QA" with the findings and their
   dispositions, then rebuild. **No second QA round.**
6. **Verify yourself**: `python3 <intel>/scripts/check.py <pdf>` exits 0; open the
   cover and at least 3 page PNGs (including a diagram page and the QA appendix); grep the PDF text for
   tokens, tenant URLs and SFDC IDs.
7. **Deliver**: print the path, page count, bottom line and QA verdict. If `--send-to` is given, send one
   single message carrying both the text and the PDF:
   `node <skill>/scripts/slack_post_with_file.js <dm-id> "<Name>" "<pdf>" <msg.txt>` (Slack desktop
   started with `--remote-debugging-port=9222`; it aborts without sending unless the text and the file
   are both staged; `DRY_RUN=1` stages only). Check with the Slack connector that the message and a
   `Files:` entry appear. Send no follow-ups. If the Slack app isn't reachable, say so and give the path.

## Requirements

Same as `/intel` (Chrome, Python 3 + PyMuPDF, `pdftotext`, Node 18+), plus the `/intel` skill itself.

## Guardrails

- No hallucination: every claim has a URL or internal-record tag plus a verbatim quote in the
  research files. Anything not opened is "Unverified" or "not found", never inferred.
- The primary-source claims are hypotheses. The brief must state which were confirmed, qualified or refuted.
- The user's own assertions (e.g. "competitor X is in the account") are labeled "per account
  team; not in SFDC" when systems of record don't show them.
- Internal Slack/product statements are labeled "Internal — not customer-safe".
- Never include tokens, tenant URLs, environment IDs or SFDC record IDs. Vendor URLs use placeholders.
- ASCII diagrams in the PDF; Mermaid only in `.md` previews.
- Report every source that returned nothing or failed.
