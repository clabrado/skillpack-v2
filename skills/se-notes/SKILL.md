---
name: se-notes
description: >-
  Reconcile a Solutions Engineer's real customer work against Salesforce. Takes
  a lookback period, sweeps Outlook email + calendar, Gong, and Slack for every
  support activity and demo on the SE's accounts, diffs that against what is
  already logged in Salesforce, then creates the missing "SE Events" (one per
  activity, linked to account/opportunity, marked Complete) and holds anything
  weakly evidenced for the user to approve. Triggers - "/se-notes", "se notes",
  "log my support activities", "make sure salesforce has my demos", "backfill
  my SE activities", "update salesforce with my calls".
argument-hint: "<lookback: 7d | 2w | 30d | YYYY-MM-DD:YYYY-MM-DD> [--dry-run] [--all]"
---

# /se-notes — backfill SE support activities + demos into Salesforce

The SE does the work in email, meetings and Slack; Salesforce only knows about
what got logged. This skill finds the gap and closes it, without inventing
activity that cannot be backed by something on disk.

## Arguments

| Arg | Meaning | Default |
|---|---|---|
| lookback | `Nd` days, `Nw` weeks, or `YYYY-MM-DD:YYYY-MM-DD` (`today` allowed as the end) | `7d` |
| `--dry-run` | Build and validate the plan, create nothing | off |
| `--all` | Also create the *held* (calendar-only / tentative) items without asking | off |

Resolve the window to absolute dates first and say it out loud
(e.g. "Window: 2026-09-13 → 2026-10-13").

## Requirements

- **Salesforce CLI** (`sf`) authenticated to the org. Org alias comes from
  `$SE_NOTES_SF_ORG`, else the CLI default target org (`sf org list`). Never guess.
- **Microsoft 365 MCP** (Outlook mail + calendar), **Slack MCP**, and
  optionally **Gong MCP**. If one is missing or fails auth, try its login tool
  once; if it still fails, carry on with the remaining sources and say which
  source was absent in the report.
- `python3` for `se_events.py` (stdlib only).

## Procedure

### 1. Preflight (main context, fast)

```bash
H=<this skill's dir>; S=<session scratchpad>/se-notes; mkdir -p "$S"
python3 "$H/se_events.py" context --out "$S/context.json" --since <start> --until <end>
```

`context` resolves, from the org itself (nothing hardcoded):
- the running user's Salesforce Id (from the CLI's username),
- the **SE Events** record type Id (`RecordType.DeveloperName = 'FTSEvents'`),
- the SE's accounts (`AccountTeamMember` where the user is on the team) →
  `accounts.tsv`,
- open opportunities on those accounts → `opps.tsv` (Id, account, name, stage),
- **existing coverage** in the window: Events the user owns, Events they are
  invited to (`EventRelation`), and Tasks they own (Gong auto-logs land as
  Tasks) → `existing.tsv`,
- Event picklist values → `picklists.json` (used later for validation).

Print a one-line status to the user: account count, existing entries in window.

### 2. Sweep — three parallel subagents, one message

Launch all three in a single message (they are independent). Each gets: the
window, the path to `accounts.tsv`, the exact output TSV path, and the rules
below. Each is **read-only** — no sends, drafts, reactions, RSVPs, or edits.

| Agent | Source | Output |
|---|---|---|
| calendar+gong | `outlook_calendar_search` query `*`, order oldest, page by offset until no `nextOffset`; keep events with ≥1 non-company attendee. Gong `list_calls`/`search_calls` to mark meetings that really happened. | `$S/calendar.tsv` |
| email | Sent Items for the whole window (page through), plus keyword fan-out: demo, POC, workshop, recap, recording, follow up, troubleshooting, ticket, configuration, dashboard, MCP, "next steps", plus the busiest account names. | `$S/email.tsv` |
| slack | `from:<self>` in window (paged, sort timestamp), messages *with* the user, account/shared channels, team forecast canvases. | `$S/slack.tsv` |

TSV columns for all three:
`date  start_utc  end_utc  account_name  account_id  type  subject  evidence  confidence  flags`

Rules to put in each agent prompt:
- **Counts:** the SE doing technical work for a customer — demo, POC help,
  troubleshooting/support, config assistance, answering customer technical
  questions (even internally on their behalf), workshops, sending follow-up
  material after a meeting, RFP technical answers.
- **Doesn't count:** internal 1:1s, team meetings, enablement, interviews,
  expenses/HR, marketing blasts, internal account syncs with no customer.
  Internal POC/demo prep → flag `internal-prep`.
