#!/usr/bin/env python3
"""Read or update <claude home>/elearn/state.json for the /elearn skill, and do its filesystem work.

  state.py get
  state.py set --run-dir DIR --status collected|running|report_ready|curating|done [--mode M] [--scope S] [--note TEXT]
  state.py clear
  state.py plan --run-dir DIR [--batch 10] [--fan 10]   assign every mapper its session files and note path (plan.json)
  state.py reduce-round --run-dir DIR                   assign the next reduce round from the notes that exist, or name the synthesis
  state.py check --run-dir DIR --phase map|reduce|verify|report   which assigned files exist (non-empty) and which slots are lost
  state.py wait --run-dir DIR [--timeout-min 9]         block until report.md + actions.json exist (exit 0); 2 at the deadline;
                                                        3 report stalled; 4 no file changed under the run dir for --phase-stall-min
  state.py backup --run-name NAME PATH                  copy a file to elearn/trash/NAME/originals/ before its first edit
  state.py trash --run-name NAME PATH [PATH ...]        move a skill dir, command, agent, or workflow file into elearn/trash/NAME/
  state.py mcp-trash --run-name NAME --server S --file settings|claude-json [--project P]
                                                        move one mcpServers entry into elearn/trash/NAME/mcp-S.json (owner-only),
                                                        then remove the key; prints names only, never values
  state.py restrict PATH [PATH ...]                     owner-only permissions
  state.py decide --run-dir DIR --id A3 --kind skill --action delete --target NAME --path P --decision applied|rejected|deferred [--undo P]

`get` prints the state as JSON (plus `python`, the interpreter running this file, and `claude_home`)
and exits 3 when a run is pending (status other than done). All writes merge into the existing file.
Nothing here deletes a file: retirement is a move into the trash directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import stat
import sys
import time

STATUSES = ("collected", "running", "report_ready", "curating", "done")
VERIFY_FILES = ("phrases.md", "stale.md", "deletes.md")
MAX_REDUCE_ROUNDS = 8


def state_path(claude_home: str) -> str:
    return os.path.join(claude_home, "elearn", "state.json")


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def present(path: str) -> bool:
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def pad4(n: int) -> str:
    return f"{n:04d}"


def single_component(name: str) -> bool:
    return name not in ("", ".", "..") and os.path.basename(name) == name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--claude-json", default=None, help="path of .claude.json (default: <parent of claude home>/.claude.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("get")
    s = sub.add_parser("set")
    s.add_argument("--run-dir", required=True)
    s.add_argument("--status", required=True, choices=STATUSES)
    s.add_argument("--mode")
    s.add_argument("--scope")
    s.add_argument("--note")
    sub.add_parser("clear")
    p = sub.add_parser("plan")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--fan", type=int, default=10)
    rr = sub.add_parser("reduce-round")
    rr.add_argument("--run-dir", required=True)
    c = sub.add_parser("check")
    c.add_argument("--run-dir", required=True)
    c.add_argument("--phase", required=True, choices=("map", "reduce", "verify", "report"))
    b = sub.add_parser("backup")
    b.add_argument("--run-name", required=True)
    b.add_argument("path")
    t = sub.add_parser("trash")
    t.add_argument("--run-name", required=True)
    t.add_argument("paths", nargs="+")
    mt = sub.add_parser("mcp-trash")
    mt.add_argument("--run-name", required=True)
    mt.add_argument("--server", required=True)
    mt.add_argument("--file", required=True, choices=("settings", "claude-json"))
    mt.add_argument("--project", default=None, help="project path key under .claude.json projects (local-scope server)")
    r = sub.add_parser("restrict")
    r.add_argument("paths", nargs="+")
    d = sub.add_parser("decide")
    for name in ("--run-dir", "--id", "--kind", "--action", "--target", "--path"):
        d.add_argument(name, required=True)
    d.add_argument("--decision", required=True, choices=("applied", "rejected", "deferred"))
    d.add_argument("--undo", default=None)
    w = sub.add_parser("wait")
    w.add_argument("--run-dir", required=True)
    w.add_argument("--timeout-min", type=float, default=9, help="default 9: fits inside one 10-minute foreground shell call")
    w.add_argument("--phase-stall-min", type=int, default=60)
    w.add_argument("--report-stall-min", type=int, default=45)
    args = ap.parse_args()

    claude_home = os.path.abspath(os.path.expanduser(args.claude_home))
    claude_json = os.path.abspath(os.path.expanduser(args.claude_json)) if args.claude_json else os.path.join(os.path.dirname(claude_home), ".claude.json")
    path = state_path(claude_home)
    trash_root = os.path.join(claude_home, "elearn", "trash")

    if args.cmd == "plan":
        run = os.path.abspath(args.run_dir)
        try:
            with open(os.path.join(run, "manifest.json"), encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as e:
            print(json.dumps({"error": f"manifest.json unreadable: {e}"}))
            return 1
        count = int(manifest.get("sessions_kept") or 0)
        if count <= 0 or args.batch < 1 or args.fan < 2:
            print(json.dumps({"error": "nothing to plan: sessions_kept is 0, or batch < 1, or fan < 2"}))
            return 1
        names = sorted(os.listdir(os.path.join(run, "sessions")))
        mappers = []
        for m, first in enumerate(range(0, count, args.batch)):
            last = min(first + args.batch, count) - 1
            files = [os.path.join(run, "sessions", n) for n in names if n[:4].isdigit() and first <= int(n[:4]) <= last]
            mappers.append({"label": f"map:{pad4(first)}-{pad4(last)}", "number": m + 1, "first": pad4(first), "last": pad4(last),
                            "files": files, "note": os.path.join(run, "map", f"{pad4(first)}-{pad4(last)}.md")})
        reducers, level = 0, len(mappers)
        while True:
            groups = -(-level // args.fan)
            reducers += groups
            level = groups
            if groups <= 1:
                break
        plan = {"run_dir": run, "count": count, "batch": args.batch, "fan": args.fan, "mappers": mappers, "reduce_rounds": [],
                "verify": {k[:-3]: os.path.join(run, "verify", k) for k in VERIFY_FILES},
                "report": {"report": os.path.join(run, "report.md"), "actions": os.path.join(run, "actions.json")},
                "agents": {"map": len(mappers), "reduce": reducers, "verify": 3, "report": 1, "total": len(mappers) + reducers + 4}}
        with open(os.path.join(run, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        print(json.dumps({"plan": os.path.join(run, "plan.json"), "agents": plan["agents"]}))
        return 0

    if args.cmd in ("reduce-round", "check"):
        run = os.path.abspath(args.run_dir)
        plan_file = os.path.join(run, "plan.json")
        try:
            with open(plan_file, encoding="utf-8") as f:
                plan = json.load(f)
        except (OSError, ValueError):
            print(json.dumps({"error": "plan.json missing: run `state.py plan` first"}))
            return 1
        if args.cmd == "check":
            if args.phase == "map":
                slots = [(m["label"], m["note"]) for m in plan["mappers"]]
            elif args.phase == "reduce":
                rounds = plan.get("reduce_rounds") or []
                slots = [(g["label"], g["out"]) for g in rounds[-1]["groups"]] if rounds else []
            elif args.phase == "verify":
                slots = [("verify:" + k, v) for k, v in plan["verify"].items()]
            else:
                slots = [("report:" + k, v) for k, v in plan["report"].items()]
            ok = [p for _, p in slots if present(p)]
            lost = [label for label, p in slots if not present(p)]
            print(json.dumps({"phase": args.phase, "present": ok, "lost": lost, "planned": len(slots)}))
            return 0 if slots and not lost else 1
        # reduce-round: inputs are the notes that exist from the previous level; paths are assigned here, never by an agent
        rounds = plan.get("reduce_rounds") or []
        if rounds:
            inputs = [g["out"] for g in rounds[-1]["groups"] if present(g["out"])]
        else:
            inputs = [m["note"] for m in plan["mappers"] if present(m["note"])]
        if not inputs:
            print(json.dumps({"error": "no input notes exist for the next round; every slot of the previous level was lost"}))
            return 1
        if rounds and (len(inputs) == 1 or len(rounds) >= MAX_REDUCE_ROUNDS):
            plan["synthesis"] = inputs[0]
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=1)
            print(json.dumps({"done": True, "synthesis": inputs[0], "rounds": len(rounds),
                              "note": "more than one note left after the round cap" if len(inputs) > 1 else ""}))
            return 0
        n = len(rounds) + 1
        fan = plan["fan"]
        groups = []
        for g, start in enumerate(range(0, len(inputs), fan)):
            groups.append({"label": f"reduce:r{n}-{pad4(g)}", "number": g + 1, "inputs": inputs[start:start + fan],
                           "out": os.path.join(run, "reduce", f"r{n}-{pad4(g)}.md")})
        rounds.append({"round": n, "final": len(inputs) <= fan, "groups": groups})
        plan["reduce_rounds"] = rounds
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        print(json.dumps({"done": False, "round": n, "final": len(inputs) <= fan, "groups": groups}, indent=1))
        return 0

    if args.cmd == "backup":
        if not single_component(args.run_name):
            print(json.dumps({"error": "run-name must be a single path component", "run_name": args.run_name}))
            return 2
        src = os.path.abspath(os.path.expanduser(args.path))
        if not os.path.isfile(src):
            print(json.dumps({"error": "missing", "path": src}))
            return 1
        name = os.path.basename(os.path.dirname(src)) if os.path.basename(src) == "SKILL.md" else os.path.splitext(os.path.basename(src))[0]
        dest_dir = os.path.join(trash_root, args.run_name, "originals")
        dest = os.path.join(dest_dir, name + ".md")
        if os.path.exists(dest):
            # the first copy in a run is the undo; a later edit must not overwrite it
            print(json.dumps({"kept_existing": dest}))
            return 0
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src, dest)
        print(json.dumps({"backup": dest, "of": src}))
        return 0

    if args.cmd == "trash":
        # the run name is one directory component under elearn/trash; anything else lands somewhere unintended
        if not single_component(args.run_name):
            print(json.dumps({"error": "run-name must be a single path component", "run_name": args.run_name}))
            return 2
        dest_dir = os.path.join(trash_root, args.run_name)
        # only these shapes are ever retired by the skill: a skills/<name> directory, a commands/*.md or agents/*.md
        # file, or a workflows/*.js file, under the claude home or a project .claude directory.
        # Sessions, config, symlinks, and roots never move.
        home_real = os.path.realpath(claude_home)
        for src in args.paths:
            src = os.path.abspath(os.path.expanduser(src.rstrip("\\/")))
            if not os.path.lexists(src):
                print(json.dumps({"error": "missing", "path": src}))
                return 1
            if os.path.islink(src):
                print(json.dumps({"error": "refusing: a symlink points into another tree; its owner repo is the place to change it", "path": src}))
                return 2
            parent = os.path.dirname(os.path.realpath(src))
            kind = os.path.basename(parent)
            grand = os.path.dirname(parent)
            in_scope = grand == home_real or grand.endswith(os.sep + ".claude")
            ok = in_scope and (
                (kind == "skills" and os.path.isdir(src))
                or (kind in ("commands", "agents") and os.path.isfile(src) and src.endswith(".md"))
                or (kind == "workflows" and os.path.isfile(src) and src.endswith((".js", ".mjs")))
            )
            if not ok:
                print(json.dumps({"error": "refusing: only a skills/<name> directory, a commands/*.md or agents/*.md file, or a workflows/*.js file under the claude home or a project .claude directory can be trashed", "path": src}))
                return 2
        os.makedirs(dest_dir, exist_ok=True)
        moved = []
        for src in args.paths:
            src = os.path.abspath(os.path.expanduser(src.rstrip("\\/")))
            dest = os.path.join(dest_dir, os.path.basename(src))
            if os.path.exists(dest):
                dest += "-" + dt.datetime.now(dt.timezone.utc).strftime("%H%M%S")
            shutil.move(src, dest)
            moved.append({"from": src, "to": dest})
        print(json.dumps({"moved": moved}, indent=1))
        return 0

    if args.cmd == "mcp-trash":
        if not single_component(args.run_name) or not single_component(args.server):
            print(json.dumps({"error": "run-name and server must each be a single path component"}))
            return 2
        cfg = os.path.join(claude_home, "settings.json") if args.file == "settings" else claude_json
        try:
            with open(cfg, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(json.dumps({"error": f"cannot read {cfg}: {type(e).__name__}"}))
            return 1
        holder = data
        if args.project:
            holder = (data.get("projects") or {}).get(args.project)
            if not isinstance(holder, dict):
                print(json.dumps({"error": "no such project key", "project": args.project}))
                return 1
        servers = holder.get("mcpServers")
        if not isinstance(servers, dict) or args.server not in servers:
            print(json.dumps({"error": "no such server", "server": args.server, "file": cfg}))
            return 1
        dest_dir = os.path.join(trash_root, args.run_name)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, f"mcp-{args.server}.json")
        if os.path.exists(dest):
            dest = dest[:-5] + "-" + dt.datetime.now(dt.timezone.utc).strftime("%H%M%S") + ".json"
        # the trash copy is written and restricted BEFORE the key leaves the config
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"file": cfg, "project": args.project, "server": args.server, "config": servers[args.server]}, f, indent=2)
        del servers[args.server]
        tmp = cfg + ".elearn.tmp"
        mode = stat.S_IMODE(os.stat(cfg).st_mode)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.chmod(tmp, mode)
        os.replace(tmp, cfg)
        with open(cfg, encoding="utf-8") as f:
            reread = json.load(f)
        if args.project:
            reread = (reread.get("projects") or {}).get(args.project) or {}
        still = args.server in (reread.get("mcpServers") or {})
        print(json.dumps({"moved_server": args.server, "from": cfg, "to": dest, "removed": not still}))
        return 0 if not still else 1

    if args.cmd == "wait":
        # the subagents report through the parent's turn; blocking here keeps that turn alive until both report files exist.
        # Only the parent records report_ready: a worker writing outside the run dir can hit a permission prompt nobody answers.
        deadline = time.time() + args.timeout_min * 60
        report = os.path.join(args.run_dir, "report.md")
        actions = os.path.join(args.run_dir, "actions.json")
        verify_dir = os.path.join(args.run_dir, "verify")
        last_phase = None
        verify_done_at = None
        last_progress = (newest_mtime(args.run_dir), time.time())
        while time.time() < deadline:
            if present(report) and present(actions):
                mark(path, args.run_dir, "report_ready")
                print(json.dumps({"status": "report_ready", "report": report, "actions": actions}))
                return 0
            phase = next((ph for ph in ("verify", "reduce", "map") if os.path.isdir(os.path.join(args.run_dir, ph)) and os.listdir(os.path.join(args.run_dir, ph))), "collected")
            if phase != last_phase:
                print(json.dumps({"status": "running", "phase": phase, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}), flush=True)
                last_phase = phase
            newest = newest_mtime(args.run_dir)
            if newest > last_progress[0]:
                last_progress = (newest, time.time())
            elif time.time() - last_progress[1] > args.phase_stall_min * 60:
                mark(path, args.run_dir, "running", {"note": f"phase_stalled: no file changed under the run dir for {args.phase_stall_min} min"})
                print(json.dumps({"status": "phase_stalled", "phase": last_phase, "synthesis": latest_synthesis(args.run_dir), "run_dir": args.run_dir}))
                return 4
            verdicts = [f for f in VERIFY_FILES if os.path.isfile(os.path.join(verify_dir, f))]
            if len(verdicts) == 3:
                verify_done_at = verify_done_at or time.time()
                if time.time() - verify_done_at > args.report_stall_min * 60:
                    mark(path, args.run_dir, "running", {"note": f"report_stalled: verifiers finished; no report.md after {args.report_stall_min} min"})
                    print(json.dumps({"status": "report_stalled", "synthesis": latest_synthesis(args.run_dir), "verify_dir": verify_dir, "run_dir": args.run_dir}))
                    return 3
            time.sleep(15)
        print(json.dumps({"status": "timeout", "last_phase": last_phase, "run_dir": args.run_dir}))
        return 2

    if args.cmd == "restrict":
        for p in args.paths:
            try:
                os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        print(json.dumps({"restricted": args.paths}))
        return 0

    if args.cmd == "decide":
        line = {"date": dt.datetime.now(dt.timezone.utc).date().isoformat(), "run_dir": args.run_dir, "id": args.id,
                "kind": args.kind, "action": args.action, "target": args.target, "path": args.path,
                "decision": args.decision, "undo": args.undo}
        dec_path = os.path.join(claude_home, "elearn", "decisions.jsonl")
        os.makedirs(os.path.dirname(dec_path), exist_ok=True)
        with open(dec_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        print(json.dumps(line))
        return 0

    state = load(path)

    if args.cmd == "get":
        pending = state.get("pending") or {}
        # a run whose files exist is report_ready even if nothing recorded it (the parent died before wait returned)
        if pending.get("status") in ("collected", "running") and files_ready(pending.get("run_dir") or ""):
            state = mark(path, pending["run_dir"], "report_ready")
            pending = state["pending"]
        view = dict(state)
        view["python"] = sys.executable
        view["claude_home"] = claude_home
        print(json.dumps(view, indent=1))
        return 3 if pending and pending.get("status") != "done" else 0

    if args.cmd == "clear":
        state.pop("pending", None)
        save(path, state)
        print(json.dumps(state, indent=1))
        return 0

    state = mark(path, args.run_dir, args.status, {k: getattr(args, k) for k in ("mode", "scope", "note")})
    print(json.dumps(state, indent=1))
    return 0


def newest_mtime(run_dir: str) -> float:
    """Latest modification time of any file under the run dir (0 if none) — the run's heartbeat."""
    newest = 0.0
    for root, _dirs, files in os.walk(run_dir):
        for f in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, f)))
            except OSError:
                pass
    return newest


def latest_synthesis(run_dir: str) -> str | None:
    """Newest reducer output; the best available result when the report stage never produced report.md."""
    d = os.path.join(run_dir, "reduce")
    if not os.path.isdir(d):
        return None
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md") and not f.endswith(".dropped.md")]
    return max(files, key=os.path.getmtime) if files else None


def files_ready(run_dir: str) -> bool:
    return bool(run_dir) and present(os.path.join(run_dir, "report.md")) and present(os.path.join(run_dir, "actions.json"))


def mark(path: str, run_dir: str, status: str, extra: dict | None = None) -> dict:
    """Record `status` for `run_dir` as the pending run and save; `done` also stamps last_completed_*."""
    state = load(path)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    pending = state.get("pending") or {}
    if pending.get("run_dir") != run_dir:
        pending = {"run_dir": run_dir, "started_at": now}
    pending["status"] = status
    pending["updated_at"] = now
    pending["report_ready"] = files_ready(run_dir)
    for k, v in (extra or {}).items():
        if v:
            pending[k] = v
    if status == "done":
        state["last_completed_at"] = now
        state["last_completed_dir"] = run_dir
    state["pending"] = pending
    save(path, state)
    return state


if __name__ == "__main__":
    sys.exit(main())
