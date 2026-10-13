#!/usr/bin/env python3
"""Deterministic collector for the /elearn skill.

Walks a Claude Code home (default: ~/.claude), keeps the sessions a human sat at,
and writes a compact run directory that the /elearn subagents read:

  <run>/manifest.json            params, counts, kept session ids in file order
  <run>/sessions/NNNN-<id>.json  one compact record per kept session
  <run>/surfaces.json            skills, commands, agents, plugins, MCP servers, hooks, workflows (names only)
  <run>/usage.json               hit counts per surface item across kept sessions
  <run>/phrases.json             repeated prompts, prompt stems, repeated instruction lines
  <run>/decisions.jsonl          copy of prior /elearn decisions, if any

The run directory defaults to <claude home>/elearn/runs/<UTC stamp>.

Human-turn filter (measured 2026-10-04 on 342 top-level session files under
~/.claude/projects, Claude Code 2.1.257 and 2.1.281):

  - only `type == "user"` records; never `isSidechain`, `isMeta`, `isCompactSummary`,
    or `isVisibleInTranscriptOnly`; never a record whose content is only `tool_result`
  - `promptSource` in {typed, queued} is a prompt the human typed. `sdk` (latch steerer feeds,
    ledger feeds, headless `claude -p`), `system` (task notifications, peer messages),
    and `suggestion_accepted` (model-written text the human accepted) are not
  - `turnOrigin` in {sdk, scheduled, task_notification, peer} is never human
  - a record with no `promptSource` counts only as a slash command:
    `<command-name>/x</command-name>` whose `turnOrigin` is `human` or absent
  - `<pasted_content>` blocks are cut out of the text (pasted, not typed)
  - text that starts with `[steerer]`, or holds the latch steerer preamble, is a steerer
    injection typed into the terminal by `latch inject`, not by the human

Stdlib only. Never prints or copies config values other than names.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile

# prompts that a human typed into the terminal (measured values of `promptSource`)
HUMAN_PROMPT_SOURCES = {"typed", "queued"}
# turn origins that are never a human, whatever promptSource says
NON_HUMAN_ORIGINS = {"sdk", "scheduled", "task_notification", "peer"}
# latch steerer text: `latch inject` types it into the live terminal, so promptSource says typed
STEERER_RES = [
    re.compile(r"^\s*\[steerer\]"),
    re.compile(r"You are the sovereign steerer for a live Claude Code session"),
]
PASTED_RE = re.compile(r"<pasted_content\b[^>]*>.*?</pasted_content\b[^>]*>", re.S)
COMMAND_NAME_RE = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")
COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SKILL_BASE_RE = re.compile(r"^Base directory for this skill:\s*(\S+)")

# scratch locations on every OS; sessions started there are fixtures and tests, not the user's work
DEFAULT_EXCLUDE_CWD = sorted({
    os.path.normcase(os.path.normpath(p))
    for p in (tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir()), "/tmp", "/private/tmp", "/var/folders")
})

TURN_CAP = 2000
# pasted credentials must not be copied into the run directory
# a credential is one unbroken run of letters and digits with digits in it; hyphenated words
# (npm-package-for-widgets, sk-learn-utils) and 40-hex git SHAs are not credentials
SECRET_RES = [
    re.compile(r"\b(xai|sk|ghp|gho|ghu|ghs|glpat|npm)[-_](?=(?:[A-Za-z_\-]*\d){3})[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bxox[abpsr]-\d[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"),  # JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-./+=]{20,}"),
    re.compile(r"(?i)\b(token|api[_-]?key|secret|password|passwd)\b\s*[:=]\s*['\"]?(?=[A-Za-z0-9_\-./+=]*\d)[A-Za-z0-9_\-./+=]{16,}"),
    re.compile(r"\b[a-f0-9]{64,}\b"),
]


def redact(text: str) -> str:
    for rx in SECRET_RES:
        text = rx.sub(lambda m: m.group(0)[:8] + "…[redacted]", text)
    return text


# a slash command, not a path segment (~/x, ./x, a/b) and not followed by more path
SLASH_RE = re.compile(r"(?<![\w/~.])/([a-z][a-z0-9:-]{1,63})\b(?!/)")
# prompts written by a launcher, not typed: eclaude/latch bootstrap briefs
DEFAULT_DROP_PATTERNS = [r"^Read the file \S*/\.latch/bootstrap/"]
SKILL_PATH_RE = re.compile(r"[/\\]skills[/\\]([^/\\]+)[/\\]SKILL\.md$")
WORD_RE = re.compile(r"\s+")
# slash tokens that are built-in Claude Code commands or common path fragments, not skills
SLASH_STOP = {
    "tmp", "usr", "bin", "etc", "var", "dev", "opt", "home", "users", "private", "volumes",
    "api", "v1", "v2", "src", "lib", "test", "tests", "docs", "help", "quit",
    "exit", "clear", "model", "compact", "rewind", "rename", "resume", "status", "config",
    "init", "login", "logout", "mcp", "plugin", "plugins", "skills", "memory", "diff",
    "review", "pr", "cost", "doctor", "theme", "vim", "terminal-setup", "agents",
    "permissions", "hooks", "context", "usage", "goal", "fast", "effort", "btw", "add-dir",
    "bug", "export", "ide", "upgrade", "release-notes", "statusline", "tasks", "todos",
}

# Cost model. CALIBRATION: these constants were measured on the Grok Build version of this skill
# (per-agent tokens from its workflow journal): mappers ~1.1M per 10 sessions, reducer 1.3-2.9M,
# verifiers 0.4-1.8M each, report 2.3-2.7M; wall time 23-66 min. No /elearn run on Claude Code
# has been measured yet, so every number below is a Grok-calibrated estimate for Claude.
MAP_TOKENS_PER_SESSION = {10: 110_000, 1: 250_000}
REDUCER_TOKENS = 1_300_000
VERIFIER_TOKENS = 800_000
REPORT_TOKENS = 2_500_000
FIXED_AGENTS = 4  # 3 skeptics + 1 report
FAN = 10


def estimate(n: int, batch: int = 10) -> dict:
    """Agents, tokens, and wall time for a run over n sessions; the same arithmetic `state.py plan` does."""
    if n <= 0:
        return {"sessions": 0, "agents": 0, "mappers": 0, "reducers": 0, "tokens": 0, "tokens_m": 0.0, "minutes": [0, 0]}
    mappers = -(-n // batch)
    reducers, level = 0, mappers
    while True:
        groups = -(-level // FAN)
        reducers += groups
        level = groups
        if groups <= 1:
            break
    per_session = MAP_TOKENS_PER_SESSION.get(batch, MAP_TOKENS_PER_SESSION[10] * 10 // batch)
    tokens = n * per_session + reducers * REDUCER_TOKENS + 3 * VERIFIER_TOKENS + REPORT_TOKENS
    mid = 30 + n // 6
    return {"sessions": n, "agents": mappers + reducers + FIXED_AGENTS, "mappers": mappers, "reducers": reducers,
            "tokens": tokens, "tokens_m": round(tokens / 1e6, 1), "minutes": [max(15, mid - 15), mid + 20],
            "calibration": "grok-build runs; not yet measured on claude code"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_time(s):
    if not s or not isinstance(s, str):
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def frontmatter(path: str) -> dict:
    """Return name/description from a SKILL.md (or command/agent .md) frontmatter without a YAML dependency."""
    base = os.path.basename(path)
    default = os.path.basename(os.path.dirname(path)) if base == "SKILL.md" else os.path.splitext(base)[0]
    out = {"name": default, "description": ""}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
    except OSError:
        return out
    if not head.startswith("---"):
        return out
    body = head.split("---", 2)
    if len(body) < 3:
        return out
    fm = body[1]
    m = re.search(r"^name:\s*(.+)$", fm, re.M)
    if m:
        out["name"] = m.group(1).strip().strip("'\"")
    m = re.search(r"^description:\s*(.*)$", fm, re.M)
    if m:
        desc = m.group(1).strip()
        if desc in (">", ">-", "|", "|-", ""):
            lines = []
            for line in fm[m.end():].splitlines():
                if line.startswith((" ", "\t")):
                    lines.append(line.strip())
                elif line.strip() == "":
                    continue
                else:
                    break
            desc = " ".join(lines)
        out["description"] = desc.strip("'\"")[:300]
    return out


# ---------------------------------------------------------------- surfaces


def git_root_of(path: str) -> str:
    """Nearest ancestor that holds .git, or ''. Pure filesystem, no subprocess."""
    d = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def git_tracked(path: str, root: str) -> bool | None:
    try:
        r = subprocess.run(["git", "-C", root, "ls-files", "--error-unmatch", "--", path],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.returncode == 0


def under(path: str, base: str) -> bool:
    path, base = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(base))
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def project_skill_dirs(cwd: str, git_root: str) -> list[tuple[str, str]]:
    """(.claude/skills dir, owning root) for cwd and every parent up to the git root."""
    if not cwd:
        return []
    cwd = os.path.normpath(cwd)
    if not git_root or not under(cwd, git_root):
        dirs = [cwd]
    else:
        dirs = []
        d, top = cwd, os.path.normpath(git_root)
        while True:
            dirs.append(d)
            parent = os.path.dirname(d)
            if os.path.normcase(d) == os.path.normcase(top) or parent == d:
                break
            d = parent
    return [(os.path.join(d, ".claude", "skills"), d) for d in dirs]


def find_plugin_skills(plugin_root: str) -> list[tuple[str, str]]:
    """(SKILL.md path, plugin name) for every skills/<n>/SKILL.md under the plugins tree; names only."""
    found = []
    if not os.path.isdir(plugin_root):
        return found
    for root, dirs, files in os.walk(plugin_root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
        if root.count(os.sep) - plugin_root.count(os.sep) > 8:
            dirs[:] = []
            continue
        if "SKILL.md" in files and os.path.basename(os.path.dirname(root)) == "skills":
            # <...>/<plugin>[/<version>]/skills/<skill>/SKILL.md
            above = os.path.dirname(os.path.dirname(root))
            name = os.path.basename(above)
            if re.fullmatch(r"v?\d+(\.\d+)*([.-][\w.]+)?|[0-9a-f]{7,40}", name):
                name = os.path.basename(os.path.dirname(above))
            found.append((os.path.join(root, "SKILL.md"), name))
    return sorted(found)


def mcp_names(path: str, label: str) -> list[tuple[str, str]]:
    """(server name, source label) from a JSON file's mcpServers (and per-project mcpServers); never values."""
    out = []
    if not os.path.isfile(path):
        return out
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for n in (data.get("mcpServers") or {}):
        out.append((n, label))
    projects = data.get("projects")
    if isinstance(projects, dict):
        for proj, cfg in sorted(projects.items()):
            if isinstance(cfg, dict):
                for n in (cfg.get("mcpServers") or {}):
                    out.append((n, f"{label}:project:{proj}"))
    return out