- Map accounts by attendee email domain and subject. Accounts not on the
  team list → `off-list:<name>`. Multi-account sessions → `multi-account`.
- `flags`: `gong-confirmed`, `tentative`, `recurring-invite-only`,
  `internal-prep`, `off-list`, `multi-account`, `time-approx`.
- Subjects ≤ 70 chars, customer-safe. **Never copy meeting links, passcodes,
  tokens or secrets** into any output. If a secret is spotted in a message
  (e.g. a platform token pasted in a DM), report its location only — never
  the value.

While they run, tell the user what is sweeping. Do not poll; wait for the
completion notifications.

### 3. Merge + tier (main context)

Merge the three TSVs into **one activity per account per day per distinct
piece of work**:
- A meeting and its same-/next-day follow-up email are **one** entry (fold the
  follow-up into the description).
- Multi-day threads on one problem → one entry on the day of the substantive
  answer.
- Drop anything already in `existing.tsv` (same account, same day, matching
  subject/topic). Report those as "already covered".
- Drop `internal-prep` rows.

Tier each remaining activity:

| Tier | Rule | Action |
|---|---|---|
| **create** | Evidence from ≥2 sources, **or** one non-calendar source showing the SE did the work (sent email, own Slack message, Gong call), **or** a customer meeting the SE accepted with corroborating follow-up | Create |
| **hold** | Calendar-only (incl. recurring invites), tentative, CSE-hosted office hours, double-booked slots, weak "nothing shows you attended" | List for approval (create only with `--all` or user say-so) |
| **off-list** | Account not on the SE's team, or no account resolvable | List; create only if the user names the account |

Classify `Type` from: `First Demo`, `Follow-up Demo`, `Customer Meeting`,
`Post Sales Support`, `Remote POC`, `Workshop`, `Sales Presentation`,
`QBR – Customer`. Existing customers getting a demo → `Follow-up Demo`.
Offline work (email/Slack only) → `Post Sales Support` or `Remote POC`, a
30-minute slot, and `time-approx` noted in the description.

Link `WhatId` to the clearly relevant open opportunity from `opps.tsv` when
one obviously matches the topic; otherwise the account. Set
`Sales_Process_Stage__c` to that opp's stage when linked.

### 4. Write the plan, validate, create

Write `$S/plan.json` — a list of:

```json
{"account_id":"001…","opp_id":"006…|null","type":"Follow-up Demo",
 "start_utc":"2026-09-14T13:00","minutes":25,"subject":"…","location":"Virtual|Onsite",
 "solutions":"Security;Application Observability","tags":"MCP Server|''",
 "description":"what was done. Sources: calendar, email, Slack."}
```

`solutions` / `tags` must be values from `picklists.json`
(`Primary_Solutions__c`, `Product_Tags__c`) — use `;` for multi-select.

```bash
python3 "$H/se_events.py" create --context "$S/context.json" --plan "$S/plan.json" --dry-run   # always first
python3 "$H/se_events.py" create --context "$S/context.json" --plan "$S/plan.json"             # unless --dry-run
```

`create` validates every picklist value and refuses the whole plan on any bad
value. It then writes **one** record, reads it back (record type, account, FTS
number), and only then creates the rest. It finishes with a count query.
Results land in `$S/results.json`.

### 5. Report

Lead with the outcome in one sentence ("Created N SE Events for <window>;
Salesforce had M before."). Then:

1. **Created** — table grouped by account: date, type, subject (short).
2. **Held for your call** — calendar-only / tentative, one line each, with why.
3. **Off-list** — accounts not on your team; offer to log if named.
4. **Already covered** — what was in Salesforce already.
5. **Mapping calls you may want to override** — ambiguous account choices.
6. **Security** — any secrets spotted in sources (location only).

Every number in the report comes from a tool result this run (the count query,
`results.json`) — not from the plan.

## Follow-up edits

The user will often add one-offs ("add X, the meeting three events ago, with
note Y"). Resolve relative references against the sweep data (list the
candidates you counted and which one you picked), look the account up in
Salesforce by name if it is off-list, then create via the same `create`
command with a one-item plan, and read it back.

## Guardrails

- Never write to Salesforce in a way other than creating Events owned by the
  running user. No updates or deletes of existing records.
- Never put tokens, passwords, meeting links/passcodes, or customer
  credentials into descriptions.
- Do not log activity the SE cannot be shown to have done.
- The org-specific schema this relies on (record type `FTSEvents`, fields
  `Meeting_Outcome__c`, `Event_Location__c`, `Primary_Solutions__c`,
  `Product_Tags__c`, `Sales_Process_Stage__c`) is checked at runtime by
  `context`; if any is missing, stop and say which.
