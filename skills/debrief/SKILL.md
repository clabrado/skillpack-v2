---
name: debrief
description: >-
  Post-call debrief and plan of action. Point it at one customer call (Teams/Stream recap
  link, Gong call, Krisp link, .txt/.vtt transcript, or pasted text). Pulls the full
  transcript, verifies every capability claim our side made on the call against public docs,
  and plans the rest of its research from what the call raised, using whichever connectors
  are available this session (CRM, usage analytics, chat, mail, docs, web; none required).
  It then writes a Dynatrace-branded PDF in the /intel visual format. Fixed spine: cover +
  bottom line, executive summary, call analysis (standard + inverted/abstract read), desired
  outcomes, what we can deliver, claims check with "say instead" lines, recommended next
  steps, talking points (Say / Don't say) and actions, sources. Other sections (background, win
  opportunities, and so on) appear only when the call gives them content. One adversarial QA
  pass, then fixes and a render check.
argument-hint: "<teams-recap-url | gong-call | krisp-url | transcript file | \"paste\"> [--account <name>] [--prior <brief.pdf>] [--out <dir>] [-clean]"
when_to_use: >-
  Strictly AFTER a customer call, when the user wants the debrief document and next-step
  plan: "/debrief", "debrief the call", "write up the call and next steps", "post-call
  analysis". For pre-call solution design use /solution; for multi-source intel use /intel.
---

# /debrief — post-call debrief + plan of action

**Requires `/intel` installed next to this skill**: build pipeline (`<intel>/scripts/build.py`,
`check.py`), page template and `references/method.md` (read it every run: voice, triangulation,
QA rules). Page skeleton: `assets/skeleton.html` (structure of a shipped debrief; replace every
word).
If `private/` exists here it holds your own finished debriefs: read the newest as the quality bar (never copy its facts).

## 1. Get the full transcript (main thread)
- **Teams / Stream recap link** (`teams.microsoft.com/l/meetingrecap?...driveId=..&driveItemId=..`):
  do NOT copy from the Teams pane (it virtualizes; copies drop the middle). Open the `fileUrl`
  in the Playwright MCP (SSO session), then `browser_evaluate` a fetch of
  `/personal/<owner>/_api/v2.1/drives/<driveId>/items/<driveItemId>/media/transcripts`, take
  `value[0].temporaryDownloadUrl`, fetch `&format=json`, and render `entries[]`
  (`speakerDisplayName`, `startOffset`, `text`) to text. Works even when the video is
  download-blocked. If Playwright is locked by another profile, find and kill that Chrome
  (`ps … | grep <profile>`) after checking what it is.
- Gong / Krisp / files: as in `/intel` SKILL.md "Inputs".
- Verify completeness: first and last lines match the call; no timestamp gap > ~5 min that
  isn't one speaker's monologue.

## 2. Plan from the call, then gather in parallel (background agents, `model: sonnet`, one message)
Work dir: `<scratchpad>/<slug>/{src,research,build}`. Reuse any prior brief/research for the
account (`--prior`, or search home + scratchpads for the account name) instead of redoing it.

First read the transcript and list what it raises: our capability claims, customer factual
claims, asks, constraints (budget, metering, freezes, compliance), named systems and vendors,
stakeholders who were mentioned but absent, and commitments. Take an inventory of the
connectors this session actually has (tool list / ToolSearch; check `token_status` /
`whoami`, and on failure call `browser_login`/`login`). Never assume one because a past run
used it. Then dispatch:
- **V1 claims check (always)**: every capability statement our side made (speaker +
  timestamp) plus key customer factual claims. Verify each against public docs with URL +
  verbatim quote; verdict CONFIRMED / PARTIAL / REFUTED / UNVERIFIED; flag over-promises.
- **Context lanes (chosen per call)**: one agent per cluster of open questions the call
  raised, each pointed at the available sources that can answer it. Examples: account
  history and commitments from whatever CRM, usage, mail or chat connectors exist; a named
  third-party system's capabilities and limits; a constraint the customer raised; a
  reference or precedent they asked for. Write one line per lane in
  `research/PLAN.md` naming the call moment that prompted it (mm:ss, or a verbatim line when the source has no timestamps). A lane with no call
  moment behind it doesn't run.