def collect_surfaces(claude_home: str, claude_json: str, sessions: list[dict]) -> dict:
    skills = []

    def add_skills(glob_dir: str, source: str, extra: dict | None = None):
        if not os.path.isdir(glob_dir):
            return
        for d in sorted(os.listdir(glob_dir)):
            p = os.path.join(glob_dir, d, "SKILL.md")
            if os.path.isfile(p):
                rec = {"path": p, "source": source, **frontmatter(p)}
                if extra:
                    rec.update(extra)
                skills.append(rec)

    user_skills_dir = os.path.join(claude_home, "skills")
    add_skills(user_skills_dir, "user")
    # a user skill that is a symlink into a git repo lives in that repo: edits land in its history
    for s in skills:
        link = os.path.dirname(s["path"])
        if os.path.islink(link):
            real = os.path.realpath(link)
            root = git_root_of(real)
            if root and not under(root, claude_home):
                s["symlink_to"] = real
                s["git_tracked"] = git_tracked(os.path.join(real, "SKILL.md"), root)

    # every .claude/skills from a session's cwd up to its git root is a loaded project surface
    skill_dirs: dict[str, tuple[str, str]] = {}
    user_real = os.path.realpath(user_skills_dir)
    for s in sessions:
        for d, owner in project_skill_dirs(s.get("cwd") or "", s.get("git_root") or ""):
            if os.path.isdir(d) and os.path.realpath(d) != user_real:
                skill_dirs.setdefault(os.path.realpath(d), (d, owner))
    project_roots = sorted({owner for _, owner in skill_dirs.values()})
    project_seen: dict[str, dict] = {}
    for d, owner in sorted(skill_dirs.values()):
        before = len(skills)
        add_skills(d, "project", {"project_roots": [owner]})
        for rec in skills[before:]:
            first = project_seen.get(rec["name"])
            if first is None:
                rec["git_tracked"] = git_tracked(rec["path"], owner)
                project_seen[rec["name"]] = rec
            elif owner not in first["project_roots"]:
                first["project_roots"].append(owner)
        del skills[before:]
    skills.extend(project_seen.values())

    # plugins: names only, from the plugins tree and settings.json enabledPlugins keys
    settings_path = os.path.join(claude_home, "settings.json")
    try:
        settings = read_json(settings_path) if os.path.isfile(settings_path) else {}
    except (OSError, ValueError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    enabled_map = settings.get("enabledPlugins") if isinstance(settings.get("enabledPlugins"), dict) else {}
    plugin_root = os.path.join(claude_home, "plugins")
    plugin_names: set[str] = set()
    installed = os.path.join(plugin_root, "installed_plugins.json")
    if os.path.isfile(installed):
        try:
            data = read_json(installed)
            plugin_names.update(k.split("@", 1)[0] for k in ((data.get("plugins") if isinstance(data, dict) else None) or {}))
        except (OSError, ValueError, AttributeError):
            pass
    data_dir = os.path.join(plugin_root, "data")
    data_names = sorted(d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))) if os.path.isdir(data_dir) else []
    for path, name in find_plugin_skills(plugin_root):
        plugin_names.add(name)
        rec = {"path": path, "source": "plugin", "plugin": name, **frontmatter(path)}
        skills.append(rec)
    enabled_names = {k.split("@", 1)[0]: bool(v) for k, v in enabled_map.items()}
    plugins = []
    for name in sorted(plugin_names | set(enabled_names)):
        state = "enabled" if enabled_names.get(name) is True else "disabled" if name in enabled_names else "unlisted"
        plugins.append({"name": name, "state": state, "installed": name in plugin_names,
                        "skill_count": sum(1 for s in skills if s.get("plugin") == name)})
    for s in skills:
        if s["source"] == "plugin":
            s["plugin_state"] = next((p["state"] for p in plugins if p["name"] == s["plugin"]), "unlisted")
    enabled_missing = sorted(n for n, on in enabled_names.items() if on and n not in plugin_names)

    commands = []
    cmd_dir = os.path.join(claude_home, "commands")
    if os.path.isdir(cmd_dir):
        for fn in sorted(os.listdir(cmd_dir)):
            if fn.endswith(".md"):
                p = os.path.join(cmd_dir, fn)
                commands.append({"name": fn[:-3], "path": p, "source": "user"})
    agents = []
    agent_dir = os.path.join(claude_home, "agents")
    if os.path.isdir(agent_dir):
        for fn in sorted(os.listdir(agent_dir)):
            if fn.endswith(".md"):
                p = os.path.join(agent_dir, fn)
                agents.append({"name": frontmatter(p)["name"], "path": p, "source": "user"})

    mcp_sources: dict[str, list[str]] = {}
    for path, label in ((settings_path, "settings.json"),
                        (os.path.join(claude_home, "settings.local.json"), "settings.local.json"),
                        (claude_json, ".claude.json")):
        for n, src in mcp_names(path, label):
            mcp_sources.setdefault(n, []).append(src)
    mcp = [{"name": n, "sources": srcs} for n, srcs in sorted(mcp_sources.items())]

    # hooks are config entries in settings.json; record event names and matcher counts only
    hooks = []
    for event, entries in sorted((settings.get("hooks") or {}).items()):
        hooks.append({"event": event, "matchers": len(entries) if isinstance(entries, list) else None})

    workflows = []
    wf_dir = os.path.join(claude_home, "workflows")
    if os.path.isdir(wf_dir):
        for fn in sorted(os.listdir(wf_dir)):
            if fn.endswith((".js", ".mjs")):
                workflows.append({"name": os.path.splitext(fn)[0], "source": "user", "path": os.path.join(wf_dir, fn)})
    for root in project_roots:
        d = os.path.join(root, ".claude", "workflows")
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith((".js", ".mjs")):
                    workflows.append({"name": os.path.splitext(fn)[0], "source": "project", "path": os.path.join(d, fn)})

    # Claude Code's own per-skill use record (all sessions, this machine); names only
    skill_usage_names: list[str] = []
    if os.path.isfile(claude_json):
        try:
            su = read_json(claude_json).get("skillUsage") or {}
            skill_usage_names = sorted(su.keys()) if isinstance(su, dict) else []
        except (OSError, ValueError, AttributeError):
            pass

    for s in skills:
        s["loaded"] = s["source"] != "plugin" or s.get("plugin_state") == "enabled"
        # in-place edits to these are lost (plugin sync) or land in a git history the skill does not own
        s["protected"] = (
            "plugin" if s["source"] == "plugin"
            else "git-tracked" if s["source"] == "project" and s.get("git_tracked") is not False
            else "git-tracked" if s.get("symlink_to") and s.get("git_tracked")
            else None
        )

    # which loaded skills mention each skill by name (deleting a referenced skill breaks the referrer)
    bodies = {}
    for s in skills:
        if s["loaded"]:
            try:
                with open(s["path"], encoding="utf-8", errors="replace") as f:
                    bodies[s["path"]] = f.read()
            except OSError:
                pass
    for s in skills:
        n = re.escape(s["name"])
        pat = re.compile(r"(`/?" + n + r"`|(?<![\w-])/" + n + r"(?![\w-])|skills/" + n + r"(?![\w-]))")
        s["referenced_by"] = sorted(
            {o["name"] for o in skills if o["loaded"] and o["path"] != s["path"]
             and o["path"] in bodies and pat.search(bodies[o["path"]])}
        )

    by_name = collections.defaultdict(list)
    for s in skills:
        if s["loaded"]:
            by_name[s["name"]].append(s["source"] + (":" + s["plugin"] if s["source"] == "plugin" else ""))
    collisions = {k: v for k, v in by_name.items() if len(v) > 1}

    return {
        "claude_home": claude_home,
        "claude_json": claude_json,
        "user_skills_dir": user_skills_dir,
        "user_skills_dir_realpath": user_real,
        "project_roots": project_roots,
        "skills": skills,
        "commands": commands,
        "agents": agents,
        "plugins": plugins,
        "plugin_data_dirs": data_names,
        "plugins_enabled_but_not_installed": enabled_missing,
        "mcp_servers": mcp,
        "hooks": hooks,
        "workflows": workflows,
        "skill_usage_names": skill_usage_names,
        "skill_name_collisions": collisions,
    }


