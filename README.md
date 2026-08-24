# skillpack v2

Seven Claude Code skills that work as one loop: **give a goal, walk away, get a
verified report back.**

They are deliberately small and they share one idea — *a claim is worth nothing
until something on disk backs it up.* Each skill re-checks its facts before it
speaks, marks what it verified apart from what it assumed, and says "I don't
know" rather than filling a gap with a plausible sentence.

| Skill | What it does |
|---|---|
| **`/turbo <goal>`** | Sets the goal as a standing directive and works it autonomously — analyse, build, verify, repeat — until every part is genuinely done. For open-ended building. |
| **`/standup <goal>`** | Same persistence, different rhythm: a fixed **assess → triage → configure → analyze** cycle each pass. For standing something *up* — a service, a box, a pipeline. |
| **`/steer`** | Hands the running session to an autonomous supervisor that watches its event stream, answers questions it raises, and pulls it back when the work drifts — so you can walk away *mid-task*, not only at the start. |
| **`/readout [topic]`** | Six questions, plain English, every claim re-checked this turn. Status, not a log dump. |
| **`/eclaude [dir]`** | Opens a fresh session in its own window — own context, own terminal, independently watchable. |
| **`/sid`** | Prints this session's id and where its transcript lives, so you can attach to it from outside. |
| **`/drive`** | Types into an interactive program the shell tool cannot reach — a live prompt, an installer, a pager, a password prompt. |

`/steer` is what completes the set: `/turbo` and `/standup` hold a goal, and
`/steer` notices when the work stops serving it.

**The steerer runs on Claude.** No other model tool is required, and none is
assumed — the default engine is `claude -p` pinned to Opus, with no
configuration at all. Grok and other command-line models are opt-in
alternatives; if your environment does not permit them, leave the settings
unset and everything works.

`/steer`, `/eclaude` and `/drive` need the supervisor in [`latch/`](latch/)
running. `/turbo`, `/standup`, `/readout` and `/sid` do not.

`/turbo` and `/standup` both finish by printing a `/readout` and sending the
same text to your phone.

## Which of these run where

Measured, not assumed. Latch's supervisor imports `termios`, `tty` and `fcntl`
— the Unix terminal interface — so it cannot run on Windows, and everything
that depends on it inherits that.

| Skill | macOS / Linux | Windows |
|---|---|---|
| `/turbo` | yes | yes |
| `/standup` | yes | yes |
| `/readout` | yes | yes |
| `/sid` | yes | yes (`sid.ps1`) |
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
`/sid`, `/drive`.

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

Four skills work with no setup: `/turbo`, `/standup`, `/readout`, `/sid`.
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
