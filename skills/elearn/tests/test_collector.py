#!/usr/bin/env python3
"""Hermetic test for the /elearn collector. Prints ELEARN_OK and exits 0 only when every check holds.

Builds a temporary claude home (never the real one; HOME is not changed), writes two fixture
sessions, runs collect_sessions.py --claude-home <tmp>, and checks the human-turn filter, the
run directory location, the names-only inventory, and the skill files' required literals.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTOR = os.path.join(SKILL_DIR, "collect_sessions.py")
sys.path.insert(0, SKILL_DIR)
sys.dont_write_bytecode = True  # no __pycache__ in the skill tree
import collect_sessions  # noqa: E402

HUMAN = "always quote the file path before the claim"
STEERER = "You are the sovereign steerer for a live Claude Code session wrapped by LATCH."
# texts that must never reach kept turns: each one is a record the filter has to drop
NEGATIVES = {
    "sidechain": "SIDECHAIN-ONLY-TEXT from a subagent",
    "meta": "META-SKILL-BODY-TEXT injected by the harness",
    "tool_result": "TOOL-RESULT-ONLY-TEXT from a shell",
    "steer_inject": "STEER-INJECT-TEXT typed by latch inject",
    "pasted": "PASTED-ONLY-TEXT that the human did not type",
    "scheduled": "SCHEDULED-LOOP-TEXT fired by a timer",
    "task_notification": "TASK-NOTIFICATION-TEXT from a background job",
}
SECRET_VALUE = "FIXTURE-SECRET-VALUE-9f8e7d6c5b4a"
FORBIDDEN_LITERAL = "learn" + "-traces"  # built at run time so this file does not contain it

failures: list[str] = []


def check(cond: bool, what: str) -> None:
    if not cond:
        failures.append(what)
        print("FAIL: " + what)


def rec(kind: str, sid: str, cwd: str, n: int, **extra) -> dict:
    base = {"type": kind, "uuid": f"u{n:04d}", "parentUuid": f"u{n - 1:04d}" if n else None, "sessionId": sid,
            "timestamp": f"2026-10-0{1 + n % 3}T12:{n:02d}:00.000Z", "cwd": cwd, "gitBranch": "main",
            "version": "2.1.281", "userType": "external", "entrypoint": "cli", "isSidechain": False}
    base.update(extra)
    return base


def user(sid, cwd, n, content, **extra):
    return rec("user", sid, cwd, n, message={"role": "user", "content": content}, **extra)


def write_jsonl(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def build_home(root: str) -> tuple[str, dict]:
    home = os.path.join(root, "claude-home")
    os.makedirs(os.path.join(home, "skills", "fixture-skill"))
    with open(os.path.join(home, "skills", "fixture-skill", "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: fixture-skill\ndescription: a fixture skill\n---\n\n# fixture\n")
    with open(os.path.join(home, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"fixture-mcp": {"command": "run", "env": {"TOKEN": SECRET_VALUE}}},
                   "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo " + SECRET_VALUE}]}]}}, f)
    with open(os.path.join(root, ".claude.json"), "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"fixture-user-mcp": {"headers": {"Authorization": SECRET_VALUE}}},
                   "skillUsage": {"fixture-skill": {"usageCount": 1, "lastUsedAt": 1}}}, f)

    cwd = "/Users/fixture/proj"
    sid1 = "11111111-1111-4111-8111-111111111111"
    skill_base = os.path.join(home, "skills", "fixture-skill")
    s1 = [
        user(sid1, cwd, 0, f"Fix the parser. Please {HUMAN}.", promptSource="typed", turnOrigin="human", promptId="p1"),
        rec("assistant", sid1, cwd, 1, message={"role": "assistant", "model": "claude-fixture", "content": [
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/Users/fixture/proj/src/a.py"}},
            {"type": "tool_use", "id": "t2", "name": "mcp__fixture-mcp__ping", "input": {}}]}),
        user(sid1, cwd, 2, [{"type": "tool_result", "tool_use_id": "t1", "content": NEGATIVES["tool_result"]}],
             toolUseResult={"stdout": NEGATIVES["tool_result"]}),
        user(sid1, cwd, 3, NEGATIVES["sidechain"], isSidechain=True, promptSource="typed"),
        user(sid1, cwd, 4, [{"type": "text", "text": f"Base directory for this skill: {skill_base}\n\n{NEGATIVES['meta']}"}], isMeta=True),
        user(sid1, cwd, 5, "[steerer] " + NEGATIVES["steer_inject"], promptSource="typed", turnOrigin="human"),
        user(sid1, cwd, 6, f'see this <pasted_content id="ab12">{NEGATIVES["pasted"]}</pasted_content id="ab12"> and fix it',
             promptSource="queued", turnOrigin="human"),
        user(sid1, cwd, 7, "<command-message>fixture-skill</command-message>\n<command-name>/fixture-skill</command-name>\n<command-args>run it now</command-args>",
             turnOrigin="human"),
        user(sid1, cwd, 8, "<command-message>check5</command-message>\n<command-name>/check5</command-name>\n<command-args>" + NEGATIVES["scheduled"] + "</command-args>",
             turnOrigin="scheduled"),
        user(sid1, cwd, 9, "<task-notification>" + NEGATIVES["task_notification"] + "</task-notification>",
             promptSource="system", turnOrigin="task_notification"),
        user(sid1, cwd, 10, f"Next time, {HUMAN}, every time.", promptSource="typed", turnOrigin="human", promptId="p2"),
        {"type": "ai-title", "aiTitle": "Fixture parser fix", "sessionId": sid1},
    ]
    write_jsonl(os.path.join(home, "projects", "-Users-fixture-proj", sid1 + ".jsonl"), s1)

    lcwd = "/Users/fixture/latch"
    sid2 = "22222222-2222-4222-8222-222222222222"
    steer_rec = user(sid2, lcwd, 0, STEERER + "\nYou observe structured events.", promptSource="sdk",
                     userType="external", entrypoint="sdk-cli", turnOrigin="sdk", permissionMode="default")
    s2 = [
        steer_rec,
        rec("assistant", sid2, lcwd, 1, entrypoint="sdk-cli", message={"role": "assistant", "model": "claude-fixture", "content": [
            {"type": "text", "text": '{"action": "noop"}'}]}),
        user(sid2, lcwd, 2, STEERER + "\nSecond event batch.", promptSource="sdk", userType="external", entrypoint="sdk-cli",
             turnOrigin="sdk"),
    ]
    write_jsonl(os.path.join(home, "projects", "-Users-fixture-latch", sid2 + ".jsonl"), s2)
    return home, steer_rec


def all_text_under(d: str) -> str:
    out = []
    for root, _dirs, files in os.walk(d):
        for f in files:
            with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                out.append(fh.read())
    return "\n".join(out)


def main() -> int:
    real_home = os.environ.get("HOME", "")
    real_state = os.path.join(os.path.expanduser("~/.claude"), "elearn", "state.json")
    real_state_before = os.path.getmtime(real_state) if os.path.exists(real_state) else None

    with tempfile.TemporaryDirectory(prefix="elearn-test-") as tmp:
        home, steer_rec = build_home(tmp)
        check(not os.path.realpath(home).startswith(os.path.realpath(real_home) + os.sep + ".claude"), "fixture home is not the real claude home")

        # record-level filter: the steerer record alone must not be a human prompt
        kind, _ = collect_sessions.classify_user_record(steer_rec)
        check(kind not in ("prompt", "slash"), f"steerer sdk record classified as human ({kind})")

        r = subprocess.run([sys.executable, COLLECTOR, "--claude-home", home], capture_output=True, text=True, timeout=120)
        check(r.returncode == 0, f"collector exit {r.returncode}: {r.stderr.strip()[-400:]}")
        try:
            last = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            last = {}
            check(False, "collector printed no JSON line")
        run = last.get("run_dir") or ""
        run_real = os.path.realpath(run) if run else ""
        check(bool(run) and os.path.isdir(run), "run_dir exists")
        check(".grok" not in run_real.split(os.sep), f"run dir is not under a .grok tree: {run_real}")
        check(run_real.startswith(os.path.realpath(os.path.join(home, "elearn", "runs")) + os.sep), f"run dir is under <claude home>/elearn/runs: {run_real}")

        sessions_dir = os.path.join(run, "sessions")
        sess = []
        if os.path.isdir(sessions_dir):
            for fn in sorted(os.listdir(sessions_dir)):
                with open(os.path.join(sessions_dir, fn), encoding="utf-8") as f:
                    sess.append(json.load(f))
        turns = [t for s in sess for t in s.get("turns", [])]
        check(len(sess) == 1, f"exactly one session kept (got {len(sess)})")
        check(sum(HUMAN in t for t in turns) == 2, f"both human turns with the sentence are kept (got {sum(HUMAN in t for t in turns)})")
        check(not any(STEERER in t for t in turns), "steerer sentence absent from kept turns")
        for name, text in NEGATIVES.items():
            check(not any(text in t for t in turns), f"{name} text absent from kept turns")
        check(any(t.startswith("/fixture-skill run it now") for t in turns), "the human slash command is a kept turn")
        check(any("see this" in t and "and fix it" in t for t in turns), "text around a pasted block is kept")

        phrases_path = os.path.join(run, "phrases.json")
        phrases = open(phrases_path, encoding="utf-8").read() if os.path.isfile(phrases_path) else ""
        check(bool(phrases), "phrases.json written")
        check("sovereign steerer" not in phrases.lower(), "steerer sentence absent from phrases.json")

        try:
            manifest = json.load(open(os.path.join(run, "manifest.json"), encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        check(manifest.get("dropped", {}).get("steerer") == 1, f"manifest counts one steerer session dropped ({manifest.get('dropped')})")
        check(manifest.get("disuse_evidence", {}).get("sufficient") is False, "a 1-session run is a narrow window")

        try:
            surfaces = json.load(open(os.path.join(run, "surfaces.json"), encoding="utf-8"))
            usage = json.load(open(os.path.join(run, "usage.json"), encoding="utf-8"))
        except (OSError, ValueError):
            surfaces, usage = {}, {}
        mcp = {m["name"] for m in surfaces.get("mcp_servers", [])}
        check({"fixture-mcp", "fixture-user-mcp"} <= mcp, f"MCP names inventoried from settings.json and .claude.json ({sorted(mcp)})")
        check(SECRET_VALUE not in all_text_under(run), "no config value copied into the run directory")
        skill_use = next((i for i in usage.get("items", []) if i.get("kind") == "skill" and i.get("name") == "fixture-skill"), {})
        check(skill_use.get("count", 0) >= 2, f"fixture-skill use counted from the meta body and the slash command ({skill_use.get('count')})")
        mcp_use = next((i for i in usage.get("items", []) if i.get("kind") == "mcp" and i.get("name") == "fixture-mcp"), {})
        check(mcp_use.get("count") == 1, f"fixture-mcp tool call counted ({mcp_use.get('count')})")

        e = subprocess.run([sys.executable, COLLECTOR, "--claude-home", home, "--estimate"], capture_output=True, text=True, timeout=120)
        try:
            est = json.loads(e.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            est = {}
        check(e.returncode == 0 and est.get("windows", {}).get("all", {}).get("sessions") == 1, "estimate prices one session")
        check(os.path.realpath(est.get("out", "")).startswith(os.path.realpath(home) + os.sep), "estimate writes under the fixture home")

    real_state_after = os.path.getmtime(real_state) if os.path.exists(real_state) else None
    check(real_state_before == real_state_after, "real ~/.claude/elearn/state.json untouched by the test")
    check(os.environ.get("HOME", "") == real_home, "HOME unchanged")

    # acceptance criteria 1, 3, 4 on the skill files themselves
    skill_md = open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8").read()
    fm = skill_md.split("---", 2)[1] if skill_md.startswith("---") else ""
    check("name: elearn" in fm.splitlines(), "SKILL.md frontmatter has name: elearn")
    for t in ("/elearn", "learn from my claude traces"):
        check(t in fm, f"SKILL.md description has trigger {t!r}")
    hits = []
    for root, dirs, files in os.walk(SKILL_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                if FORBIDDEN_LITERAL in fh.read():
                    hits.append(os.path.join(root, f))
    check(not hits, f"no file under the skill dir names the old workflow ({hits})")
    prompts = open(os.path.join(SKILL_DIR, "prompts.md"), encoding="utf-8").read()
    for lit in ("Write only inside the run directory.", "You are mapper", "You are reducer", "You are a skeptic",
                "You write the final /elearn report"):
        check(lit in prompts, f"prompts.md has {lit!r}")
    report_fmt = open(os.path.join(SKILL_DIR, "report-format.md"), encoding="utf-8").read()
    check("# /elearn report" in report_fmt, "report-format.md has '# /elearn report'")

    if failures:
        print(f"ELEARN_FAIL {len(failures)} check(s) failed")
        return 1
    print("ELEARN_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