# ---------------------------------------------------------------- sessions


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text") or "")
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts)
    return ""


def only_tool_results(content) -> bool:
    return isinstance(content, list) and bool(content) and all(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content)


def is_steerer(text: str) -> bool:
    return any(rx.search(text) for rx in STEERER_RES)


def classify_user_record(r: dict, include_sdk: bool = False) -> tuple[str, str]:
    """Return (kind, text). kind is prompt, slash, or a drop reason. Only prompt and slash are human."""
    if r.get("isSidechain"):
        return "sidechain", ""
    if r.get("isMeta") or r.get("isCompactSummary") or r.get("isVisibleInTranscriptOnly"):
        return "meta", ""
    content = (r.get("message") or {}).get("content")
    if only_tool_results(content):
        return "tool_result", ""
    raw = text_of(content)
    origin = r.get("turnOrigin")
    source = r.get("promptSource")
    if origin in NON_HUMAN_ORIGINS and not (include_sdk and origin == "sdk"):
        return "origin_" + str(origin), ""
    if source is None:
        m = COMMAND_NAME_RE.search(raw)
        if m and origin in (None, "human"):
            a = COMMAND_ARGS_RE.search(raw)
            args = PASTED_RE.sub(" ", a.group(1)).strip() if a else ""
            if is_steerer(args):
                return "steerer", ""
            return "slash", ("/" + m.group(1) + (" " + args if args else "")).strip()
        return "no_prompt_source", ""
    if source not in HUMAN_PROMPT_SOURCES and not (include_sdk and source == "sdk"):
        return "source_" + str(source), ""
    text = PASTED_RE.sub(" ", raw).strip()
    if is_steerer(text):
        return "steerer", ""
    if not text:
        return "pasted_only", ""
    return "prompt", text


