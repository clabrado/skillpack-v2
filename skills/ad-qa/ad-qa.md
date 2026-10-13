# ad-qa: Living Reference

Adversarial QA for any delivered ask, artifact, quote, or dataset. An independent Opus subagent attacks the deliverable against the original ask and every provided source.

> **Purpose of this doc:** context injection (read it before running or editing `/ad-qa`), plus an operational runbook. Update it after every real run, bug fix, or design change.

## Current Status

| Item | State | Notes |
|---|---|---|
| `SKILL.md` (workflow, prompt template, flags) | ✅ | Registered; harness lists `ad-qa` in available skills |
| `extract.py`: PDF text + page PNGs | ✅ | Tested on 3 PDFs (3, 29 and 15 pages) on 2026-10-13 |
| `extract.py`: HTML | ✅ | Tested; gives text only (render separately for visuals) |
| `extract.py`: docx / pptx / xlsx | ✅ | Tested on fixtures 2026-10-13. xlsx gives a values pass plus a formulas pass. Formula cells from files Excel never saved have no cached value |
| soffice render for docx/pptx | ✅ | docx and pptx → PDF → PNG verified (1 page each) |
| Default single-Opus-reviewer run | ✅ | First live run on a customer PDF (v2), 2026-10-13. 9 findings; 8 reproduced; 1 false positive caught by the Step 4 re-check |
| `--deep` (3 lens agents) | ⏳ | Untested |
| `--fix` loop | ✅ | v2→v3: 15 exact-match replacements, re-render, check of all 3 pages |

**Known gaps and risks at this commit**
- **The reviewer only knows what's in the evidence pack.** If the main agent summarizes session evidence instead of quoting it, errors can launder through. The SKILL.md rule is verbatim excerpts.
- **Wide spreadsheets get truncated.** xlsx extraction caps at 2000 rows × 60 columns; very wide RFP-portal sheets (700+ columns) are cut off.
- **No OCR.** Scanned PDFs and images get visual review only.

## What is ad-qa
A skill (`/ad-qa`) that red-teams anything Claude or a human delivered before someone relies on it: chat answers, PDFs, decks, docs, spreadsheets, code, emails, RFP responses, quotes, data tables.
- **Where it lives:** `~/.claude/skills/ad-qa/`.
- **What it replaces:** ad-hoc "re-read it once" self-review. That review is biased, because the author checks their own work against their own memory.

## Design

**Goals**
- Universal: works on any domain or format.
- Independent: a fresh-context Opus reviewer.
- Evidence-bound.
- Low false-positive rate.
- Findings come with an exact fix.

| Decision | Choice | Reason |
|---|---|---|
| Reviewer | `general-purpose` agent, `model: opus` | Forks ignore model overrides and inherit author bias; a fresh context forces evidence over recall |
| Context transfer | On-disk evidence pack (ask, artifact, sources, audience) | The subagent can't see the conversation; files are inspectable and reusable |
| Session evidence | Verbatim excerpts; author reasoning labeled `[AUTHOR-DERIVED]` | Stops the author's assumptions from being "verified" as facts |
| Finding gate | Subagent self-refutes, then the main agent re-verifies | Two filters on false positives |
| Visual artifacts | Rasterize pages, and the reviewer reads the PNGs | Text extraction misses orphaned headings, overflow and clipping |
| Fixing | Opt-in `--fix`, versioned copy, re-render, re-QA | Never mutate the original; "fixed" requires a render check |
| Deep mode | 3 parallel lenses: numbers / sources+quotes / ask+logic+render | Big artifacts exceed one reviewer's attention |

**Non-goals**
- Code-bug review of diffs (use `/code-review`).
- Security audit (use `/security-review`).
- Rewriting for style.

## Auth Architecture
None. The skill uses local tools only. Fetching a URL target uses whatever web or MCP access the session already has.

