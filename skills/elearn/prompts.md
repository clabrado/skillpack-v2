# /elearn worker prompts

The parent session fills these prompts and passes each one to a Claude subagent (the Agent tool). A subagent cannot read the parent conversation, so everything it needs is in its prompt.

Placeholders, filled by the parent from `plan.json` and `manifest.json` — never from a worker's text:

| Placeholder | Value |
|---|---|
| `{RUN}` | the run directory (`manifest.json` → `run_dir`) |
| `{SKILL_DIR}` | the directory holding this file |
| `{CLAUDE_HOME}` | `manifest.json` → `claude_home` |
| `{TODAY}` | today's date, `YYYY-MM-DD` |
| `{USER_LABEL}` | the user's name, or `the user` |
| `{FOCUS_LINE}` | `Extra focus from {USER_LABEL}: <text>` when `--focus` was given, else an empty line |
| `{N}`, `{M}`, `{FIRST}`, `{LAST}`, `{FILE_LIST}`, `{NOTE}` | one mapper's entry in `plan.json` → `mappers` |
| `{G}`, `{ROUND}`, `{FINAL_LINE}`, `{INPUT_LIST}`, `{OUT}` | one group in the round `state.py reduce-round` printed |
| `{SYNTHESIS}` | the path `state.py reduce-round` printed with `done: true` |
| `{VERIFY_FILES}`, `{FAILED_LINE}`, `{LOST_MAP}`, `{LOST_REDUCE}`, `{SESSIONS_READ}`, `{COUNT}` | report inputs (see the Report prompt) |

Every prompt starts with the shared rules block.

## Shared rules block

```
Today is {TODAY}. You are one worker in a /elearn run for {USER_LABEL}.
Run directory: {RUN}
Rules:
- Read files with tools before you write anything. A claim with no file behind it is invalid.
- Do not edit skills, plugins, hooks, settings, CLAUDE.md, memory, or session transcripts. Write only inside the run directory.
- Never print secrets: tokens, headers, env values, API keys, auth files. Config inventory is names only.
- Quote session ids from the files. Do not invent ids, counts, or skill names.
- Counts of skill, command, agent, plugin, MCP, and workflow use come from usage.json. Do not recount them by hand.
- Do not launch subagents, workflows, or background jobs. Run no command that changes a file outside the run directory: a command that needs the user's approval blocks you forever when the user is away.
- End your reply with exactly one line of JSON, the shape your section names, and nothing after it.
```

## 1. Map — one subagent per mapper in plan.json

```
{RULES}

You are mapper {N} of {M}.
Read every one of these session files in full ({FIRST} to {LAST} inclusive):
{FILE_LIST}
Each file is one Claude Code session {USER_LABEL} sat at: `turns` (only the prompts the human typed, in order; slash commands appear as `/name args`), `slash_commands`, `skills_loaded`, `mcp_servers_used`, `agent_types_used`, `tools`, `top_dirs_touched`, `cwd`, `git_root`, `title`, `model`.
Read {RUN}/surfaces.json once so you know which skills exist and are loaded (name, path, source, loaded).
Read {CLAUDE_HOME}/CLAUDE.md once: it is loaded into every session, so a phrase it already states has that file as owner.
Read {SKILL_DIR}/signals.md: it defines what to extract (sections 1, 2, 3, 5) and the per-session record shape. Section 4 is not your job.
{FOCUS_LINE}

Write {NOTE} with one record per session in file order, in the shape signals.md gives, ending with `## Batch candidates`.

Final line: {"ok": true|false, "note": "{NOTE}", "sessions_read": <files you read in full>, "candidates": <bullets under Batch candidates>}
Return ok=true only after the note exists and sessions_read equals the number of files you read in full. If a file is missing or unreadable, say so in the note and set ok=false.
```

## 2. Reduce — one subagent per group in each round

```
{RULES}

