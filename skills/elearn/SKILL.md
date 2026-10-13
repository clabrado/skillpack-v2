---
name: elearn
description: >-
  Learn from your own Claude Code sessions and tune your setup: add skills for
  things you keep typing, fix stale skill instructions, and retire skills,
  commands, plugins, or MCP servers you never use. Triggers: "/elearn",
  "elearn", "learn from my claude traces", "what skills do I never use". Not for
  summarizing sessions into notes or memory.
argument-hint: "[--mode step|auto|report] [--days N | --since-last | --limit N] [--per-trace] [--include-headless] [--cwd PATH] [--focus TEXT] [--resume]"
---

# /elearn

Read the sessions this user sat at, find what they repeat, correct, and never use, and change the harness so the next session needs less typing. Every path derives from the claude home (`~/.claude`); state, runs, trash, and decisions live under `<claude home>/elearn/`.

```
You (the top-level session)
│
├── 0. state.py get → resume a pending run; collect_sessions.py --estimate → price per scope;
│      read the user's wording → decide, or ask mode + scope once with the price on each option
├── 1. collect_sessions.py  → <RUN>/sessions/*.json, surfaces.json, usage.json, phrases.json   (deterministic, seconds)
├── 2. state.py plan, then Claude subagents (Agent tool), phase by phase, all inside this turn:
│      Map     one subagent per batch of sessions → map/<range>.md        (signals.md §1,2,3,5)
│      Reduce  one subagent per 10 notes, round after round, until one synthesis remains
│      Verify  three skeptics: phrases, stale lines, deletes — keep or drop, add nothing
│      Report  report.md + actions.json                                     (report-format.md)
├── 3. Short version in chat — end the turn on it
└── 4. Curate with the user → apply → decisions.jsonl → state.py → done
```

Files next to this SKILL.md: `collect_sessions.py`, `state.py` (all filesystem work: plan, check, trash, backup, decide, wait), `prompts.md` (the five worker prompts and their placeholders), `signals.md` (what to look for, ordered by blast radius), `report-format.md` (shape of `report.md` and `actions.json`), `tests/test_collector.py`.

Placeholders: `<skill dir>` is the directory holding this SKILL.md; `<CLAUDE_HOME>` is `claude_home` from `state.py get`; `<RUN>` is the run directory the collector prints; `<run name>` is its last path component (for example `20261004-174034`). Run the helpers with `python3`; if `python3 <skill dir>/state.py get` does not print JSON (exit 0, or 3 when a run is pending), try `python`, and use the `python` field it prints as `<PYTHON>` from then on. Double-quote every path. If no Python 3 runs, tell the user and stop.

If the user asked to summarize learnings into memory or notes rather than change skills, do not run this skill; use the memory files and say why.

## 0. Resume or set up

`state.py get` is also the resume check. Exit code 3 means a run is pending; `pending.run_dir` is its directory and `pending.status` says where it stopped:

- `report_ready` or `curating` — the report exists but was never curated. Tell the user the run date, the session count, and the action count from `<run_dir>/actions.json`, and offer to resume at step 3 instead of collecting again. `decisions.jsonl` lines already written for that run are respected.
- `running` with no `report.md` — the run was interrupted (the session ended mid-run). Offer two choices: read the partial synthesis (`plan.json` → `synthesis`, else the newest file under `<run_dir>/reduce/`, else the `map/*.md` notes) and stop, or start a fresh run. `state.py check --phase <phase>` says which assigned files exist; a resumed run relaunches only the missing slots of the phase it stopped in.
- `collected` — sessions were collected but no subagent ran. Offer to start step 2 with that run dir, or start fresh.
- `--resume` takes the first offer in each case without asking.

For a new run, price it before deciding anything:

```bash
<PYTHON> "<skill dir>/collect_sessions.py" --estimate [--batch 1]
```

It scans everything in seconds and writes `estimate.json` under `<CLAUDE_HOME>/elearn/runs/estimate/` (its `out` field is the directory): for each scope (`all`, `30d`, `14d`, `quick` = the 25 most recent sessions, `since_last` when a completed run exists) the kept session count, agent count, estimated tokens, and a wall-time range, plus a `recommended` scope (`since_last` when it has sessions; otherwise `14d` above 100 sessions, else `all`). **Say what the numbers are:** the token and minute constants were calibrated on runs of the Grok Build version of this skill, not on Claude Code. Quote them as "estimate, not yet measured on Claude Code". If every scope has 0 sessions, tell the user there is nothing to learn from yet and stop.