## API / Interface Surface
- **Invocation:** `/ad-qa [target] [--fix] [--deep] [--sources a,b] [--focus lens] [--strict]`.
- **Default target:** the last deliverable in the session.
- **Evidence pack layout:** `<scratchpad>/ad-qa-<slug>/{ask.md, audience.md, artifact/, sources/}`.
- **Reviewer output contract:** Verdict, Findings, Verified clean, Unverifiable.
  - Each finding: ID | Severity | CONFIRMED/PLAUSIBLE | Location | What's wrong | Evidence | Fix.

## Tool / Function Reference

**`extract.py <file-or-dir> <out_dir>`**

| Input | Output |
|---|---|
| `.pdf` | `-layout` text + `<stem>-pages/page-N.png` at 70 dpi |
| `.docx` / `.pptx` | Text (paragraphs, tables, slide notes) + soffice → PDF → PNGs |
| `.xlsx` / `.xlsm` | Values pass, then a formulas-only pass (cap 2000×60) |
| `.csv` / `.tsv` | Rows (cap 5000) |
| `.html` | Tag-stripped text |
| Images | Pointer to view with Read |
| Code and text | Raw |

- Prints a one-line manifest per file.
- If one file fails, it reports the failure and continues with the rest.
- Run it with `python3 -P`.

## How to Use
- **Quick check of your last answer:** `/ad-qa`
- **A file, plus extra ground truth:** `/ad-qa ~/Downloads/report.pdf --sources ~/Downloads/data.xlsx`
- **High stakes, with fixes:** `/ad-qa deck.pptx --deep --fix`
- **Numbers only, emphasized:** `/ad-qa model.xlsx --focus numbers --strict`

## Registration / Installation
`./install.sh` (or `install.ps1`) copies `skills/ad-qa` to `~/.claude/skills/ad-qa`, where Claude Code auto-discovers it.

## Staying Current
- Re-run on a known-bad fixture after editing the prompt template. Keep a v1 fixture with known errors (the original had six, listed in the Changelog).
- If the harness adds a native adversarial-review primitive, compare against it and trim this skill accordingly.

## Code Reference
- `SKILL.md` Step 3a holds the reviewer prompt template. Edit it to tune severity rules or lenses.
- `extract.py`:
  - `TEXT_EXT` / `IMG_EXT`: format routing
  - `xlsx_text(max_rows, max_cols)`: truncation limits
  - `render_pdf` (`-r 70`): PNG resolution

## Open Items / Future Work

| Item | Priority |
|---|---|
| Run `extract.py` on large real-world docx/pptx/xlsx | Medium |
| First `--deep` run; tune the lens split | Medium |
| OCR fallback for scanned PDFs (tesseract if installed) | Low |
| Smarter wide-sheet handling (detect non-empty column span) | Low |

## Changelog

| Date | Change | How discovered |
|---|---|---|
| 2026-10-13 | Created SKILL.md, extract.py, this doc | Requested after a manual adversarial QA of a customer PDF caught 6 errors (opp-amount mislabel, non-verbatim quote, unconfirmed meeting stated as fact, unlabeled assumptions, range-sum off by $5K, missing Year-2 caveat) |
| 2026-10-13 | extract.py verified on PDF (3pp/29pp/15pp) and HTML | Live test while building a real evidence pack |
| 2026-10-13 | `-I` → `-P`; page dirs keyed by full filename | Fixture test: `-I` dropped user site-packages (no openpyxl), and t.docx/t.pptx collided on `t-pages` |
| 2026-10-13 | First live run on a customer PDF (v2). PASS WITH FIXES. Caught a Year-2 growth understatement (projection at +31% MoM vs "slightly over"), AppSec using Sep memory instead of Oct (+50%), wrong RFP section cited as the Partial, and an omitted 9.7%-higher rate card on the open opp. False positive (a named contact flagged "unsourced") came from the evidence pack leaving out an email; Step 1 rule hardened | Live run |