You are reducer {G} in round {ROUND}.{FINAL_LINE}
Read every one of these notes in full:
{INPUT_LIST}
Then read {RUN}/usage.json (deterministic use counts per skill, command, agent, plugin, MCP, workflow; `unused_loaded`; `slash_commands_with_no_loaded_skill`; `mcp_servers_used_but_not_in_local_config`), {RUN}/surfaces.json (what exists, paths, name collisions, plugins enabled but not installed), and {RUN}/phrases.json (exact repeated prompts and repeated instruction lines with distinct-session counts).
If {RUN}/decisions.jsonl exists, read it: it holds prior /elearn decisions. Never re-propose an action the user rejected. Mark an item already applied as applied instead of proposing it again.
{FOCUS_LINE}
Read {SKILL_DIR}/signals.md for the definition of each section and the safety rules for unused surfaces.

Merge the notes into {OUT} with these sections:
## 1. Repeated phrases -> skills — one bullet per phrase: quoted phrase, distinct session ids, owner (existing loaded skill with path, the global CLAUDE.md, or NEW <name>). Before naming an existing owner, open its file and quote the line the phrase joins or that already covers it.
## 2. Skills to update — one bullet per skill: path, the stale line quoted from the current file (open it; no line, no item), trace evidence with session ids, proposed replacement text.
## 3. Unused -> delete or disable — from usage.json only, per signals.md section 4: name, kind, path, count, last_used, why removal is safe or `ask`. Put zero-use surfaces that share kind and disposition in one bullet listing the names, referrers in parentheses; one bullet per surface only when it needs its own reason.
## 4. Gaps — recurring needs with no owner, with session ids.
## Dropped — every candidate from the input notes you did not carry forward, with the reason.

Keep every session id. Do not merge two different instructions into one phrase. Keep the file under 350 lines: the readers after you load it whole, and a longer file fails their read. Write it in pieces — one Write call for sections 1 and 2, then an Edit on the last line to append sections 3 and 4 — and keep any single tool call under roughly 6,000 words: a call whose arguments exceed the output limit is cut off and the whole turn is lost. Put the Dropped section in a sibling file `{OUT}.dropped.md` and leave a one-line pointer to it.

Final line: {"ok": true|false, "note": "{OUT}", "proposals": <bullets in sections 1-3>}
Return ok=true after the file exists.
```

`{FINAL_LINE}` is ` This is the final round: your output is the synthesis the whole run will act on.` when the round is final, else empty.

## 3. Verify — three skeptics, launched together

All three share this head:

```
{RULES}

You are a skeptic. Read the synthesis at {SYNTHESIS} in full. Keep or drop claims; add none.
Write your verdicts to the file named below as `## Kept` and `## Dropped` bullet lists that repeat the claim text and add a one-line reason. Create the file first and append a verdict after each claim, so a partial file survives if you are stopped. Check at most 40 claims; if the section has more, verify the 40 with the most sessions and list the rest under `## Unchecked`. Do not spend more than 25 tool calls in total.

Final line: {"ok": true|false, "note": "<the file you wrote>", "kept": <n>, "dropped": <n>}
Return ok=true after the file exists.
```

### 3a. Phrases

```
Section to verify: 1. Repeated phrases -> skills. Write {RUN}/verify/phrases.md
For each phrase: re-find it in {RUN}/phrases.json or in the `turns` of the named session files under {RUN}/sessions/. Keep it only if at least 2 distinct sessions show it, or 1 session shows it and the user repeated it inside the session after a correction. Then grep the loaded skill files listed in {RUN}/surfaces.json, and {CLAUDE_HOME}/CLAUDE.md, for the phrase's key words: if one of them already states it, keep the item only with that file as owner (correct the owner if the synthesis named NEW). Drop a phrase that reads like machine text (a steerer, a scheduler, a pasted brief): the human did not type it.
```

### 3b. Stale lines

```
Section to verify: 2. Skills to update. Write {RUN}/verify/stale.md
For each item: open the skill file and confirm the quoted stale line exists now. Open the named session file(s) and confirm the trace evidence contradicts that line. Drop the item if either check fails. Drop an item whose skill is `protected` in surfaces.json (plugin, git-tracked) unless the proposal is phrased as an upstream change or a pull request, because a plugin sync overwrites direct edits and a git-tracked file belongs to its repo.
```

### 3c. Deletes

```
Section to verify: 3. Unused -> delete or disable. Write {RUN}/verify/deletes.md
For each item: confirm in {RUN}/usage.json that count is 0 and, for a skill, that `in_skill_usage` is false. Confirm the safety claim by reading surfaces.json (a duplicate exists, a plugin copy stays, the plugin was never enabled). If the item is the only copy of a job, change the action to ask. Drop every hook and every MCP server that is not in local config. If {RUN}/decisions.jsonl exists and the user rejected the same delete before, drop the item. If {RUN}/manifest.json `disuse_evidence.sufficient` is false, drop every item in this section and say the window is too narrow.
```

## 4. Report — one subagent

```
{RULES}

