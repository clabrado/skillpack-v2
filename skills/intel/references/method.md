# Intel debrief method

How one call (or transcript, or email thread) becomes an intel debrief PDF.
Before writing anything, read `assets/example/acme-racing-debrief-example.pdf`
(`pdftotext -layout`) and match its voice and depth. It is fictional and shows every possible section. Never
copy its facts, and don't treat its section list as required: §4 decides which sections
this call gets. Start the markup from `assets/skeleton.html` and delete the evidence-driven
pages this call doesn't warrant. Use `assets/example/example-content.html` only as a markup
reference.

## 1. Ingest the primary source

Primary source = what was actually said or written. Rank: full transcript >
email thread > AI notes. AI notes (Krisp, Gong, Copilot) are summaries — use
them for orientation, but quote and timestamp from the transcript.

- Krisp share link (`app.krisp.ai/m/...`): `scripts/krisp_fetch.js <url> <outprefix>`
  pulls AI notes + speaker-labeled transcript (public share links only).
- Gong call (if a call-recording connector is present): `get_call_details` +
  `retrieve_transcripts` (find it with `list_calls` if filtered search fails). Without a
  connector, ask for the transcript file or a paste.
- `.eml` / pasted email: read directly; capture sender, recipients, dates, asks.
- Local `.txt` / `.vtt` / `.docx` transcript: read directly.

AI notes are not evidence. On a real run, Krisp's notes inverted the key
comparison number; the transcript and emails showed the reverse. Every number in the doc must come from the transcript or
a system of record.

Extract: attendees + roles, every explicit ask, pains, numbers, dates, named
systems/vendors, commitments made by **our** side (these are risk), and
verbatim quotes with `(mm:ss)` timestamps.

## 2. Triangulate: check what the call raises, record what each source returned

