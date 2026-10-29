---
name: intel
description: >-
  Agentic call-intelligence debrief. Point it at one or more customer calls,
  transcripts or email threads (Krisp share links, Gong calls, .eml, .txt/.vtt/.docx,
  pasted text, or a Slack message that contains them). For each source it runs one
  Opus agent that reads the primary source, triangulates across Salesforce, Power BI
  (if existing customer), Gong, M365, Slack, Dynatrace product docs and the public web,
  then produces a Dynatrace-branded 8–12 page PDF: bottom line, executive summary,
  main talking points, standard + inverted analysis, tech stack known/unknown,
  triangulated intelligence with confidence, next-meeting angle, POC angle, actions
  and asks. Every PDF gets an independent adversarial QA pass before it is called done.
argument-hint: "<krisp-url | gong-call | file.eml | transcript.txt | slack-permalink | \"paste\"> [more sources...] [--send-to <slack-user>] [--out <dir>] [-clean]"
when_to_use: >-
  After a customer call or email exchange when the user wants a triangulated
  intelligence debrief: "intel on this call", "debrief these Krisp calls",
  "write up the call with Jane", "/intel <link>".
---

# /intel — triangulated call intelligence debrief

Method, sources, structure and voice: `references/method.md` (read it every run).
Quality bar: `assets/example/acme-racing-debrief-example.pdf` (12 pages, source
`assets/example/example-content.html`): a **fictional** account (all companies, people, dates and figures
are invented) written to the standard of a shipped debrief. Match its depth, voice and layout; never copy
its facts. Blank page skeleton: `assets/skeleton.html`. If `private/` exists in this skill
folder, it holds the user's own real debriefs (internal only, never quoted elsewhere).

Paths below are relative to this skill's folder (`<skill>` = the directory holding this file).

## Inputs

Each positional argument is one **source** = one debrief:

| Source | How to ingest |
|---|---|
| `https://app.krisp.ai/m/...` | `node <skill>/scripts/krisp_fetch.js <url> <work>/call` → `call_notes.txt`, `call_transcript.txt` |
| Gong call URL / id | Gong MCP `get_call_details` + `retrieve_transcripts` |
| `.eml` / `.msg` / email thread | read file; or the M365 connector's mail search |
| `.txt` / `.vtt` / `.docx` / `.pdf` transcript | read file |
| Slack permalink or "my DM with X" | Slack connector: read the DM/thread; extract every Krisp/Gong link + pasted notes; group them by meeting |
| pasted text | treat as transcript/notes |

If the user names a person ("my discussion with Jane"), find the DM, list every
call/transcript/notes in it, and treat each distinct meeting as one source. When
several sources describe the **same** meeting (link + pasted notes), merge them.

Flags: `--out <dir>` (default: cwd), `--send-to <slack user>` (DM one 2-sentence
summary per PDF, then attach it), `-clean` (sanitize customer names, hostnames and
people for an artifact that will leave the company).

## Run

1. **Gather** (main thread): resolve every source to local text files under
   a per-source work dir in the scratchpad. Check auth up front so agents don't stall:
   Gong and Power BI `token_status`, and `sf org list` (org = `$INTEL_SF_ORG`, else the
   `sf` default org). On failure call that MCP's `browser_login`/`login` yourself.
   A connector that isn't installed is reported as "not available", not as "no data".
2. **Analyse**: one Opus agent per source (`model: opus`, background, all in one
   message). Brief each agent with: the source file paths, everything you already
   know (Slack context, attendees, dates), `references/method.md`, `assets/skeleton.html`,
   its work dir, the output PDF path `<out>/<Account> Intel Debrief <YYYY-MM-DD>.pdf`,
   and an instruction to write `triangulation_notes.md` (raw per-source results) next
   to `content.html`. Rules for the agent: read-only everywhere, no messages sent,
   no subagents.
3. **Adversarial QA**: when an agent returns, spawn a **fresh** reviewer
   (Opus, no access to the author's conclusions beyond the PDF) with: PDF text
   (`pdftotext -layout`), the primary source, `triangulation_notes.md`, and
   `references/method.md §7`. The reviewer returns findings as CONFIRMED / PLAUSIBLE
   with evidence. Send CONFIRMED findings back to the author agent (SendMessage) to fix,
   rebuild and re-run `scripts/check.py`. Repeat until there are no CONFIRMED defects.
4. **Verify yourself**: `python3 <skill>/scripts/check.py <pdf> --expect N` exits 0, and
   you open the cover + 2 other page PNGs. A static check alone doesn't count as "done".
5. **Deliver**: print the path, page count, bottom line and QA verdict per PDF. If
   `--send-to` was given, DM the recipient once per PDF: two plain sentences on what the
   doc is and the one thing they'll find most useful, signed the way the user asks. Then
   attach each PDF: `node <skill>/scripts/slack_attach.js <dm-or-channel-id> "<Recipient Name>" "<pdf>"`
   (drives the Slack desktop app over its debug port, see Requirements). Verify with the
   Slack connector that a `Files:` entry appears for each PDF. If the Slack app isn't
   reachable, say so and give the user the path; don't claim it was sent.

## Build pipeline

- `scripts/build.py <work> <out.pdf> --title .. --footer ..`: copies
  `assets/template/` (style.css, logo, any brand fonts) into the work dir, fills
  `{{WAVE}} {{P}} {{TOTAL}} {{FOOTER}}` and prints Letter-size pages via headless Chrome.
- `scripts/check.py <pdf> [--expect N]`: catches footer-zone overflow and page
  spill, and writes a PNG per page.
- `scripts/krisp_fetch.js`: Krisp public share → AI notes + speaker-labelled transcript.
- Shared with `/solution`, which calls these same scripts.

## Requirements

- Google Chrome (macOS path by default; set `CHROME=/path/to/chrome` elsewhere), Python 3
  with PyMuPDF (`pip install pymupdf`), `pdftotext` (poppler), Node 18+.
- `krisp_fetch.js` and the Slack scripts install Playwright into `~/.cache/intel` on first use.
- Fonts: the template uses DT Flow if the `.otf` files are present in `assets/template/`
  or `$INTEL_FONT_DIR`; otherwise it falls back to Arial. DT Flow is licensed brand
  material and is not shipped in this repo.
- Connectors used when present: Gong, Power BI, Salesforce (`sf` CLI), M365, Slack,
  Dynatrace docs, Highspot, LinkedIn. Missing ones are reported, never faked.
- `--send-to` attaches files through the Slack desktop app started with
  `--remote-debugging-port=9222`. Without it, delivery is text-only via the Slack connector.

## Guardrails

- Internal-confidential by default: real names are fine. Never include tokens, tenant
  URLs, entity IDs or customer credentials.
- No capability claim without verification against docs, Hub or product Slack. Flag
  over-promises made on the call as "fix before next meeting".
- Unmeasured numbers stay "unknown". Never invent ACV, host counts or dates.
- Report every source that returned nothing. Never skip one silently.
