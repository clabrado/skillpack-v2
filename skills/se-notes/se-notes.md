# se-notes — Living Reference

Backfills a Solutions Engineer's support activities and demos from email,
calendar, Gong and Slack into Salesforce as SE Events.

> **Purpose of this doc:** context injection (read it before changing or
> running the skill) and an operational runbook. Update it after every run
> that teaches something new: schema drift, a source that broke, a tiering
> rule that was wrong.

---

## 1. Current Status

| Item | State | Notes |
|---|---|---|
| `SKILL.md` procedure | ✅ | Derived from a real 30-day backfill (24 events created, verified by count query) |
| `se_events.py context` | ✅ | Run against the live org: 100 accounts, 144 open opps, 26 existing entries resolved |
| `se_events.py create --dry-run` | ✅ | Picklist validation refuses bad values (exit 2), passes good ones |
| `se_events.py create` (live) | ⏳ | Same `sf data create record` call shape as the run that created 24 events; the script path itself not yet run live (avoided duplicate test records) |
| Calendar sweep | ✅ | `outlook_calendar_search` paged by offset; ~189 events / 30 days |
| Email sweep | ✅ | Sent Items + keyword fan-out |
| Slack sweep | ✅ | `from:self` + channels + canvases |
| Gong confirmation | ⚠️ | In the first run Gong returned no calls the user could access in the window; treat as optional |
| Windows | ⏳ | Untested; needs `sf` + `python3` on PATH |

**Known gaps / risks at this commit**
- Tiering is judgment applied by the model; recurring invites are the main
  false-positive source, hence the "hold" tier.
- Offline work (email/Slack) gets an approximate 30-minute slot.
- Off-list accounts (not on the user's account team) are never auto-created.
- Org schema is Dynatrace-specific (`FTSEvents` record type + custom fields);
  other orgs will fail fast in `context`.

## 2. What is se-notes

An SE does customer work across email, meetings and Slack, but leadership
reporting reads Salesforce. Manually logging every demo, POC assist and
support answer is the step that gets skipped. `/se-notes <lookback>` finds
every such activity in the window, diffs against what Salesforce already has,
creates the missing SE Events, and lists anything weakly evidenced for the
user to approve. Scope: one user, their account-team accounts, one window.

## 3. Design

**Goals:** never log work that can't be backed by evidence; never duplicate
existing entries; no hardcoded org/user identifiers; one approval surface for
the uncertain items.

| Decision | Choice | Reason |
|---|---|---|
| Record type | SE Events (`FTSEvents`) | Matches how peer SEs self-log; auto-assigns an FTS number |
| Write path | `sf` CLI | The Salesforce MCP exposes SOQL + metadata only, no record DML |
| Sweep | 3 parallel read-only subagents | Sources are independent; keeps raw mail/Slack out of the main context |
| Dedupe unit | account × day × distinct piece of work | Meeting + follow-up email is one activity, not two |
| Uncertain items | Hold tier, not created | Calendar acceptance ≠ attendance |
| IDs | Resolved at runtime | Repo is public; record type / user IDs are org-specific |
| Create order | One record, read back, then the rest | Catch schema/permission problems before bulk writes |

**Non-goals:** editing or deleting existing records; logging other users'
activity; Tasks (Gong already auto-logs those).

## 4. Auth Architecture

| Identity | Mechanism |
|---|---|
| Salesforce | `sf` CLI org auth (`sf org login web`); alias from `--org` / `$SE_NOTES_SF_ORG` / default target org |
| Microsoft 365, Slack, Gong | The host's MCP servers; the skill calls their login tool once on auth failure |

No credentials are stored by the skill.

## 5. API / Interface Surface

SOQL used by `context` (all filtered by the running user's Id):
- `User WHERE Username = <sf org display username>`
- `RecordType WHERE SobjectType='Event' AND DeveloperName='FTSEvents'`
- `AccountTeamMember WHERE UserId = …` (100 rows in the first run)
- `Opportunity WHERE IsClosed=false AND AccountId IN (…)` (batched by 150)
- Existing coverage: `Event` (owned), `EventRelation` (invited), `Task` (owned) in window
- `sf sobject describe -s Event` → picklists

Event fields written: `RecordTypeId, OwnerId, Subject, Type, StartDateTime,
EndDateTime, WhatId, Event_Location__c, Meeting_Outcome__c='Complete', ShowAs,
Description, Primary_Solutions__c, Product_Tags__c, Sales_Process_Stage__c`.
Read back: `FTS_Request_Number_FTS__c` (auto-assigned, e.g. `FTS-3565xxxx`).

## 6. Tool / Function Reference

| Command | Params | Output |
|---|---|---|
| `context` | `--out ctx.json --since YYYY-MM-DD --until YYYY-MM-DD [--org]` | `ctx.json`, `accounts.tsv`, `opps.tsv`, `existing.tsv`, `picklists.json` |
| `create` | `--context ctx.json --plan plan.json [--dry-run]` | Validation report; `results.json`; verified count |

`plan.json` item: `account_id, opp_id|null, type, start_utc, minutes, subject,
location, solutions, tags, description`.

## 7. How to Use

```
/se-notes 30d             # last 30 days
/se-notes 2w --dry-run    # preview only
/se-notes 2026-09-13:today --all   # also create held items
```

Follow-ups in the same session: "add <account> <relative meeting>, note <text>"
→ one-item plan through `create`.

## 8. Registration / Installation

`./install.sh` copies `skills/se-notes` to `~/.claude/skills/se-notes`.
Prereqs: `sf` CLI logged in, M365 + Slack MCPs connected (Gong optional).
Optionally `export SE_NOTES_SF_ORG=<alias>`.

## 9. Staying Current

- `context` fails fast if the record type or any required field disappears;
  update `REQUIRED_FIELDS` / `RT_DEVNAME` in `se_events.py`.
- New picklist values are picked up automatically from the describe call.
- If an MCP renames tools, update the sweep table in `SKILL.md`.

## 10. Code Reference

| Where | What |
|---|---|
| `se_events.py: RT_DEVNAME` | Record type developer name |
| `se_events.py: REQUIRED_FIELDS / PICKLISTS` | Schema the skill depends on / validates |
| `se_events.py: build()` | Plan item → Event payload (defaults: Virtual, Complete, Busy) |
| `se_events.py: create_one()` | Escaping for `sf data create record -v` |
| `SKILL.md §3` | Merge + tier rules |

## 11. Open Items / Future Work

| Priority | Item |
|---|---|
| High | First live run of `create` through the script (not the ad-hoc loader) |
| Med | Link `WhoId` to the customer contact when the attendee email matches a Contact |
| Med | Persist a per-user "already reconciled through" date to shorten repeat runs |
| Low | Windows verification |

## 12. Changelog

| Date | Change | How discovered |
|---|---|---|
| 2026-10-13 | Created from a manual 30-day backfill: 24 SE Events + 1 follow-up one-off | First real reconciliation run |
| 2026-10-13 | Gong treated as optional confirmation | Gong returned no accessible calls for the window |
| 2026-10-13 | Hold tier for calendar-only / recurring invites | Recurring syncs + CSE office hours overlapped team meetings |
