# skillpack v2

Four Claude Code skills that work as one loop: **give a goal, walk away, get a
verified report back.**

They are deliberately small and they share one idea — *a claim is worth nothing
until something on disk backs it up.* Each skill re-checks its facts before it
speaks, marks what it verified apart from what it assumed, and says "I don't
know" rather than filling a gap with a plausible sentence.

| Skill | What it does |
|---|---|
| **`/turbo <goal>`** | Sets the goal as a standing directive and works it autonomously — analyse, build, verify, repeat — until every part is genuinely done. For open-ended building. |
| **`/standup <goal>`** | Same persistence, different rhythm: a fixed **assess → triage → configure → analyze** cycle each pass. For standing something *up* — a service, a box, a pipeline. |
| **`/readout [topic]`** | Six questions, plain English, every claim re-checked this turn. Status, not a log dump. |
| **`/sid`** | Prints this session's id and where its transcript lives, so you can attach to it from outside. |

`/turbo` and `/standup` both finish by printing a `/readout` and sending the
same text to your phone.

## Install

```bash
git clone https://github.com/clabrado/skillpack-v2.git
cd skillpack-v2
./install.sh            # copies into ~/.claude/skills/, never overwrites without asking
```

Then in Claude Code: `/turbo`, `/standup`, `/readout`, `/sid`.

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
to have been launched under a supervisor that owns its terminal. The setup here
uses [`latch`](https://github.com/anthropics/claude-code) — an in-house wrapper,
not public — via a shell alias, so that every session is attachable by default:

```bash
alias claude='latch run -- claude-stable --dangerously-skip-permissions'
```

The same shape works for other agent CLIs — wrap the binary, keep the name:

```bash
alias grok='latch run -- grok'
```

**This is the only part of the pack with an outside dependency, and it is
optional.** Without it: `/sid` works, `/turbo`, `/standup` and `/readout` all
work — you simply can't type into a session from another window. If you use
`tmux`, `zellij`, or `screen`, wrapping the launch the same way gives you the
same ability with tools you already have. Nothing in the pack calls `latch`
directly.

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

## Licence

MIT — see [LICENSE](LICENSE).