You write the final /elearn report and the machine-readable action list.
Read {SKILL_DIR}/report-format.md first and follow it exactly for both files.
Inputs: the synthesis {SYNTHESIS}, the skeptic files:
{VERIFY_FILES}
{FAILED_LINE}
Also read {RUN}/manifest.json (coverage counts and params), {RUN}/usage.json, and {RUN}/surfaces.json.
Only claims kept by a skeptic go into sections 1-3. Dropped claims go under Dropped claims with their reasons.
Coverage facts for this run: map notes lost = {LOST_MAP}, reduce notes lost = {LOST_REDUCE}, sessions read by mappers = {SESSIONS_READ} of {COUNT}.
For every action that edits a file, open that file and make `edit.anchor` an exact substring of it. For every create, write the complete SKILL.md content with only the frontmatter keys report-format.md allows.
surfaces.json marks each skill with `protected` (plugin, git-tracked, or null) and `referenced_by` (loaded skills that name it). A protected skill is never edited or deleted in place: emit the action with `action: propose` and `requires_confirmation: true`, and say in `reason` whether the fix belongs upstream in the plugin or in a pull request in the owning repo. A delete of a skill with a non-empty `referenced_by` becomes `ask` and lists the referrers in `reason`.
Check manifest.json `disuse_evidence` first: when `sufficient` is false the window cannot show disuse, so section 3 becomes `## 3. Not seen in this window` with no delete, disable, ask, or group action and the Overview quotes `disuse_evidence.reason`, per report-format.md.
Group before you write: unused surfaces (count 0, `in_skill_usage` false) that share a kind and a disposition become ONE action with `kind: group` and an `items` array, per report-format.md. A report that lists thirty separate asks for thirty zero-use plugin skills is wrong; it should list one group. Keep single actions only for items with evidence of use and for a surface whose kind has no other zero-use member; a referenced zero-use skill goes into the ask group of its kind with referenced_by in its item.
{FOCUS_LINE}

Write {RUN}/report.md and {RUN}/actions.json. Every file you touch stays inside {RUN}; do not delete files. The parent session records the run as report_ready once both files exist.
Work budget: read each input file once (the synthesis, the three skeptic files, manifest.json, usage.json, surfaces.json, and the skill files you must anchor edits in) — at most 40 file reads in total. Write report.md first, then actions.json, with the Write tool in one call each — never through a shell heredoc or a script, and never by pasting the content into your reply; if a write fails, retry once with the same tool. The shell is for reading only. If you reach 40 reads or 80 tool calls without both files written, stop reading, write both files from what you already have, and say in the Overview which sections are incomplete. A shorter report is the correct outcome; an unwritten one is not.

Final line: {"ok": true|false, "report_path": "{RUN}/report.md", "actions_path": "{RUN}/actions.json", "overview": "<the Overview text>", "action_count": <n>}
```

`{FAILED_LINE}` is empty when all three skeptics returned their file. Otherwise it is: `These skeptic sections FAILED and are unverified: <names>. Put every claim from those sections under ## Unverified claims (not in sections 1-3) and set requires_confirmation=true on any action you still emit for them.`
