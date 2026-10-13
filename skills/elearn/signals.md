# What /elearn looks for

Ordered by blast radius: an item higher on this list costs the user more per session than one lower down. Mappers extract these per session; reducers merge them across sessions; every claim carries the session ids that show it.

## 1. Instructions the user types by hand (a skill should own them)

Text in `turns` that tells the agent HOW to work rather than WHAT to do: process, order of steps, tools to prefer, checks to run, style, who to notify. Quote it exactly (at most 200 characters). Then check the loaded skills in `surfaces.json`: if one already states it, the owner is that skill (the phrase joins it as a trigger or a line); if none does, the owner is NEW.

The task content itself ("fix the flaky test in X") is not an instruction. A phrase seen in one session is a candidate; two or more distinct sessions make it a habit.

`turns` holds only what the human typed. The collector already removed subagent (sidechain) records, sdk feeds, latch steerer injections, scheduled `/loop` fires, task notifications, skill bodies, and pasted blocks. A turn that still reads like machine text is a collector defect: name it under `## Batch candidates` as `[gap] collector kept non-human text`, with the session id, and do not count it as a habit.

The user's global instructions file (`<claude home>/CLAUDE.md`) is loaded into every session. A phrase that file already states is not NEW: its owner is that file, and the action is at most a sharper line in it, never a new skill.

## 2. Friction (the harness failed the user)

Turns where the user corrected the agent, repeated an earlier instruction, said the result was wrong or too big, or asked "how's it going" while waiting. Quote briefly. Friction that recurs across sessions points at a missing or unclear skill line.

## 3. Stale skill lines (a loaded skill is wrong)

A line in a loaded SKILL.md that the session shows to be wrong or outdated: a path that did not exist, a flag or command that failed, a model or tool name that was overridden, a step the user told the agent to skip. Name the skill, quote the current line from the file, and quote the trace evidence. If the line is not in the current file, there is no claim.

## 4. Unused surfaces (candidates to remove)

Never counted by an agent. `usage.json` holds the deterministic counts: loaded skills with count 0 and `in_skill_usage: false`, commands and agents with count 0, plugins with count 0, MCP servers with count 0, workflows with count 0. `in_skill_usage` means Claude Code's own record (`.claude.json` → `skillUsage`) names the skill, which counts as use outside this window. `surfaces.json` holds the structural findings: plugins listed as enabled but not installed, and duplicate skill names loaded from two places. For each, the safety argument is what still does the job: a second loaded copy, a plugin copy, or the fact that the plugin was never enabled. A copy outside `surfaces.json` (a dotfiles repo, a backup) is not a loaded surface. If nothing else does the job, the action is `ask`, not `delete`. `surfaces.json` also carries `referenced_by` (loaded skills that name this one) and `protected` (plugin or git-tracked); a referenced skill is an `ask` that names the referrers, and a protected skill is never removed or edited in place (see `report-format.md`).

Hooks are config entries in `settings.json`. Their runs are not in the transcripts, so their count is `None`: list them as information, never as a delete.

MCP servers that come from claude.ai connectors (`mcp__claude_ai_*` tool names) are not in local config; `usage.json` lists them under `mcp_servers_used_but_not_in_local_config`. They are never a delete.

## 5. Gaps (a recurring need with no owner)

A job the user did by hand in two or more sessions that no skill, command, agent, MCP server, or workflow covers. Gaps are for discussion; they carry no action id unless the user asks for a skill.

## Per-session record shape (mappers)

```
### <index> <session id> — <title>
- area: repo and top directories touched
- task type: feature | bug fix | debugging | ops/infra | research | config/harness | writing | other
- skills used / mcps used / agents used: names from the session file (or none)
- instructions outside skills: quoted, with the owning skill or NEW
- friction: quoted
- stale skill signals: skill, quoted current line, quoted evidence
- gaps
```

End each mapper note with `## Batch candidates`: `- [phrase|stale|gap] <text> | sessions: <ids> | owner: <skill or NEW>`, duplicates merged within the batch.