Rules for agents: read-only, no messages, cite everything, report empty sources. Skip
connectors known to be broken and report them as unavailable.
Every connector that was tried, unavailable or deliberately not queried goes in the sources
appendix, with a one-line reason.

## 3. Write `build/content.html` (main thread, from the skeleton)
The fixed **spine** is cover, executive summary, call analysis (01 + 02), desired outcomes,
what we can deliver, claims check, next steps, actions & talking points (Say / Don't say), and the appendix. The rest
is **evidence-driven**: introduction & background, and win opportunities. Include those
only when the call gives them real content, and add a section the call needs that isn't
listed (e.g. a constraint, a risk, a reference ask). Log every include/cut in
`research/PLAN.md` §Section choices. Mention a cut in the executive summary only when the
absence is itself a finding. Number sections in the order used and adapt titles to
the account. The full set, for reference:
1. **Cover** — headline that states the play, bottom line, 4 sourced stat cards, 3 themes, 4 moves
2. **Executive summary** — the play, main threat, leadership asks, fix-before-next-meeting
3. **00 Introduction & background** (evidence-driven) — why the call happened, timeline, who was in the room (role + read)
4. **01 Call analysis · what was said** — movements table with timestamps, 4 key quotes
5. **02 Call analysis · between the lines** — abstract patterns (what they are really buying,
   constraints that shape the architecture, demo vs. stated priority, political map),
   absent stakeholders, pre-mortem, contradictions vs. systems of record
6. **03 Desired outcomes** — ranked table: outcome · verbatim evidence (mm:ss, or a verbatim line when the source has no timestamps) · why it matters; one implied outcome
7. **04 What we can deliver** — deliverable · outcome # · how · cost/constraint impact · readiness
   (Ready / Pilot build / Needs customer / Find); one ASCII flow diagram (`.diag`)
8. **05 Win opportunities** (evidence-driven) — explicit vs. implied, capability, size/timing; non-IT value angle; deprioritized items
9. **06 Claims check** — said on the call · verdict pill · docs + "say instead"; customer claims checked
10. **07 Recommended next steps** — timeline diagram to the next customer milestone; our ask / our offer / keep separate; a pilot or proof with measurable success criteria only when the call supports one (log the include/cut in §Section choices)
11. **08 Actions & talking points** — owner · due · action; talking points tied to outcome # (Say / Don't say, each Say line customer-safe and sourced); one-line leadership summary
12. **Appendix · Sources & coverage** — primary source, doc refs [D#/M#/W#], internal sources incl. empty ones, QA verdict

Voice per `<intel>/references/method.md §5`: outcome first, short sentences, every number sourced,
quotes timestamped, inference labelled as inference. Customer names fine (internal); never
tokens, tenant URLs, entity IDs or CRM record IDs.

## 4. Build, QA once, fix, verify
```
python3 <intel>/scripts/build.py <work>/build "<out>/<Account> Call Debrief <YYYY-MM-DD>.pdf" \
  --title "<Account> Call Debrief" --footer "<Account> · Call Debrief · Dynatrace internal"
python3 <intel>/scripts/check.py "<pdf>"
```
- Adversarial QA: one fresh agent gets `pdftotext -layout` output, the transcript and the research
  files, including `PLAN.md` (not your reasoning). On top of its fact checks, it verifies that
  every context lane and every evidence-driven section traces to a call moment; returns CONFIRMED / PLAUSIBLE findings with exact replacement
  text. Apply CONFIRMED, update the appendix QA line, rebuild. No second round.
- `check.py` exits 0 and you open the cover plus at least 2 other page PNGs before saying done.
- User corrections outrank agent findings: apply them and re-verify the dependent counts/pills.

## 5. Deliver
Print path, page count, bottom line, QA verdict, and what was not verified. Don't send it
anywhere unless asked.

## Guardrails
- The transcript is the primary source; AI recap notes are orientation only.
- Our own over-promises go in the claims check, stated plainly — including the user's.
- Internal chat threads and roadmap content never appear under "Say".
- `-clean`: replace account, people, hostnames and internal-only statements with placeholders,
  drop internal-tagged rows, and keep the footer text check.py requires.
- Unknowns stay unknown (freeze dates, budgets, counts). Report every empty source.