def scan_session(path: str, drop_patterns: list[re.Pattern], include_sdk: bool) -> dict:
    """One pass over a session JSONL. Always returns a record; `turns` holds only human text."""
    turns: list[str] = []
    tools = collections.Counter()
    mcp_tools = collections.Counter()
    skill_loads = collections.Counter()
    skill_load_paths = {}
    slash = collections.Counter()
    agent_types = collections.Counter()
    workflow_names = collections.Counter()
    paths_touched = collections.Counter()
    dropped_records = collections.Counter()
    models = collections.Counter()
    entrypoints = collections.Counter()
    subagents = 0
    workflow_launches = 0
    parse_errors = 0
    dropped_turns = 0
    sdk_prompts = 0
    steerer_session = False
    cwd = branch = version = ""
    first_ts = last_ts = None
    ai_title = custom_title = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                parse_errors += 1
                continue
            if not isinstance(r, dict):
                parse_errors += 1
                continue
            t = r.get("type")
            ts = r.get("timestamp")
            if isinstance(ts, str):
                first_ts = first_ts or ts
                last_ts = ts if (last_ts is None or ts > last_ts) else last_ts
            if t == "ai-title":
                ai_title = r.get("aiTitle") or ai_title
            elif t == "custom-title":
                custom_title = r.get("customTitle") or custom_title
            if t in ("user", "assistant") and not r.get("isSidechain"):
                cwd = r.get("cwd") or cwd
                branch = r.get("gitBranch") or branch
                version = r.get("version") or version
                if r.get("entrypoint"):
                    entrypoints[r["entrypoint"]] += 1
            if t == "user":
                content = (r.get("message") or {}).get("content")
                if r.get("isMeta") and not r.get("isSidechain"):
                    m = SKILL_BASE_RE.match(text_of(content))
                    if m:
                        name = os.path.basename(m.group(1).rstrip("/\\"))
                        skill_loads[name] += 1
                        skill_load_paths.setdefault(name, m.group(1))
                if r.get("promptSource") == "sdk" and not r.get("isSidechain"):
                    sdk_prompts += 1
                    if is_steerer(text_of(content)):
                        steerer_session = True
                kind, text = classify_user_record(r, include_sdk)
                if kind not in ("prompt", "slash"):
                    dropped_records[kind] += 1
                    continue
                if any(p.search(text) for p in drop_patterns):
                    dropped_turns += 1
                    continue
                turns.append(text)
                for m in SLASH_RE.findall(text):
                    slash[m] += 1
            elif t == "assistant" and not r.get("isSidechain"):
                msg = r.get("message") or {}
                if msg.get("model") and msg.get("model") != "<synthetic>":
                    models[msg["model"]] += 1
                for block in msg.get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name") or ""
                    tools[name] += 1
                    a = block.get("input") if isinstance(block.get("input"), dict) else {}
                    if name.startswith("mcp__"):
                        parts = name.split("__")
                        mcp_tools[parts[1] if len(parts) > 2 else name] += 1
                    elif name in ("Agent", "Task"):
                        subagents += 1
                        if isinstance(a.get("subagent_type"), str):
                            agent_types[a["subagent_type"]] += 1
                    elif name == "Workflow":
                        workflow_launches += 1
                        if isinstance(a.get("name"), str):
                            workflow_names[a["name"]] += 1
                    elif name == "Skill" and isinstance(a.get("skill"), str):
                        skill_loads[a["skill"]] += 1
                    target = a.get("file_path") or a.get("notebook_path") or a.get("path")
                    if isinstance(target, str) and target:
                        sm = SKILL_PATH_RE.search(target)
                        if sm:
                            skill_loads[sm.group(1)] += 1
                            skill_load_paths.setdefault(sm.group(1), target)
                        elif name in ("Read", "Write", "Edit", "NotebookEdit"):
                            paths_touched[target] += 1

    real_tools = sum(tools.values())
    smoke_test = bool(turns) and real_tools == 0 and all(len(t.split()) < 3 for t in turns)
    if steerer_session:
        kind = "steerer"
    elif entrypoints and all(e.startswith("sdk") for e in entrypoints):
        kind = "headless"
    else:
        kind = "interactive"
    git_root = git_root_of(cwd) if cwd and os.path.isdir(cwd) else ""
    base = git_root or cwd
    dirs = collections.Counter()
    for p, n in paths_touched.items():
        rel = os.path.relpath(p, base) if base and under(p, base) else p
        parts = [x for x in re.split(r"[\\/]+", rel) if x]
        key = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if parts else rel)
        dirs[key] += n

    return {
        "id": os.path.splitext(os.path.basename(path))[0],
        "cwd": cwd,
        "git_root": git_root,
        "branch": branch,
        "title": custom_title or ai_title,
        "session_kind": kind,
        "entrypoints": dict(entrypoints),
        "version": version,
        "created_at": first_ts,
        "updated_at": last_ts,
        "model": models.most_common(1)[0][0] if models else None,
        "human_turns": len(turns),
        "dropped_turns": dropped_turns,
        "dropped_records": dict(dropped_records),
        "sdk_prompts": sdk_prompts,
        "parse_errors": parse_errors,
        "smoke_test": smoke_test,
        "turns": [(lambda s: s[:TURN_CAP] + ("…" if len(s) > TURN_CAP else ""))(redact(t)) for t in turns],
        "slash_commands": dict(slash.most_common()),
        "skills_loaded": {k: v for k, v in skill_loads.most_common() if v},
        "skill_load_paths": skill_load_paths,
        "mcp_servers_used": dict(mcp_tools.most_common()),
        "agent_types_used": dict(agent_types.most_common()),
        "workflows_used": dict(workflow_names.most_common()),
        "tools": dict(tools.most_common(25)),
        "subagent_spawns": subagents,
        "workflow_launches": workflow_launches,
        "top_dirs_touched": dict(dirs.most_common(10)),
        "trace_path": path,
    }


