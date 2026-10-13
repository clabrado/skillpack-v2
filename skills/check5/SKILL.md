---
name: check5
description: >-
  Watch in-flight work every 5 minutes and stay quiet unless something really changed.
  Each tick re-checks the actual artifacts (job journals, service health, maintenance
  windows, temperatures, logs), prints one short line when nothing changed, and reports
  only real changes: a unit passing or failing its check, a job finished or stuck, a
  service down outside a planned window, a thermal stop, anything the user asked to hear
  about. Re-arms itself with ScheduleWakeup (300 s) until the watched work is done, then
  stops. Takes the watch list as its argument. Triggers: "/check5", "check every 5
  minutes", "check every 5 minutes, don't spam", "keep an eye on it every 5 min".
argument-hint: "<what to watch and what counts as a real change>"
---

# /check5 — a 5-minute watch that does not spam

The instruction behind this skill: **"Check every 5 minutes, don't spam."** This skill is
that instruction as a fixed procedure.

## Argument

Everything after `/check5` is the **watch list**: what to check and what counts as a real
change. If it is empty, build the watch list from the work in flight in this conversation
(running jobs, background units, maintenance windows, services the work depends on,
temperatures) and state it once in one line.

Carry forward any standing notes from earlier ticks (for example "maintenance window
started 20:32, flag it if the server is not back by 21:05") by putting them in the next
tick's prompt.

## Each tick

1. **Check the artifacts, not memory.** In ONE tool call where possible:
   - job progress: the run's journal or log line count, or its completion notification;
   - each watched service: a real request (HTTP code and result), not a process list;
   - active units and maintenance windows, and when each window started;
   - temperatures and any new thermal-guard or throttle event;
   - any result file the watch list names.
   Never poll a process table in a loop. Poll the artifact the work produces.
2. **Decide if anything REALLY changed** since the last tick. A real change is:
   - a unit or job passed, failed, finished, or escalated;
   - a result the user asked for landed;
   - a planned downtime ran past its deadline, or a service is down with no planned window;
   - a thermal stop, a guard firing, an error in a log that blocks the work;
   - a decision that only the user can make is now waiting.
   Expected states (a build still running, a planned window in progress, temperatures
   normal) are NOT changes.
3. **Report:**
   - **No real change:** one line only, for example
     `No change: builders running, port 8000 up, 47 / 59 °C.` No tables, no recap.
   - **Real change:** state the change and its evidence in 1-3 short sentences or a short
     list, with the number that matters. If it needs the user, say exactly what is needed.
   - Never message the user about a routine tick. A message goes out only if the watch list
     or the owning skill says so, or the change is a blocker the user must clear.
4. **Re-arm:** call `ScheduleWakeup` with `delaySeconds: 300`, the same
   `/check5 <watch list>` prompt plus any updated standing notes, `noop: true` when nothing
   changed and `false` when something did, and a one-line `reason`.
5. **Stop** when every watched item is done or the user says stop: give one short final
   summary, then call `ScheduleWakeup` with `stop: true`. If a completion notification
   (for example a background job finishing) arrives between ticks, handle it at once — it
   is the real change.

## Rules

- Five minutes means 300 s. Do not shorten it to look busy; do not stretch it.
- Brevity binds what you write, not what you read: read the full result when a unit reports.
- A check that could not run (host unreachable, file missing) is reported as UNMEASURED on
  the first occurrence, never as "no change".
- Session limit: if the context shows a usage or rate limit, do not re-arm at 300 s;
  schedule to the reset time (cap 3600 s) with `noop: true`.
- When this runs inside another skill's loop (for example `/standup`), that skill's goal and
  finish rules still apply; `/check5` only sets the cadence and the reporting bar.
