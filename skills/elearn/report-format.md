# /elearn output format

Two files in the run directory. `report.md` is for the user. `actions.json` is for the apply step. Every action in `actions.json` must appear in `report.md`, and every claim in sections 1–3 of `report.md` must be backed by a skeptic's Kept list.

## report.md

Write short sentences with one meaning each. No hedged summaries: a count is a number, a path is a path.

```markdown
# /elearn report — <today>

## Overview
Problem: <2–4 sentences: what the traces show the user repeating, correcting, or never using>
Proposed change: <2–4 sentences: the smallest set of harness edits that removes that repetition>
Actions: <N> total — <a> new skills, <b> skill updates, <c> enables, <d> deletes/disables, <e> need a decision

## 1. Repeated phrases -> skills
| # | Phrase (quoted) | Sessions | Owner | Action |
Owner is an existing skill (name, path), the global CLAUDE.md, or NEW <name>. Action is the action id from actions.json.

## 2. Skills to update
| # | Skill (path) | Stale line (quoted) | Evidence (session ids) | Replacement | Action |

## 3. Unused -> delete or disable
| # | Name | Kind | Count | Last used | Why safe | Action |
Kind is skill, command, agent, plugin, mcp, or workflow. "Why safe" names what still does the job, or says `only copy — ask`, or `referenced by <names> — ask`. A grouped action is one row that names the group and lists its members in the Name cell. Hooks never appear here: their runs are not recorded.

## 4. Gaps
Recurring needs with no owner. No action ids; these are for the user to decide.

## Unverified claims
Only present when a skeptic section failed: the claims from that section, listed but not acted on unless the user asks; any action emitted for them carries `requires_confirmation: true`.

## Dropped claims
Bullet list: claim, reason it was dropped (which skeptic, what failed). Include "previously rejected by the user" items here.

## Coverage
- sessions seen / kept / dropped by reason, and records dropped by reason (from manifest.json)
- human turns read; sessions read by mappers vs total
- map or reduce slots lost; skeptic sections that failed
- window and filters used (params from manifest.json)
- what this run could not see: headless and steerer sessions unless included, subagent transcripts, hook runs, claude.ai connector MCP servers, anything outside this machine's claude home
```

## actions.json

```json
{
  "run_dir": "<run_dir>",
  "generated_at": "<today>",
  "actions": [
    {
      "id": "A1",
      "kind": "skill | command | agent | plugin | mcp | workflow | config | group",
      "action": "create | edit | enable | disable | delete | propose | ask",
      "target": "<name>",
      "path": "<absolute path of the file or directory the action touches>",
      "protected": "plugin | git-tracked | null",
      "referenced_by": ["<loaded skill names that mention this skill>"],
      "reversible": true,
      "requires_confirmation": false,
      "evidence": {
        "sessions": ["<session id>", "..."],
        "count": 0,
        "quote": "<exact phrase or stale line, at most 300 chars>"
      },
      "reason": "<one sentence>",
      "edit": {
        "anchor": "<exact substring of the current file, or \"\" for create>",
        "replacement": "<full replacement text, or full file content for create>",
        "mode": "replace | insert_after | append"
      },
      "mcp": {"file": "settings | claude-json", "project": "<project key or null>"}
    }
  ]
}
```

Rules for the fields:

- `id` is `A1`, `A2`, … in report order.
- `path` is exact. For a `plugin` action it is `<claude home>/settings.json` and the change is one key in `enabledPlugins`. For an `mcp` action it is the config file that holds the server (`<claude home>/settings.json` or `.claude.json`, from the server's `sources` in surfaces.json), and the `mcp` block names it; there is no `edit` block, because the apply step moves the entry with `state.py mcp-trash`. Never include config values other than names.
- `reversible` is `true` for edits with an anchor, enables/disables, and deletes (the apply step moves deleted files and MCP entries to `<claude home>/elearn/trash/<run name>/`). It is `false` only when the apply step cannot undo the change from the trash directory or the anchor.
- `protected` and `referenced_by` are copied from `surfaces.json`. A protected skill is never edited or deleted in place: the action is `propose`, with `requires_confirmation: true` and a `reason` that says where the fix belongs — upstream in the plugin for `plugin`, a pull request in the owning repo for `git-tracked`. `propose` carries an `edit` block so the apply step can write the patch file.
- A `delete` whose `referenced_by` is non-empty is emitted as `ask`, and `reason` names the referrers.
- `requires_confirmation` is `true` for `ask`, `propose`, any `delete` of the only copy of a job, any edit of the global CLAUDE.md, and any unverified claim.
- **Narrow windows prove nothing.** `manifest.json` → `disuse_evidence.sufficient` is `false` when the run was scoped to one working directory or listed sessions, kept fewer than 20 sessions, or spans under 7 days. In that case section 3 is titled `## 3. Not seen in this window`, lists the zero-use surfaces as information only, emits **no** `delete`, `disable`, `ask`, or `group` action for them, and the Overview's deletes/disables count is 0 with `disuse_evidence.reason` quoted ("window too narrow to judge disuse: scoped to one working directory; only 3 sessions kept"). A skill unused in three sessions from one folder may be the user's most-used skill everywhere else.
- **Grouping.** Unused surfaces that share a kind and a disposition (for example "9 zero-use plugin skills → ask") are one action with `kind: group`, `action` set to the shared disposition, `target` a short label, and an `items` array of `{name, kind, path, protected, referenced_by, count, last_used}`. One decision is worth one row; 40 rows that each say "ask" are not 40 decisions. Never group across dispositions and never group anything with evidence of use (`count > 0` or `in_skill_usage: true`). A referenced zero-use skill is never a `delete`; its disposition is `ask`, so it joins the `ask` group of its kind with `referenced_by` filled in its item — it does not get its own row. The Overview's action count counts a group as one.
- `edit` is required for `create`, `edit`, and `propose`; omit it for enable, disable, delete, ask.
- **One phrase, one owner.** A repeated phrase whose job an existing skill already owns is an `edit` of that skill (a trigger or a line), never a `create`.
- `create` writes `<claude home>/skills/<name>/SKILL.md`. The `replacement` is the whole file: `---` frontmatter with `name` and `description` (what it does plus the trigger phrases), then a body of imperative steps. Add `argument-hint` only when the skill takes arguments. Use no other frontmatter key: no live skill under `<claude home>/skills/` carries an `origin` key, so a new skill has none. Use the quoted phrases as the trigger list and the body. The name must not collide with an existing skill, command, or built-in slash command.
