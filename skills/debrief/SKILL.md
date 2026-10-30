---
name: debrief
description: >-
  Post-call debrief and plan of action. Point it at one customer call (Teams/Stream recap
  link, Gong call, Krisp link, .txt/.vtt transcript, or pasted text). Pulls the full
  transcript, triangulates against Salesforce, Power BI, Slack, M365 and public docs,
  verifies every capability claim our side made on the call, and writes a Dynatrace-branded
  PDF in the /intel visual format: cover + bottom line, executive summary, introduction &
  background, call analysis (standard + inverted/abstract read), desired outcomes, what we
  can deliver, technical Dynatrace win opportunities (explicit and implied), claims check,
  recommended next steps with pilot criteria, actions & asks, sources. One adversarial QA
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

## 2. Gather in parallel (background agents, `model: sonnet`, one message)
Work dir: `<scratchpad>/<slug>/{src,research,build}`. Reuse any prior brief/research for the
account (`--prior`, or search home + scratchpads for the account name) instead of redoing it.
- **V1 claims check**: list every Dynatrace capability statement our side made (speaker +
  timestamp) plus key customer factual claims; verify each against public docs with URL +
  verbatim quote; verdict CONFIRMED / PARTIAL / REFUTED / UNVERIFIED; flag over-promises.
- **I internal**: SFDC (account, opps, tasks, contacts matching attendees), Power BI (existing
  customers), Slack + M365 since the call, any assets demoed on the call. No Highspot.
Rules for agents: read-only, no messages, cite everything, report empty sources.

## 3. Write `build/content.html` (main thread, from the skeleton)
Sections, in order (adapt titles to the account; drop one only if empty, and say so):
1. **Cover** — headline that states the play, bottom line, 4 sourced stat cards, 3 themes, 4 moves
2. **Executive summary** — the play, main threat, leadership asks, fix-before-next-meeting
3. **00 Introduction & background** — why the call happened, timeline, who was in the room (role + read)
4. **01 Call analysis · what was said** — movements table with timestamps, 4 key quotes
5. **02 Call analysis · between the lines** — abstract patterns (what they are really buying,
   constraints that shape the architecture, demo vs. stated priority, political map),
   absent stakeholders, pre-mortem, contradictions vs. systems of record
6. **03 Desired outcomes** — ranked table: outcome · verbatim evidence (mm:ss) · why it matters; one implied outcome
7. **04 What we can deliver** — deliverable · outcome # · how · cost/constraint impact · readiness
   (Ready / Pilot build / Needs customer / Find); one ASCII flow diagram (`.diag`)
8. **05 Technical Dynatrace win opportunities** — explicit vs. implied, capability, size/timing; non-IT value angle; deprioritized items
9. **06 Claims check** — said on the call · verdict pill · docs + "say instead"; customer claims checked
10. **07 Recommended next steps** — timeline diagram to the next customer milestone, pilot with measurable success criteria, our ask / our offer / keep separate
11. **08 Actions & asks** — owner · due · action; Say / Don't say; one-line leadership summary
12. **Appendix · Sources & coverage** — primary source, doc refs [D#/M#/W#], internal sources incl. empty ones, QA verdict

Voice per `<intel>/references/method.md §5`: outcome first, short sentences, every number sourced,
quotes timestamped, inference labelled as inference. Customer names fine (internal); never
tokens, tenant URLs, entity or SFDC IDs.

## 4. Build, QA once, fix, verify
```
python3 <intel>/scripts/build.py <work>/build "<out>/<Account> Call Debrief <YYYY-MM-DD>.pdf" \
  --title "<Account> Call Debrief" --footer "<Account> · Call Debrief · Dynatrace internal"
python3 <intel>/scripts/check.py "<pdf>"
```
- Adversarial QA: one fresh agent gets `pdftotext -layout` output, the transcript and the research
  files only (not your reasoning); returns CONFIRMED / PLAUSIBLE findings with exact replacement
  text. Apply CONFIRMED, update the appendix QA line, rebuild. No second round.
- `check.py` exits 0 and you open the cover plus at least 2 other page PNGs before saying done.
- User corrections outrank agent findings: apply them and re-verify the dependent counts/pills.

## 5. Deliver
Print path, page count, bottom line, QA verdict, and what was not verified. Don't send it
anywhere unless asked.

## Guardrails
- The transcript is the primary source; AI recap notes are orientation only.
- Our own over-promises go in the claims check, stated plainly — including the user's.
- Internal Slack/roadmap content never appears under "Say".
- Unknowns stay unknown (freeze dates, budgets, counts). Report every empty source.