def normalize(s: str) -> str:
    return WORD_RE.sub(" ", s.strip().lower())


def session_files(projects_root: str) -> list[str]:
    """Top-level <encoded-cwd>/<uuid>.jsonl only; <uuid>/subagents/*.jsonl are sidechains and never read."""
    out = []
    if not os.path.isdir(projects_root):
        return out
    for enc in sorted(os.listdir(projects_root)):
        d = os.path.join(projects_root, enc)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if fn.endswith(".jsonl") and os.path.isfile(p):
                out.append(p)
    return out


def old_runs(runs_dir: str, keep_days: int) -> list[str]:
    """Run directories older than keep_days. Listed only: this collector deletes nothing."""
    if not os.path.isdir(runs_dir):
        return []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
    out = []
    for name in sorted(os.listdir(runs_dir)):
        try:
            when = dt.datetime.strptime(name[:15], "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if when < cutoff:
            out.append(os.path.join(runs_dir, name))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    ap.add_argument("--claude-json", default=None, help="path of .claude.json (default: <parent of claude home>/.claude.json)")
    ap.add_argument("--out", default=None, help="run directory to create (default: <claude home>/elearn/runs/<UTC timestamp>, or .../runs/estimate with --estimate)")
    ap.add_argument("--days", type=int, default=0, help="only sessions updated in the last N days (0 = all)")
    ap.add_argument("--since-last", action="store_true", help="only sessions updated after the last completed /elearn run (<claude home>/elearn/state.json)")
    ap.add_argument("--include-headless", action="store_true", help="keep headless sessions (claude -p, sdk entrypoints) and their sdk prompts; latch steerer sessions stay out")
    ap.add_argument("--cwd", action="append", default=[], help="keep only sessions whose cwd starts with this (repeatable)")
    ap.add_argument("--exclude-cwd", action="append", default=None, help="drop sessions whose cwd is under this (repeatable; default: the OS temp dirs)")
    ap.add_argument("--drop-pattern", action="append", default=[], help="regex; human turns matching it are dropped (scheduler templates, canaries)")
    ap.add_argument("--min-turns", type=int, default=1, help="minimum kept human turns per session")
    ap.add_argument("--session-id", action="append", default=[], help="only these session ids (repeatable)")
    ap.add_argument("--limit", type=int, default=0, help="keep only the N most recently updated sessions (0 = no limit)")
    ap.add_argument("--estimate", action="store_true", help="scan everything, write only <out>/estimate.json with per-scope session counts, agents, tokens, minutes; touch nothing else")
    ap.add_argument("--batch", type=int, default=10, help="sessions per mapper (10, or 1 for --per-trace)")
    args = ap.parse_args()
    if args.batch < 1:
        ap.error("--batch must be at least 1")

    claude_home = os.path.abspath(os.path.expanduser(args.claude_home))
    claude_json = os.path.abspath(os.path.expanduser(args.claude_json)) if args.claude_json else os.path.join(os.path.dirname(claude_home), ".claude.json")
    projects_root = os.path.join(claude_home, "projects")
    if not os.path.isdir(projects_root):
        log(f"no projects directory at {projects_root}")
        return 2
    runs_dir = os.path.join(claude_home, "elearn", "runs")
    if args.out:
        out = os.path.abspath(os.path.expanduser(args.out))
    else:
        stamp = "estimate" if args.estimate else dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = os.path.join(runs_dir, stamp)
    stale_runs = old_runs(runs_dir, keep_days=30)
    # the run dir holds the user's prompts; keep it owner-only where the OS supports it
    os.makedirs(out, exist_ok=True)
    try:
        os.chmod(out, 0o700)
    except OSError:
        pass
    if not args.estimate:
        for sub in ("sessions", "map", "reduce", "verify"):
            os.makedirs(os.path.join(out, sub), exist_ok=True)

    exclude_cwd = args.exclude_cwd if args.exclude_cwd is not None else DEFAULT_EXCLUDE_CWD
    drop_patterns = [re.compile(p, re.I) for p in DEFAULT_DROP_PATTERNS + args.drop_pattern]
    if args.estimate:
        args.days, args.since_last, args.limit = 0, False, 0
    cutoff = None
    if args.days > 0:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    state_path = os.path.join(claude_home, "elearn", "state.json")
    if args.since_last:
        # count from the last run whose curation finished; an orphaned run must not hide its sessions
        try:
            cutoff = parse_time(read_json(state_path).get("last_completed_at"))
        except (OSError, ValueError):
            cutoff = None
        if cutoff is None:
            log("--since-last: no completed run recorded; scanning everything")
    only_ids = set(args.session_id)

    seen = 0
    dropped = collections.Counter()
    record_drops = collections.Counter()
    kept: list[dict] = []
    for path in session_files(projects_root):
        seen += 1
        sid = os.path.splitext(os.path.basename(path))[0]
        if only_ids and sid not in only_ids:
            dropped["not_in_session_id_list"] += 1
            continue
        if cutoff is not None:
            try:
                if dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc) < cutoff:
                    dropped["older_than_window"] += 1
                    continue
            except OSError:
                pass
        try:
            rec = scan_session(path, drop_patterns, args.include_headless)
        except OSError:
            dropped["unreadable"] += 1
            continue
        for k, v in rec["dropped_records"].items():
            record_drops[k] += v
        if rec["session_kind"] == "steerer":
            dropped["steerer"] += 1
            continue
        if rec["session_kind"] == "headless" and not args.include_headless:
            dropped["headless"] += 1
            continue
        cwd = rec["cwd"]
        if cwd and any(under(cwd, p) for p in exclude_cwd):
            dropped["excluded_cwd"] += 1
            continue
        if args.cwd and not any(under(cwd, p) for p in args.cwd):
            dropped["outside_cwd"] += 1
            continue
        if cutoff is not None:
            ts = parse_time(rec.get("updated_at"))
            if ts is None or ts < cutoff:
                dropped["older_than_window"] += 1
                continue
        if rec["human_turns"] < args.min_turns:
            dropped["no_human_turns"] += 1
            continue
        if rec["smoke_test"]:
            dropped["smoke_test"] += 1
            continue
        kept.append(rec)

    kept.sort(key=lambda r: r.get("updated_at") or "", reverse=True)

    if args.estimate:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            st = read_json(state_path)
        except (OSError, ValueError):
            st = {}
        since = parse_time(st.get("last_completed_at"))

        def in_window(r, cut):
            ts = parse_time(r.get("updated_at"))
            return ts is not None and ts >= cut

        windows = {
            "all": kept,
            "30d": [r for r in kept if in_window(r, now - dt.timedelta(days=30))],
            "14d": [r for r in kept if in_window(r, now - dt.timedelta(days=14))],
            "quick": kept[:25],
        }
        if since is not None:
            windows["since_last"] = [r for r in kept if in_window(r, since)]
        est = {name: estimate(len(rows), args.batch) for name, rows in windows.items()}
        for name in est:
            est[name]["flags"] = {"all": [], "30d": ["--days", "30"], "14d": ["--days", "14"], "quick": ["--limit", "25"],
                                  "since_last": ["--since-last"]}[name]
        if since is not None and est["since_last"]["sessions"] > 0:
            recommended = "since_last"
        elif len(kept) > 100:
            recommended = "14d"
        else:
            recommended = "all"
        result = {"claude_home": claude_home, "out": out, "generated_at": now.isoformat(timespec="seconds"), "sessions_seen": seen,
                  "dropped": dict(dropped), "records_dropped": dict(record_drops), "batch": args.batch,
                  "last_completed_at": st.get("last_completed_at"), "windows": est, "recommended": recommended,
                  "runs_older_than_30d": stale_runs,
                  "note": "tokens and minutes use constants calibrated on Grok Build runs (about +/-50% there); no Claude Code run is measured yet"}
        with open(os.path.join(out, "estimate.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        log(f"seen={seen} kept(all)={len(kept)} batch={args.batch}")
        for name in ("since_last", "quick", "14d", "30d", "all"):
            if name in est:
                e = est[name]
                log(f"  {name:<10} sessions={e['sessions']:>4} agents={e['agents']:>3} tokens~{e['tokens_m']:>5}M  minutes~{e['minutes'][0]}-{e['minutes'][1]}{'  (recommended)' if name == recommended else ''}")
        print(json.dumps(result))
        return 0

    if args.limit > 0 and len(kept) > args.limit:
        dropped["beyond_limit"] += len(kept) - args.limit
        kept = kept[: args.limit]

    # sessions that are one identical prompt repeated across sessions look like automation
    single = collections.Counter(normalize(r["turns"][0]) for r in kept if r["human_turns"] == 1)
    for r in kept:
        r["repeated_single_turn"] = bool(r["human_turns"] == 1 and single[normalize(r["turns"][0])] >= 3)

    for i, r in enumerate(kept):
        r["index"] = i
        with open(os.path.join(out, "sessions", f"{i:04d}-{r['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, indent=1, ensure_ascii=False)

    surfaces = collect_surfaces(claude_home, claude_json, kept)
    project_roots = surfaces["project_roots"]
    with open(os.path.join(out, "surfaces.json"), "w", encoding="utf-8") as f:
        json.dump(surfaces, f, indent=1, ensure_ascii=False)

    # usage per surface item, deterministic
    def hit_record():
        return {"count": 0, "sessions": [], "last_used": None, "via": collections.Counter()}

    usage = collections.defaultdict(hit_record)

    def hit(key, r, n, via):
        u = usage[key]
        u["count"] += n
        if r["id"] not in u["sessions"] and len(u["sessions"]) < 8:
            u["sessions"].append(r["id"])
        if (r.get("updated_at") or "") > (u["last_used"] or ""):
            u["last_used"] = r.get("updated_at")
        u["via"][via] += n

    skill_names = {s["name"] for s in surfaces["skills"]}
    plugin_skill_names = {s["plugin"] + ":" + s["name"]: s["name"] for s in surfaces["skills"] if s["source"] == "plugin"}
    command_names = {c["name"] for c in surfaces["commands"]}
    workflow_names = {w["name"] for w in surfaces["workflows"]}
    for r in kept:
        for name, n in r["skills_loaded"].items():
            hit(("skill", plugin_skill_names.get(name, name)), r, n, "skill_load")
        for name, n in r["slash_commands"].items():
            bare = plugin_skill_names.get(name, name)
            if bare in skill_names:
                hit(("skill", bare), r, n, "slash")
            elif name in command_names:
                hit(("command", name), r, n, "slash")
            elif name in workflow_names:
                hit(("workflow", name), r, n, "slash")
        for name, n in r["mcp_servers_used"].items():
            hit(("mcp", name), r, n, "tool_call")
        for name, n in r["agent_types_used"].items():
            hit(("agent", name), r, n, "agent_call")
        for name, n in r["workflows_used"].items():
            hit(("workflow", name), r, n, "workflow_call")

    def u_of(kind, name):
        u = usage.get((kind, name))
        return {"count": u["count"] if u else 0, "sessions": u["sessions"] if u else [],
                "last_used": u["last_used"] if u else None, "via": dict(u["via"]) if u else {}}

    items = []
    for s in surfaces["skills"]:
        items.append({
            "kind": "skill", "name": s["name"], "source": s["source"], "path": s["path"],
            "protected": s["protected"], "referenced_by": s["referenced_by"],
            "plugin": s.get("plugin"), "plugin_state": s.get("plugin_state"), "loaded": s["loaded"],
            "in_skill_usage": s["name"] in surfaces["skill_usage_names"], **u_of("skill", s["name"]),
        })
    for c in surfaces["commands"]:
        items.append({"kind": "command", "name": c["name"], "path": c["path"], **u_of("command", c["name"])})
    for a in surfaces["agents"]:
        items.append({"kind": "agent", "name": a["name"], "path": a["path"], **u_of("agent", a["name"])})
    for p in surfaces["plugins"]:
        n = sum(i["count"] for i in items if i.get("plugin") == p["name"])
        sess = []
        for i in items:
            if i.get("plugin") == p["name"]:
                for sid in i["sessions"]:
                    if sid not in sess and len(sess) < 8:
                        sess.append(sid)
        items.append({"kind": "plugin", "name": p["name"], "state": p["state"], "installed": p["installed"],
                      "skill_count": p["skill_count"], "count": n, "sessions": sess})
    for m in surfaces["mcp_servers"]:
        items.append({"kind": "mcp", "name": m["name"], "sources": m["sources"], **u_of("mcp", m["name"])})
    for w in surfaces["workflows"]:
        items.append({"kind": "workflow", "name": w["name"], "source": w["source"], "path": w["path"], **u_of("workflow", w["name"])})
    for h in surfaces["hooks"]:
        items.append({"kind": "hook", "name": h["event"], "count": None,
                      "note": "hook runs are not recorded in session transcripts; judge by config only"})

    unknown_slash = collections.Counter()
    for r in kept:
        for name, n in r["slash_commands"].items():
            bare = plugin_skill_names.get(name, name)
            if bare not in skill_names and name not in SLASH_STOP and name not in command_names and name not in workflow_names:
                unknown_slash[name] += n
    configured_mcp = {m["name"] for m in surfaces["mcp_servers"]}
    mcp_unconfigured = {k[1]: u["count"] for k, u in usage.items() if k[0] == "mcp" and k[1] not in configured_mcp}

    unused_loaded = [i for i in items if i["kind"] == "skill" and i["loaded"] and i["count"] == 0 and not i["in_skill_usage"]]
    with open(os.path.join(out, "usage.json"), "w", encoding="utf-8") as f:
        json.dump({
            "kept_sessions": len(kept),
            "items": items,
            "unused_loaded": unused_loaded,
            "slash_commands_with_no_loaded_skill": dict(unknown_slash.most_common()),
            "mcp_servers_used_but_not_in_local_config": mcp_unconfigured,
            "note": "hooks and claude.ai connector MCP servers are not visible in local config; count is None when it cannot be measured. in_skill_usage = the name appears in .claude.json skillUsage (all sessions on this machine)",
        }, f, indent=1, ensure_ascii=False)

    # repeated phrases
    exact = collections.defaultdict(list)
    stems = collections.defaultdict(list)
    lines = collections.defaultdict(set)
    for r in kept:
        if r["repeated_single_turn"]:
            continue
        for t in r["turns"]:
            n = normalize(t)
            if len(n) < 12:
                continue
            if SLASH_RE.fullmatch(t.strip()) or re.fullmatch(r"/[a-z0-9:-]+(\s+\S+){0,3}", n):
                continue
            exact[n].append(r["id"])
            words = n.split(" ")
            if len(words) >= 6:
                stems[" ".join(words[:12])].append(r["id"])
            for ln in t.splitlines():
                ln_n = normalize(ln)
                if len(ln_n.split(" ")) >= 5 and len(ln_n) >= 24:
                    lines[ln_n].add(r["id"])

    def top(d, min_count, key_name):
        rows = []
        for k, ids in d.items():
            ids = list(ids)
            c = len(set(ids))
            if c >= min_count:
                rows.append({key_name: k[:400], "sessions": c, "occurrences": len(ids), "session_ids": sorted(set(ids))[:8]})
        rows.sort(key=lambda x: (-x["sessions"], -x["occurrences"]))
        return rows[:60]

    with open(os.path.join(out, "phrases.json"), "w", encoding="utf-8") as f:
        json.dump({
            "exact_prompts": top(exact, 2, "phrase"),
            "prompt_stems_12_words": top(stems, 3, "stem"),
            "repeated_instruction_lines": top(lines, 3, "line"),
            "note": "counts are distinct sessions; single-turn sessions repeated 3+ times are excluded as likely automation",
        }, f, indent=1, ensure_ascii=False)

    decisions_src = os.path.join(claude_home, "elearn", "decisions.jsonl")
    if os.path.isfile(decisions_src):
        with open(decisions_src, encoding="utf-8") as src, open(os.path.join(out, "decisions.jsonl"), "w", encoding="utf-8") as dst:
            dst.write(src.read())

    # zero hits only mean disuse when the window is wide: every cwd, at least 20 sessions, at least 7 days
    kept_times = sorted(t for t in (parse_time(r.get("updated_at")) for r in kept) if t)
    span_days = (kept_times[-1] - kept_times[0]).total_seconds() / 86400 if len(kept_times) >= 2 else 0.0
    narrow = []
    if args.cwd:
        narrow.append("scoped to one working directory")
    if args.session_id:
        narrow.append("scoped to listed sessions")
    if len(kept) < 20:
        narrow.append(f"only {len(kept)} sessions kept")
    if span_days < 7:
        narrow.append(f"sessions span {span_days:.1f} days")
    disuse_evidence = {"sufficient": not narrow, "span_days": round(span_days, 1),
                       "reason": "; ".join(narrow) or "every working directory, %d sessions over %.0f days" % (len(kept), span_days)}

    manifest = {
        "claude_home": claude_home,
        "run_dir": out,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "disuse_evidence": disuse_evidence,
        "runs_older_than_30d": stale_runs,
        "params": {
            "days": args.days, "since_last": args.since_last, "cutoff": cutoff.isoformat() if cutoff else None,
            "include_headless": args.include_headless, "cwd": args.cwd,
            "exclude_cwd": exclude_cwd, "drop_patterns": DEFAULT_DROP_PATTERNS + args.drop_pattern, "min_turns": args.min_turns,
            "session_ids": args.session_id, "limit": args.limit, "batch": args.batch,
        },
        "estimate": estimate(len(kept), args.batch),
        "sessions_seen": seen,
        "sessions_kept": len(kept),
        "dropped": dict(dropped),
        "records_dropped": dict(record_drops),
        "human_turns_total": sum(r["human_turns"] for r in kept),
        "repeated_single_turn_sessions": sum(1 for r in kept if r["repeated_single_turn"]),
        "project_roots": project_roots,
        "kept": [{"index": r["index"], "id": r["id"], "cwd": r["cwd"], "turns": r["human_turns"], "updated_at": r["updated_at"], "title": r["title"]} for r in kept],
        "prior_decisions": os.path.isfile(decisions_src),
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)

    # a new collection starts a new pending run; state.py moves it through running -> report_ready -> done
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    try:
        state = read_json(state_path)
    except (OSError, ValueError):
        state = {}
    state.update({"last_run_at": manifest["generated_at"], "last_run_dir": out, "sessions_kept": len(kept)})
    if kept:
        state["pending"] = {"run_dir": out, "status": "collected", "started_at": manifest["generated_at"],
                            "updated_at": manifest["generated_at"], "report_ready": False}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)

    log(f"seen={seen} kept={len(kept)} dropped={dict(dropped)} turns={manifest['human_turns_total']}")
    log(f"surfaces: skills={len(surfaces['skills'])} commands={len(surfaces['commands'])} agents={len(surfaces['agents'])} plugins={len(surfaces['plugins'])} mcp={len(surfaces['mcp_servers'])} hooks={len(surfaces['hooks'])} workflows={len(surfaces['workflows'])}")
    log(f"unused loaded skills={len(unused_loaded)}")
    print(json.dumps({"run_dir": out, "kept": len(kept), "seen": seen, "dropped": dict(dropped), "runs_older_than_30d": len(stale_runs)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
