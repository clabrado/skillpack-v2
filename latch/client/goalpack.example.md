# Goal
In the current working directory (toy project), make the test suite pass.
Work only inside this repo. Prefer the smallest fix.

# Constraints
- Do not push to remote
- Do not modify files outside this repository
- Do not install global packages
- Prefer editing existing files over large refactors

# Definition of done
- `npm test` (or the project's test command) exits 0
- Evidence: tool_result or assistant transcript showing a green test run

# Stop conditions
- blocked: missing network/credentials needed to finish; or goal is impossible without forbidden actions
- No time/steer budget — this runs until done/blocked or you stop it yourself
  (`latch steer --stop <sid>`). Pass --max-minutes/--max-steers on the CLI if you
  want a hard cap for this particular run; there is none by default.
