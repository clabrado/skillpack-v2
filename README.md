# skillpack v2

Eighteen Claude Code skills that work as one loop: **give a goal, walk away, get a
verified report back.**

They are deliberately small and they share one idea — *a claim is worth nothing
until something on disk backs it up.* Each skill re-checks its facts before it
speaks, marks what it verified apart from what it assumed, and says "I don't
know" rather than filling a gap with a plausible sentence.

| Skill | What it does |
|---|---|
| **`/asap [goal]`** | Takes the "next steps" from the last answer (or the goal you name) and drives them to done: `/standup` the goal, `/turbo` any fixes, an adversarial QA pass by a fresh agent, then the plain-English readout. |
| **`/give`** | Collects the decisions that are genuinely yours (open forks, blocked items, anything needing your password), filters out what is not, and puts each to you in plan mode with options, a recommendation and the do-nothing default. Read-only. |
| **`/check5 <watch list>`** | Watches in-flight work every 5 minutes and stays quiet unless something really changed: one line per quiet tick, a real report only on a real change. Re-arms itself until the work is done. |
| **`/fixfail [failure]`** | Turns a recurring failure into a fixed process: finds the core failure class from artifacts, makes the fix a goal, runs it on a subagent through `/asap`, has a separate reviewer approve, then merges. Loop-guarded. |
| **`/elearn [--mode …]`** | Learns from your own Claude Code session history and proposes changes to your setup (skills, rules, hooks), with every claim traced to a session. Python collector, read-only until you approve. |
| **`/keep-awake [hours\|status\|stop]`** | Holds the Mac awake and unlocked for N hours (default 8) and restores the lock setting when it ends. macOS only. |
| **`/turbo <goal>`** | Sets the goal as a standing directive and works it autonomously — analyse, build, verify, repeat — until every part is genuinely done. For open-ended building. |
| **`/standup <goal>`** | Same persistence, different rhythm: a fixed **assess → triage → configure → analyze** cycle each pass. For standing something *up* — a service, a box, a pipeline. |
| **`/steer [notes] [--status\|--stop]`** | Hands the running session to an autonomous supervisor that watches its event stream, answers questions it raises, and pulls it back when the work drifts — so you can walk away *mid-task*, not only at the start. |
| **`/readout [topic]`** | Six questions, plain English, every claim re-checked this turn. Status, not a log dump. |
| **`/eclaude [dir] [--name N]`** | Opens a fresh session in its own window — own context, own terminal, independently watchable. Starts in the current directory and on the current config dir unless told otherwise. |
| **`/sid`** | Prints this session's id and where its transcript lives, so you can attach to it from outside. |
| **`/drive <sid\|name> <text>`** | Types into an interactive program the shell tool cannot reach — a live prompt, an installer, a pager, a password prompt. |
| **`/ad-qa [target]`** | **End any prompt or command with `/ad-qa`** and it QAs what that work just produced; or give it a target (file, URL, pasted text). Adversarial QA of any deliverable — answer, PDF, deck, sheet, code, email — against the original ask and every source. An independent Opus reviewer recomputes numbers, checks quotes verbatim, and traces claims; each finding is re-verified before it is reported. `--fix` writes a versioned, re-rendered copy. |
| **`/dt-spend-eval <tenant>`** | For Dynatrace DPS customers: explains why a tenant spends what it spends and where to save. Prices every billing event at DPS list, finds new cost lines, spikes and weekly patterns, breaks the top costs down by host, synthetic monitor, metric key, query user and RUM app, and sorts Full-Stack hosts into move-to-Infrastructure vs keep. A second agent re-runs the queries to disprove findings before the Markdown or HTML report is written. Needs `dtctl`; see [`skills/dt-spend-eval/README.md`](skills/dt-spend-eval/README.md). |
| **`/se-notes [lookback]`** | For Solutions Engineers: sweeps Outlook mail + calendar, Gong and Slack for every customer support activity and demo in the window, diffs against Salesforce, creates the missing SE Events (validated against the org's picklists, first record read back before the rest), and holds calendar-only items for your approval. Needs the `sf` CLI plus M365 and Slack MCPs; see [`skills/se-notes/se-notes.md`](skills/se-notes/se-notes.md). |
| **`/intel <call…>`** | For Solutions Engineers: turns a customer call (Krisp link, Gong call, transcript, email thread, or a Slack DM that contains them) into an 8–12 page Dynatrace-branded PDF debrief. One Opus agent per call checks it against Salesforce, Power BI, Gong, M365, Slack, product docs and the web; a fresh reviewer attacks the draft until no confirmed defect is left. Bottom line, talking points, standard and inverted analysis, triangulation table, next-meeting and POC angle, actions. See [`skills/intel/SKILL.md`](skills/intel/SKILL.md). |
| **`/solution <source> --account --target`** | For Solutions Engineers: a cited, customer-verifiable design for observing a third-party product with Dynatrace (extension, OTel/log export, API polling, synthetic), usually to displace a competitor. Fans out ~10 Sonnet researchers (one per link plus vendor API, export paths, UX, Dynatrace product truth, account intel), merges their findings into a knowledge graph, then an Opus author writes the PDF with ASCII flow diagrams and a docs appendix. One final adversarial QA pass. **Needs `/intel` installed** (shared build pipeline). |

`/steer` is what completes the set: `/turbo` and `/standup` hold a goal, and
`/steer` notices when the work stops serving it.

**The steerer runs on Claude.** No other model tool is required, and none is
assumed — the default engine is `claude -p` pinned to Opus, with no
configuration at all. Grok and other command-line models are opt-in
alternatives; if your environment does not permit them, leave the settings
unset and everything works.

`/steer`, `/eclaude` and `/drive` need the supervisor in [`latch/`](latch/)
running. `/turbo`, `/standup`, `/readout`, `/sid`, `/asap`, `/give`, `/check5`, `/fixfail`, `/elearn`, `/keep-awake`, `/ad-qa`, `/se-notes`, `/dt-spend-eval`, `/intel` and `/solution` do not.

`/turbo` and `/standup` both finish by printing a `/readout` and sending the
same text to your phone.

## Usage and options

Every skill also triggers on plain English (the phrases are in each `SKILL.md`).
Arguments in `<>` are required, `[]` optional.

| Command | Options |
|---|---|
| `/turbo <goal>` | Goal in plain words. Runs until done, then prints a `/readout` and texts it if `SKILLPACK_NOTIFY_TO` is set. |
| `/standup <goal>` | Same as `/turbo`, using the assess → triage → configure → analyze cycle. |
| `/asap [goal]` | No goal = the "next steps" from the last answer. |
| `/readout [focus]` | Optional session / ticket / epic to focus on; default is everything in scope. |
| `/give` | No arguments. Read-only. |
| `/check5 [watch list]` | What to watch and what counts as a real change. Empty = builds the list from the work in flight. Re-arms every 300 s until the work is done. |
| `/fixfail [failure]` | Empty = the most recent failure in this session. |
| `/ad-qa [target]` | Two forms. **Closing step (main use):** `<any prompt or command>, then /ad-qa`, or `/ad-qa` right after it, QAs what that work produced. **Named target:** `/ad-qa <file \| URL>`. `--fix` apply confirmed fixes to a versioned copy and re-render · `--deep` three parallel reviewers · `--sources a,b` extra ground truth · `--focus numbers\|quotes\|claims\|ask\|render\|security` · `--strict` also report plausible findings. |
| `/dt-spend-eval <tenant> [<tenant> …]` | Tenant = `https://abc12345.apps.dynatrace.com`, `abc12345`, or a dtctl context; repeat for a multi-tenant roll-up. `format=md\|html` (default md) · `since=` / `until=YYYY-MM-DD` (default ~4 months back → yesterday) · `account="<name>"` adds PowerBI commit/consumption context · `out=<dir>` (default current dir) · `-clean` replace hostnames, emails, tenant and entity IDs with placeholders. Read-only; dtctl runs strictly serially. |
| `/se-notes [lookback]` | `7d` (default), `2w`, `30d`, or `YYYY-MM-DD:YYYY-MM-DD` (`today` allowed). `--dry-run` plan and validate only · `--all` also create held (calendar-only) items. Org from `$SE_NOTES_SF_ORG` or the `sf` default org. |
| `/intel <source> [<source> …]` | Source = Krisp share link, Gong call, `.eml`/`.txt`/`.vtt`/`.docx`, Slack permalink, "my DM with <name>", or pasted text; one PDF per meeting. `--out <dir>` (default current dir) · `--send-to <slack user>` DM a 2-line summary + attach the PDF · `-clean` sanitize names and hosts for external sharing. Salesforce org from `$INTEL_SF_ORG` or the `sf` default org. |
| `/solution <source> --account <name> --target <product>` | Source = Slack DM/thread, URLs, file or paste. `--competitor <name>` · `--goal "..."` · `--meeting <date>` · `--out <dir>` · `--send-to <slack user>` one message with text + PDF · `-clean`. |
| `/elearn` | `--mode step\|auto\|report` · scope `--days N`, `--since-last`, or `--limit N` · `--per-trace` one reviewer per session · `--include-headless` · `--cwd PATH` · `--focus TEXT` · `--resume`. Bare `/elearn` prices the run and asks mode + scope once. |
| `/keep-awake [hours]` | `/keep-awake 10`, `/keep-awake 1.5` (default 8) · `status` · `stop` · `attach [idleTime]` adopts an orphaned hold. macOS only. |
| `/sid` | No arguments. Prints session id, transcript path, web link, PID, scratchpad. |
| `/eclaude [dir]` | Default dir = current directory. `--name NAME` · `--fork default\|NAME\|PATH` (`NAME` → `~/.claude-NAME`; default inherits `CLAUDE_CONFIG_DIR`) · `--no-latch` not watchable · `--dry-run` print the command only. |
| `/steer [notes]` | Extra goal notes for the steerer. `--status` is this session steered? · `--stop` detach the steerer. Needs latch. |
| `/drive <sid\|name> <text>` | `<sid\|name> --keys enter,y` press keys (`enter esc tab space up down ctrl-c y n q …`) · `--list` targets · `<sid\|name> --interrupt`. Needs latch. |

**Updating an existing install.** `install.sh` never overwrites a skill that
already exists, so after a `git pull` copy the skills over yourself:

```bash
git pull && for s in skills/*/; do rsync -a --exclude __pycache__ "$s" ~/.claude/skills/$(basename "$s")/; done
```

## Which of these run where

Measured, not assumed. Latch's supervisor imports `termios`, `tty` and `fcntl`
— the Unix terminal interface — so it cannot run on Windows, and everything
that depends on it inherits that.

| Skill | macOS / Linux | Windows |
|---|---|---|
| `/turbo` | yes | yes |
| `/standup` | yes | yes |
| `/readout` | yes | yes |
| `/asap` | yes | yes |
| `/give` | yes | yes |
| `/check5` | yes | yes |
| `/fixfail` | yes | yes |
| `/elearn` | yes | not tested |
| `/keep-awake` | yes (macOS only) | no |
| `/sid` | yes | yes (`sid.ps1`) |
| `/ad-qa` | yes | yes (page renders need `pdftoppm`; docx/pptx renders need LibreOffice) |
| `/dt-spend-eval` | yes | not tested (needs `dtctl` + Python 3.9+) |
| `/intel`, `/solution` | yes (needs Chrome, Python + PyMuPDF, `pdftotext`, Node; set `CHROME=` on Linux) | not installed by `install.ps1` |
| `/eclaude` | yes, watchable | yes, **not** watchable |
| `/steer` | yes | **no** — needs latch ([what a port takes](docs/WINDOWS-STEER.md)) |
| `/drive` | yes | **no** — needs latch |

The four that hold and report on a goal — `/turbo`, `/standup`, `/readout`,
`/sid` — are the core of the pack and work everywhere. What Windows loses is
the ability to reach into a *running* session from another window.

`/eclaude` still opens a fresh session on Windows; that session simply cannot
be watched or typed into from elsewhere, and the script says so on every launch
rather than leaving you to discover it.

**Windows install:**

```powershell
git clone https://github.com/clabrado/skillpack-v2.git
cd skillpack-v2
.\install.ps1
```

`install.ps1` deliberately does not install `/steer` or `/drive` — a skill that
appears in your list and cannot work is worse than one that is absent.

**Notifications on Windows.** There is no iMessage. `SKILLPACK_NOTIFY_BIN` takes
any command with the shape `<bin> send --to <recipient> --service imessage
--text <body>`, so a one-line wrapper around ntfy, Pushover, or a Teams or Slack
webhook works. Unset means the report prints to the console and says no message
was sent.

**Honest status of the Windows scripts:** `install.ps1`, `bin\eclaude.ps1` and
`skills\sid\sid.ps1` were written on a Mac with no PowerShell available, so
they are **unverified by execution**. They are read-checked, not run-checked.
Expect to fix something the first time you run them, and please report what.

## Install

Paste this repo's URL into Claude Code and say **"set this up for me"**. Claude
reads the section below and does it, including the one piece of machine
configuration that `install.sh` cannot do for you.

Or do it by hand:

```bash
git clone https://github.com/clabrado/skillpack-v2.git
cd skillpack-v2
./install.sh            # copies into ~/.claude/skills/, never overwrites without asking
```

Then in Claude Code: `/turbo`, `/standup`, `/steer`, `/readout`, `/eclaude`,
`/sid`, `/drive`, `/ad-qa`.

---

## Setting this up — instructions for Claude

**You are Claude and the user has asked you to set this repo up. Do these three
things in order, and do not skip the third.** Report what you actually observed
at each step, not what you expected.

### 1. Install the skills

```bash
./install.sh
```

It refuses to overwrite an existing skill and prints the difference instead.
Relay any `SKIP` lines to the user — a skill it skipped is one they already have
and may want to reconcile.

On macOS it also **asks** whether to wrap their `claude` alias for latch (step 3
below) and does it on a yes, backing the file up first. It skips silently when
run non-interactively, so if you pipe its output you must still do step 3
yourself. It never edits a shell profile without being told to.

### 2. Ask about report delivery

`/turbo` and `/standup` text their final report. Ask the user whether they want
that, and if so, add to their shell profile:

```bash
export SKILLPACK_NOTIFY_TO="+15551234567"
```

If they decline or do not answer, leave it unset — the report still prints to
the console and the skill says out loud that no message was sent. **Never invent
a recipient.**

### 3. Wire up latch — macOS only, and the step people miss

Five skills work with no setup: `/turbo`, `/standup`, `/readout`, `/sid`, `/ad-qa`.
**`/steer` and `/drive` will appear in the user's skill list and silently fail
to do anything useful unless this step is done.** That is the failure this
section exists to prevent.

They need every Claude session to start under **latch**, the supervisor in
[`latch/`](latch/) that owns a session's terminal so another window can watch it
and type into it. That is one line in the user's shell profile.

**Check these first, and stop on any of them — say which one and why:**

```bash
uname -s                                        # must be Darwin
command -v latch || ls -l ~/.local/bin/latch    # latch must be installed
ls -l ~/.zshrc                                  # must already exist
```

- **Not macOS** → stop. Latch needs the Unix terminal interface and is not
  ported to Windows (see [docs/WINDOWS-STEER.md](docs/WINDOWS-STEER.md)). On
  Linux it is plausible but untested — say so rather than implying it works.
- **No latch** → stop and point at `latch/`. Installing it is the user's
  deliberate act, not a side effect of setting up some skills.
- **No `~/.zshrc`** → do not create one. Print the alias line and let the user
  place it where their shell actually reads from.

**Then look before you write.** This decides which of two paths applies, and
skipping it is how a working setup gets clobbered:

```bash
grep -n "alias claude=" ~/.zshrc || echo "ABSENT: no claude alias"
```

Read that output. There are exactly three cases (note there is no
`latch alias-state` command — `alias-on` and `alias-off` are the only alias
subcommands, and each prints the resulting state):

| What the grep shows | Do this |
|---|---|
| A line containing `latch run --` | Already wrapped. Say so and change nothing. |
| A line **without** `latch run --` | `latch alias-on` — it swaps that line in place and writes its own backup. |
| `ABSENT` | Add the line yourself, below. **`latch alias-on` does not help here** — it only rewrites an alias that already exists and returns `claude_alias_not_found` otherwise. |

**When absent**, resolve the real binary paths rather than hardcoding them
(`claude-stable` is a pinned build and wins when present; plain `claude` is the
normal name), back up, then append — never rewrite the file whole:

```bash
cp ~/.zshrc ~/.zshrc.bak-latch-$(date +%s)
printf "\nalias claude='%s run -- %s --dangerously-skip-permissions'\n" \
  "$(command -v latch)" "$(command -v claude-stable || command -v claude)" >> ~/.zshrc
grep -n "alias claude=" ~/.zshrc    # confirm it is there and contains: latch run --
```

Tell the user the backup filename.

**Say what the flag means, in one sentence.** `--dangerously-skip-permissions`
lets a session act without stopping to ask each time. It is what makes an
unattended supervised run possible, and it is a real reduction in prompting.
Do not add it silently — and do not drop it silently either, because a
supervisor watching a session that pauses for permission at every step is not
much of a supervisor. If the user prefers, use the same line without the flag;
everything still works, the session just asks first.

**Verify it for real.** The alias does not apply to any shell already open, and
a line sitting in a file proves nothing:

1. Have the user open a **new terminal window** and run `claude`.
2. From a **different** window, run `latch ls`. The new session must appear with
   an id.
3. Run `latch inject <sid> "hello"` and confirm the text lands in the other
   window.

**That listing is the proof.** If the session does not appear, the alias did not
take — check they opened a genuinely new window, then re-read `~/.zshrc`. Do not
report success on the strength of having written the line.

**To undo:** `latch alias-off`. Leave the `.zshrc.bak-latch-*` backups alone.

`install.sh` refuses to clobber. If a skill of the same name already exists it
stops and shows you the difference; move your copy aside yourself.

## Configure the phone delivery

`/turbo` and `/standup` text you their final report. Nothing is hardcoded — set
two variables in your shell profile:

```bash
export SKILLPACK_NOTIFY_TO="+15551234567"                 # your number
export SKILLPACK_NOTIFY_BIN="/opt/homebrew/bin/imsg"      # optional; this is the default
```

**If `SKILLPACK_NOTIFY_TO` is unset the report still prints to the console**, and
the skill says out loud that no message went out. It never guesses a recipient
and never quietly drops the delivery.

The sender is [`imsg`](https://github.com/steveyackey/imsg) or any command with
the same shape: `<bin> send --to <recipient> --service imessage --text <body>`.
On a non-Mac, point `SKILLPACK_NOTIFY_BIN` at your own one-line wrapper around
whatever you use — ntfy, Pushover, a Slack webhook. Only that argument shape
matters.

## `/sid`, and attaching to a running session

`/sid` on its own needs nothing installed. It reads `CLAUDE_CODE_SESSION_ID`,
which Claude Code exports into every shell it spawns, and finds the matching
transcript under `~/.claude/projects/`. It never guesses from "newest file" —
with several sessions open, modification time is not an identifier.

That gets you the id and the transcript path, which is enough to *read* a
session while it runs.

**To also send input into a running session from outside it**, the session has
to be launched under something that owns its terminal. That tool is included in
this repo, under [`latch/`](latch/) — a terminal supervisor that holds the
session's pseudo-terminal, streams its events, and accepts typed input from
another window.

Wrap your agent binary in a shell alias so every session is attachable by
default:

```bash
alias claude='latch run -- claude-stable --dangerously-skip-permissions'
alias grok='latch run -- grok'
```

Then from anywhere:

```bash
latch ls                       # every live session: id, name, cwd, pid
latch inject <sid> "<text>"    # type into that session
latch attach <sid>             # watch it
```

**It is optional.** Without it `/sid`, `/turbo`, `/standup` and `/readout` all
work — you simply cannot type into a session from another window. Nothing in the
four skills calls `latch` directly.

Latch sends notifications the same way the skills do, and by the same rule:

```bash
export LATCH_NOTIFY_TO="+15551234567"                 # unset = notifications skipped, and said to be
export LATCH_NOTIFY_BIN="/opt/homebrew/bin/imsg"      # optional; this is the default
export LATCH_NOTIFY=0                                 # suppress entirely
```

Note `--dangerously-skip-permissions` in that alias: it lets a session act
without stopping to ask. It suits an unattended run you are supervising from
outside; decide for yourself whether it suits yours.

## What these skills assume about you

They were written for someone who would rather be told "the test didn't run" than
be shown a green check that means nothing. Concretely, each one:

- **re-derives before reporting** — runs the command again rather than trusting
  what it said earlier in the same conversation;
- **separates verified from assumed**, and says which is which;
- **omits what it did not measure** instead of writing a zero;
- **stops when it is genuinely blocked**, tells you the specific blocker, and
  waits — rather than pushing through and reporting success.

`/turbo` and `/standup` hold their goal across a long session and will not ask
"should I continue?" once you have set it. That is the point of them. It also
means you should scope the goal deliberately before you walk away.

## Running latch's tests

```bash
cd latch && LATCH_NOTIFY=0 PYTHONPATH=. python3 -m pytest test/ -q
```

116 pass. One — `test_real_machine_config_is_hardened` — asserts a setting in
*your own* `~/.grok/config.toml` rather than anything in this repo, and will
fail on any machine that has not disabled Grok's codebase upload. It is a
standing check on its author's machine, not a test of this code. Either set
`[harness] disable_codebase_upload = true` in that file, or ignore it.

## Licence

MIT — see [LICENSE](LICENSE).