Then read what the user typed and pick one of three paths. Depth words and go words combine ("just run it, quick" = `auto` + `quick`); explicit flags (`--mode`, `--days`, `--limit`, `--since-last`, `--per-trace`) win over wording. Two rules override both wording and flags: a first-ever run (no `last_completed_at` in `estimate.json`) is always `step`, because `auto` removes zero-use skills and the user has never seen a report; and above 40M estimated tokens, ask the neutral-path question below before launching.

- **They told you to go.** "just run it", "go ahead", "don't ask", "auto", "you decide" → mode `auto`, scope = the recommended one. Do not ask about mode or scope — but never skip the price: print the estimate line (sessions, ~tokens, minutes) before the collector runs. If the recommended scope prices above 10M tokens, "auto" still gets one question — "this will use ~N tokens, go?" — because a user who said "go" without seeing a number has not agreed to that number.
- **They told you the depth.** "quick", "cheap", "light", "a taste" → `quick`; "everything", "all of it", "deep", "thorough" → `all`; "per trace", "every session on its own" → `--per-trace`; "since last time", "what's new" → `since_last`. Mode stays `step` unless they also said to go. State the price in one line.
- **Neutral** (bare `/elearn`, "learn from my claude traces") → ask once with one AskUserQuestion call of exactly two questions, then do not ask again until curation:
  - **Mode** — `step` (recommended): present each group of actions and apply what the user picks. `auto`: apply every reversible action, then ask once about the rest. `report`: write the report, change nothing.
  - **Scope** — one option per scope in `estimate.json` (AskUserQuestion allows four options, so offer the recommended scope plus the three nearest), each labeled with its price, for example "Since last run — 12 sessions, ~7M tokens est. (recommended)". Headless and steerer sessions stay out unless the user passes `--include-headless`; say so in the option text rather than asking a third question.

If the user dismisses the question, ask the same two things in one plain-text line ("reply like `step, since-last`") and take exactly what they type.

`--per-trace` runs one mapper per session (most thorough, about twice the tokens; default is batches of 10). `--limit N` keeps the N most recent sessions. `--focus TEXT` is a free-text lens for mappers and reducers; it cannot remove a report section. `--cwd PATH` limits collection to one working directory.

**Unattended runs** (`/loop`, a scheduled task, `claude -p "/elearn"`): nobody will answer a question, so use `--mode report --since-last` unless told otherwise, skip the setup question, still print the coverage and price, and stay in the turn through step 2 exactly as below. Leave the report for the next interactive `/elearn`, which offers to resume curation from it (step 0). A first-ever unattended run has no `last_completed_at`, so `--since-last` scans everything; that is the one time the estimate can exceed the 40M guard — respect it and stop rather than ask.

Traces from another machine: copy that machine's `projects/` tree into a directory of its own (`<dir>/projects/...`) and run the collector with `--claude-home <dir>`; the subagents read the run directory, not the machine.

## 1. Collect

```bash
<PYTHON> "<skill dir>/collect_sessions.py" [--days N | --since-last | --limit N] [--batch 1] [--include-headless] [--cwd PATH] [--drop-pattern REGEX]
```

The collector creates the run directory itself (`<CLAUDE_HOME>/elearn/runs/<UTC timestamp>`, owner-only) and prints it as `run_dir` in its last stdout line; use that value as `<RUN>` everywhere below. It deletes nothing. It lists run directories older than 30 days as `runs_older_than_30d`; if that list is not empty, tell the user in one line and offer to move them to `<CLAUDE_HOME>/elearn/trash/`. Never remove them.

A session is a top-level `projects/<encoded cwd>/<uuid>.jsonl` file (subagent transcripts under `<uuid>/subagents/` are never read). A record counts as a human turn only when the human typed it — the filter is in the collector's docstring, measured on this machine's transcripts: `promptSource` `typed` or `queued`, or a slash command the human ran; never a sidechain, meta, compact-summary, tool-result, sdk, system, scheduled, peer, or suggested-prompt record; pasted blocks and latch steerer injections (`[steerer] ...`) are cut out. A session is kept when it has at least one human turn, is not a steerer or headless session (unless `--include-headless`; steerer sessions never), was not started under an OS temp directory, and is not a one-word smoke test with no tool use. `--drop-pattern` removes automation prompts; latch bootstrap briefs (`Read the file .../.latch/bootstrap/...`) are dropped by default. Pasted credentials are redacted before anything is written.