First list what this call needs checked: each ask, number, claim our side made, named
system, stakeholder and commitment. Then pick the sources that can confirm or refute those,
from the connectors this session actually has. The table below lists common sources and
what they're good for. It's a menu, not a checklist: use what's available and relevant, and
add anything else the call points to (a vendor's docs, a partner portal, a prior brief).
Every source you tried is reported, including empty ones ("Gong: no calls found for
<account> in 12 months"). So is every relevant source that wasn't available. None is
silently skipped. Available connectors you chose not to query are listed in the
source-coverage line, with a one-line reason.

| Source (typical) | Tools (if present) | What to pull |
|---|---|---|
| Salesforce | `sf data query` or the Salesforce MCP (org = `$INTEL_SF_ORG`, else the `sf` default org). Read-only SOQL. | Account (Type, owner, parent, industry, ARR/P2B fields), Opportunities (stage, amount, close, Next Steps, description), Contracts/products, Contacts matching attendees, recent Tasks/Events, POC__c on the opp |
| Power BI | Power BI MCP (e.g. a consumption dataset via DAX) | Only if existing customer: DPS/consumption trend, capabilities in use, renewal date, health |
| Call recordings (e.g. Gong) | the recording MCP (Gong: `search_calls`, `get_call_details`, `retrieve_transcripts`; filtered search has returned HTTP 500 before, so fall back to `list_calls` and report it as a tool failure, not "no calls") | Prior calls with this account; what was promised before |
| M365 | M365 connector: mail, calendar, Teams chat and SharePoint search | Thread history, upcoming meetings, internal Teams chatter, account plans/decks |
| Slack | Slack connector search (public + private) | Account channels, AE/SE DMs, product/roadmap channels for the topics raised (e.g. extension or feature names) |
| Product truth | Dynatrace docs MCP, Highspot (if available), WebSearch on docs.dynatrace.com / dynatrace.com/hub | Verify every capability claim made on the call or planned for the follow-up. Flag over-promises. |
| External | WebSearch, LinkedIn MCP (if available) | Company news last 60–90 days, strategy, earnings, tech stack signals, attendee roles |

Auth: on any MCP auth failure, call that MCP's `browser_login`/`login` and
retry — never ask the user to authenticate. A connector that isn't installed is
reported as "not available". Never run `dtctl` in parallel.

## 3. Analyse

- **Standard read**: explicit business problems, desired outcomes, technical
  needs — each tied to a quote.
- **Inverted read**: what wasn't said (absent stakeholders, budget, timeline,
  competitors), pre-mortem ("how we lose this"), contradictions between
  the call and system-of-record data, over-promises from our side.
- **Known vs unknown** tech/infra stack.
- **Triangulation table**: claim → source(s) → confidence (Confirmed /
  Corroborated / Single-source / Contradicted).
- **Opportunity sizing**: only from real data (a CRM potential/propensity field, usage
  or consumption data, counts stated on the call). Unmeasured stays "unknown" — never invent a number.

## 4. Document structure

**Spine (always):** cover, executive summary, main talking points, what the customer is
asking for (desired outcomes and asks), standard + inverted analysis, triangulated
intelligence, actions & asks. **Evidence-driven (only with real content):** account
context, technology & infrastructure, next-meeting angle, POC / proof angle, or a section
this call needs that isn't listed (e.g. a constraint, a risk, a competitor). Number
sections in the order used. Adapt the names to the account. The fictional example shows
the full set, in this order:

1. Cover — kicker, headline that states the play, the bottom line, 4 stat
   cards, 3 theme cards, 4 recommended moves
2. Executive summary — 60-second read; opportunity, buyer, ask, play, main
   threat, open questions; 3 stats; "what we need from leadership"; fix-before
   box
3. Main talking points — priority table: talking point · business outcome for
   customer · potential for Dynatrace; Say / Don't say
4. 01 Account context — where we stand, timeline, history
5. 02 What the customer is asking for — each ask and how we answer
6. 03 Standard analysis — what was said
7. 04 Inverted analysis — what wasn't said, how we lose
8. 05 Technology & infrastructure — known vs unknown
9. 06 Triangulated intelligence — per-source findings + confidence table +
   external intel
10. 07 Next-meeting angle — agenda/demo narrative for the follow-up
11. 08 POC / proof angle — success criteria (if applicable)
12. 09 Actions & asks — owner, date, action; leadership asks

Typically 8–12 pages; length follows the evidence. Never pad a section to keep the
structure. Record one line per evidence-driven section in `triangulation_notes.md`
§Section choices: included (the evidence that justified it) or cut (why). Mention a cut in
the exec summary only when the absence is itself a finding (e.g. no POC angle because no
success criteria were discussed).

## 4b. Internal vs customer-safe

Internal Slack threads, blog drafts and roadmap docs are fine as *intel* but
must never appear under "what we can say" / talking points. Label them
"Internal — confirm with <principal> before saying". Customer-safe roadmap =
the customer-facing roadmap page / rally slides only.

## 5. Voice

Plain English, outcome first, short sentences. Business outcome before
capability. Every number has a source. Quotes carry timestamps. No hype, no
competitor bashing. Internal-confidential: real names allowed; never include
tokens, tenant URLs or entity IDs.

## 6. Build + render check

```
cp assets/skeleton.html <work>/content.html   # starting skeleton
# edit <work>/content.html  (uses {{WAVE}} {{P}} {{TOTAL}} {{FOOTER}})
python3 scripts/build.py <work> "<out>.pdf" --title "<Acct> Debrief" --footer "<Acct> Debrief · Dynatrace internal"
python3 scripts/check.py "<out>.pdf" --expect <pages>
```
`check.py` must exit 0 and you must look at every page PNG. Fix overflow by
cutting words, not shrinking fonts. Classes available: see
`assets/template/style.css` (`page cover`, `hdr`, `ftr`, `kicker`, `bar`,
`lede`, `grid2/3/4`, `card tint|accent|purple|green|amber`, `stat`, tables).

## 7. Adversarial QA (separate agent, fresh context)

Give a reviewer the PDF text + primary source + raw triangulation notes —
not your conclusions. It must try to break the doc:
- every number/date/name traced to a source; unsupported → flag
- every quote present in the transcript at that timestamp
- capability claims verified against docs (over-promise = defect)
- internal contradictions between pages
- recommendations actually follow from evidence
- spine sections all present; each evidence-driven section traces to §Section choices
- render: overflow, clipped text, empty cards
Fix every CONFIRMED finding, rebuild, re-check. Record the QA verdict.