Outputs in `<RUN>`: `manifest.json` (params, counts, `dropped` by reason, `records_dropped` by reason, kept list), `sessions/NNNN-<id>.json` (human `turns`, `slash_commands`, `skills_loaded`, `mcp_servers_used`, `agent_types_used`, `tools`, `top_dirs_touched`, cwd, git root, title, model), `surfaces.json` (every skill, command, agent, plugin, MCP server, hook event, and workflow that exists — user skills, every `.claude/skills` from a session's cwd up to its git root, plugin skills — names and paths only, with `loaded`, `protected` (plugin, git-tracked), `referenced_by`, `skill_usage_names`, and `skill_name_collisions`), `usage.json` (deterministic hit counts, `unused_loaded`), `phrases.json` (prompts and instruction lines repeated across sessions), and `decisions.jsonl` (prior decisions, if any). The collector records the run as `pending: collected` in `<CLAUDE_HOME>/elearn/state.json`.

MCP inventory comes from `<CLAUDE_HOME>/settings.json`, `settings.local.json`, and `.claude.json` (user and per-project `mcpServers`); plugin inventory from `<CLAUDE_HOME>/plugins` and `settings.json` → `enabledPlugins`. Names only, never values.

If `sessions_kept` is under 5, do not launch: the fixed cost of the reduce, verify, and report subagents buys almost nothing from so few sessions, and a narrow window cannot support any retirement anyway — say so in one line and offer the next wider scope from `estimate.json`. `manifest.json` carries `estimate` for the chosen scope (agents, tokens, minutes); use those numbers, not a guess. Tell the user the coverage line (`seen`, `kept`, `dropped` by reason) **before** launching, and say plainly that the prompts from those N sessions will be sent to the model as part of the run. If `kept` is 0, fix the scope before going on. A skill counts as used when it was loaded (Skill tool, its SKILL.md was read, or its body was injected), its slash command appears in a prompt, or `.claude.json` → `skillUsage` names it; a slash command with no skill in the scanned roots shows up under `slash_commands_with_no_loaded_skill`, which means "not found", not "no skill exists".

## 2. Map-reduce with subagents

There is no workflow host. This session is the orchestrator: it launches Claude subagents with the Agent tool, phase by phase, and checks each phase with `state.py` before the next one. The prompts are in `<skill dir>/prompts.md`; fill every placeholder from `plan.json`, `manifest.json`, and `state.py` output. **Every artifact path comes from `state.py`, never from a subagent's text.** A subagent's final JSON line is its self-report; `state.py check` is the evidence.

Before launching, tell the user three things in one short message: the coverage line; the price from `manifest.json` → `estimate` (sessions, agents, ~tokens, minutes — Grok-calibrated, not yet measured on Claude Code); and that the run lives in this session, so ending the session stops it. Then:

```bash
<PYTHON> "<skill dir>/state.py" plan --run-dir "<RUN>" --batch <10, or 1 for --per-trace>
<PYTHON> "<skill dir>/state.py" set --run-dir "<RUN>" --status running --mode <mode> --scope <scope>
```

**Stay in the turn.** Do not end the turn, and do not say "it will notify me", until `report.md` and `actions.json` exist and `state.py wait` has returned `report_ready`. Ending the turn early kills a headless or scheduled run, and in an interactive session it leaves an orphaned run. If the Agent tool is not in your tool list, you are a subagent: stop and report that `/elearn` must run from the top-level session.

Models: mappers and reducers run on `sonnet`; the three skeptics and the report run on `opus`, so the checker is a different model from the builder. If the user named a model for this run, use theirs. Every subagent gets `subagent_type: "general-purpose"`.

1. **Map.** Read `<RUN>/plan.json` → `mappers`. Launch the mappers in waves of at most 10 Agent calls in one message, one per mapper, with prompt `prompts.md` §1. Wait for every subagent of the wave to report before the next wave. If every subagent of a wave of two or more failed at once, the usage limit is reached or the API is down: stop spending, set the state to `running` with a note, tell the user which wave stopped, and end the turn — a later `/elearn --resume` relaunches only the missing slots. After the last wave run `state.py check --run-dir "<RUN>" --phase map`; its `lost` list is the lost map slots. Add up `sessions_read` from the mappers' final lines. If no note exists, stop and tell the user.
2. **Reduce.** Run `state.py reduce-round --run-dir "<RUN>"`. It prints the groups of the next round (inputs and assigned output path each) or `done: true` with the `synthesis` path. Launch one reducer per group (waves of at most 10) with prompt `prompts.md` §2, wait for all, run `state.py check --phase reduce`, and repeat `reduce-round` until it prints `done: true`. If a round loses every slot, `reduce-round` refuses: stop and tell the user.
3. **Verify.** Launch the three skeptics in one message with prompt `prompts.md` §3 (3a, 3b, 3c). Wait for all three. `state.py check --phase verify` names any skeptic section that failed.
4. **Report.** Launch one subagent with prompt `prompts.md` §4. Put the failed skeptic sections in `{FAILED_LINE}` and the lost slot counts in the coverage placeholders. Then run `state.py wait --run-dir "<RUN>"` in the foreground (default `--timeout-min 9`, under the 10-minute shell limit) and repeat it until it exits 0 (`report_ready`, which it records in `state.json`).

Only this parent session writes `state.json`. A worker that writes outside the run directory can hit a permission prompt that nobody answers, and the run then sits forever.

**If the report subagent returns without both files**, or `wait` exits 3 (`report_stalled`) after it ended: do not relaunch the whole run. Present the synthesis's sections 1–3 (kept claims only, per the three skeptic files, trimmed to the top rows, marked "unverified report step") and offer one retry of the report subagent alone. If the retry fails too, stop there: the synthesis is the result, and the user can curate from it by hand. Never write `report.md` yourself from the synthesis — a report the skeptics did not gate must not feed the apply step.

**If `wait` exits 4 (`phase_stalled`)**, no file under the run directory changed for an hour: a subagent is wedged or gone. Run `state.py check` for the current phase, relaunch only the missing slots once, and do not wait longer than one more `--phase-stall-min`.

If the user asks how it is going, run `state.py check` for the current phase and say which phase is writing.

## 3. Present

Read `report.md`. Give the user the Overview (problem, proposed change, action counts), the three tables trimmed to their top rows, the Coverage line, and the path to the full report. Keep it under a screen; do not paste `actions.json`. If the report's headline names a skill as missing, check `slash_commands_with_no_loaded_skill` in `usage.json` first: the skill may exist in a root the collector did not scan, and the right action is to say so, not to create a duplicate.

**The report comes first, on its own.** Print that short version as a plain message and end the turn on it; the first AskUserQuestion of step 4 belongs to the next turn, after the user has had the report in view. Never open a picker in the turn that presents the report, and never open one without having presented it — a user who is asked "which of A1, A5, A7 should go?" before seeing what A1 is cannot give consent, whatever they pick. If the report proposes nothing to create or edit, say so; "no new skills" is a valid outcome, not a reason to jump to deletes.

## 4. Curate and apply

`actions.json` is the work list (fields in `report-format.md`). Consent rules, identical in every mode:

- An action is applied only when the user picked its id, or in `auto` mode when it is reversible and not `requires_confirmation`.
- A free-text answer ("Other", "just go", "fix the wording") is not consent. Re-ask with the literal reading as options ("edit existing skills only, create none?") before writing anything.
- Options the user left unpicked are recorded `deferred`, not `rejected`. Only an explicit refusal ("no", "reject", "keep", "none") is `rejected`. Deferred items return next run; rejected ones do not.
- One group's answer never authorizes another group. Ask per group even after "all" on the previous one.
- Before recording rejections, re-read the answer once: a single-item pick on a multi-select that offered many is the shape of an accidental Enter. Apply the pick, defer the rest, and say so.

Apply mechanics:

- `create` — Write `edit.replacement` to `path` (`<CLAUDE_HOME>/skills/<name>/SKILL.md`); the Write tool creates the directory. Refuse if a skill, command, or built-in slash command of that name exists.
- `edit` — before the first edit to any file in a run, `<PYTHON> "<skill dir>/state.py" backup --run-name <run name> <path>` copies it to `<CLAUDE_HOME>/elearn/trash/<run name>/originals/<name>.md`; that copy is the undo and goes in `--undo`. Then use the Edit tool on `path` with `edit.anchor` as the old string; `edit.mode` says how: `replace` swaps the anchor for `replacement`, `insert_after` keeps the anchor and adds `replacement` after it, `append` adds `replacement` at the end of the file. If the anchor is missing, re-read the file and fix the anchor; never overwrite the whole file. An edit of the global CLAUDE.md always asks first.
- `propose` — the target is protected. Never edit a plugin or git-tracked file in place: a plugin sync overwrites the first, and the second lands in a repo this skill does not own. Write the patch (current text with `edit.anchor` → `edit.replacement` applied, as a unified diff) to `<RUN>/patches/<name>.diff` and tell the user where the fix belongs — upstream in the plugin, or a pull request in the owning repo.
- `enable` / `disable` — a plugin: change only that plugin's key in `<CLAUDE_HOME>/settings.json` → `enabledPlugins` with the Edit tool. Read only that block.
- `delete` — if `referenced_by` is non-empty, stop and ask, naming the referrers. A skill directory, command file, agent file, or workflow file: `<PYTHON> "<skill dir>/state.py" trash --run-name <run name> <path>` moves it into `<CLAUDE_HOME>/elearn/trash/<run name>/` and prints where it went; it refuses symlinks and any other shape. An MCP server: `<PYTHON> "<skill dir>/state.py" mcp-trash --run-name <run name> --server <name> --file settings|claude-json [--project <key>]` writes the entry to an owner-only file in the trash **before** it removes the key, and prints names only; never echo the entry. Claude Code rewrites `.claude.json` itself, so re-read the key after the move. Hooks are never deleted by this skill. Undo is moving the file or the entry back.
- After each apply, re-read the changed file or config key and confirm the change is present.

By mode:

- **Narrow runs retire nothing.** Read `manifest.json` → `disuse_evidence` before group 3. When `sufficient` is `false` (the run was `--cwd`-scoped, kept fewer than 20 sessions, or spans under 7 days), skip group 3 entirely in every mode — apply no `delete`, `disable`, or `group` action even if the report emitted one — and tell the user in one line that zero hits in this window are not evidence of disuse and that retiring anything needs a run over every working directory. The "only copy of a job" rule below still applies when the window is wide.
- **step** — one AskUserQuestion per group: 1 (phrases → create/edit), 2 (updates), 3 (deletes/disables), then 4 (gaps, discussion only). `multiSelect: true` over action ids with the quoted evidence in each option's description; at most four options per question (the tool's limit), so split larger groups into several questions or calls; label `ask` and `propose` actions as such. Apply the picked ones before the next group, and write `deferred` for the unpicked ones the moment the group closes, so a user who goes silent leaves a complete ledger.
  A `kind: group` action is one question with three options, not one per item: **apply to all** (run the group's `action` on every item), **pick items** (expand into multi-select questions of at most four items each), or **skip all** (defer). Record one `decide` line per item either way, with the group id in `--path` so a later run can tell the batch apart.
- **auto** — apply every action with `requires_confirmation: false`, then one question for the `requires_confirmation: true`, `ask`, and `propose` actions, then apply the picked ones.
- **report** — stop after step 3, then set the state to `done` so the next run's `since_last` counts from here.

Record every decision with `<PYTHON> "<skill dir>/state.py" decide --run-dir "<RUN>" --id A3 --kind skill --action delete --target <name> --path <path> --decision applied|rejected|deferred [--undo <trash path>]`; it appends one JSON line to `<CLAUDE_HOME>/elearn/decisions.jsonl`:

```json
{"date":"<YYYY-MM-DD>","run_dir":"<RUN>","id":"A3","kind":"skill","action":"delete","target":"<name>","path":"...","decision":"applied|rejected|deferred","undo":"<CLAUDE_HOME>/elearn/trash/<run name>/<name>"}
```

Set `state.py set --run-dir "<RUN>" --status curating` when group 1 opens and `--status done` when the last group closes or the user stops; `done` is what `--since-last` counts from. If the user re-invokes `/elearn` while a run is pending, the resume path in step 0 handles it. After a completed run, the estimate's `since_last` scope is the recommended one, so a repeat run prices only the new sessions; if `since_last` has 0 sessions, say so and stop instead of relaunching over the same corpus.

Finish with what changed (paths), what was rejected or deferred, how to undo, and the full report path. In `step` and `auto` mode a run that changed nothing is unfinished unless the user rejected or deferred every action; say which.

## Rules

- Price the run before launch. A first run is mode `step`.
- Nothing is retired, edited, or trashed before `wait` has returned `report_ready` and the report is on screen — not even when the user asked up front to "delete the stale skills": that request is curated from the report, never executed from the collection. `state.py trash` before a report is a bug, whoever asked.
- Zero hits is evidence, not proof, and only in a wide window (`manifest.json` → `disuse_evidence.sufficient`). A narrow window retires nothing. The only copy of a job is an `ask`, not a delete. A skill in `skillUsage`, or one that other loaded skills reference, is not a free delete.
- A delete is a move into `<CLAUDE_HOME>/elearn/trash/<run name>/`. Nothing in this skill removes a file.
- A protected surface (plugin or git-tracked) is never edited in place.
- One repeated phrase is one action; it joins the skill that already owns the job when one exists.
- Never print secrets: tokens, headers, env values, API keys, auth files. Inventory is names and paths only.
- If the user disputes a count, re-run the collector; do not guess.
