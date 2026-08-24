#!/usr/bin/env python3
"""Unit tests for the STEER-01 engine layer (client/steerer.py).

Pure stdlib, no live CLI calls: engine subprocesses are faked by monkeypatching
steerer._spawn. Run: python3 test/test_engine_layer.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("steerer", REPO / "client" / "steerer.py")
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1


def fake_proc(stdout="", stderr="", rc=0):
    p = types.SimpleNamespace()
    p.stdout, p.stderr, p.returncode = stdout, stderr, rc
    return p


def with_spawn(stdout="", stderr="", rc=0):
    """Patch steerer._spawn to return a canned process result."""
    st._spawn = lambda argv, timeout, engine: (fake_proc(stdout, stderr, rc), None)


DEC = {"action": "steer", "message": "m", "reasoning": "r", "evidence": "e"}


def clean_env():
    for k in ("LATCH_STEER_ENGINE", "LATCH_STEER_CMD", "LATCH_GROK_CMD",
              "LATCH_CLAUDE_MODEL"):
        os.environ.pop(k, None)


# --- engine selection -------------------------------------------------------
clean_env()
ok(st.EngineSession().engine == "claude", "default engine is claude")
ok(st.EngineSession().stateful, "claude engine is stateful")
os.environ["LATCH_GROK_CMD"] = "mycli --flag 'quoted arg'"
e = st.EngineSession()
ok(e.engine == "cmd" and not e.stateful, "LATCH_GROK_CMD implies stateless cmd")
ok(e.cmd_argv == ["mycli", "--flag", "quoted arg"], "cmd argv shlex-split at init")
os.environ["LATCH_STEER_ENGINE"] = "grok"
ok(st.EngineSession().engine == "grok", "explicit grok wins over cmd alias")
clean_env()

# unbalanced quote fails at INIT, not mid-run
os.environ["LATCH_STEER_CMD"] = "mycli --p \"unbalanced"
try:
    st.EngineSession()
    ok(False, "unbalanced quote must sys.exit at init")
except SystemExit as ex:
    ok("invalid LATCH_STEER_CMD" in str(ex.code), "unbalanced quote exits with clear msg")
clean_env()

# --- status classification --------------------------------------------------
ok(st._kind_from_status(401) == "auth", "401 auth")
ok(st._kind_from_status(403) == "auth", "403 auth")
ok(st._kind_from_status(402) == "payment", "402 payment")
ok(st._kind_from_status(429) == "ratelimit", "429 ratelimit")
ok(st._kind_from_status(503) == "transient", "503 transient")
ok(st._kind_from_status(408) == "transient", "408 transient")
ok(st._kind_from_status(404) == "config", "404 config (won't self-heal)")
ok(st._kind_from_status(None) is None, "null status unclassified")

# --- _normalize: non-enum action is a tagged malformed error ----------------
d = st._normalize({"action": "continue", "message": "keep going"})
ok(d["_engine_error_kind"] == "malformed", "unknown action tagged malformed")
d = st._normalize({"error": "quota"})
ok(d["_engine_error_kind"] == "malformed", "actionless object tagged malformed")
d = st._normalize(dict(DEC))
ok(d["action"] == "steer" and "_engine_error_kind" not in d, "valid decision passes")

# --- parse_decision: failures are tagged, not silent waits ------------------
d = st.parse_decision("total garbage")
ok(d["_engine_error_kind"] == "malformed", "no-JSON scrape tagged malformed")
d = st.parse_decision('{"action": broken')
ok(d["_engine_error_kind"] == "malformed", "bad-JSON scrape tagged malformed")

# --- _interpret: parse FIRST, classify only on failure ----------------------
# a legit decision whose evidence contains error-signature words must SURVIVE
prosey = "Decision:\n" + json.dumps({**DEC, "action": "redirect",
                                     "evidence": "pytest timed out; rate limit hit"})
d = st._interpret(prosey, "")
ok(d["action"] == "redirect" and "_engine_error_kind" not in d,
   "decision with 'timed out' in evidence is NOT misclassified as engine error")
# fenced block
d = st._interpret("blah\n```json\n" + json.dumps(DEC) + "\n```\ntrailer", "")
ok(d["action"] == "steer", "fenced json parsed")
# strict whole-stdout
d = st._interpret(json.dumps(DEC), "")
ok(d["action"] == "steer", "strict whole-stdout parsed")
# pure error text → classified
d = st._interpret("", "API error (status 402 Payment Required): balance empty")
ok(d["_engine_error_kind"] == "payment", "error-only output classified payment")
# garbage → malformed
d = st._interpret("no json here", "")
ok(d["_engine_error_kind"] == "malformed", "garbage output tagged malformed")

# --- CRITICAL #1: claude envelope without a decision fails LOUD -------------
# envelope is valid JSON, is_error false, rc 0, but structured_output absent
# and result is a DICT (not str) — the old code scraped the envelope itself,
# normalized to a silent untagged `wait`, and ran blind forever.
env_no_decision = json.dumps({"is_error": False, "result": {"action": "redirect"},
                              "session_id": "x"})
with_spawn(stdout=env_no_decision, rc=0)
d = st._run_claude(["claude", "-p", "x"], 10)
ok(d["_engine_error_kind"] == "malformed",
   "CRITICAL: envelope without structured_output/result-str → malformed, not silent wait")
with_spawn(stdout=json.dumps({"is_error": False, "session_id": "x"}), rc=0)
d = st._run_claude(["claude", "-p", "x"], 10)
ok(d["_engine_error_kind"] == "malformed", "envelope missing result entirely → malformed")

# happy path: structured_output honored
with_spawn(stdout=json.dumps({"is_error": False, "structured_output": DEC}), rc=0)
d = st._run_claude(["claude", "-p", "x"], 10)
ok(d["action"] == "steer" and "_engine_error_kind" not in d, "structured_output honored")

# result-as-string fallback still parses
with_spawn(stdout=json.dumps({"is_error": False, "result": json.dumps(DEC)}), rc=0)
d = st._run_claude(["claude", "-p", "x"], 10)
ok(d["action"] == "steer", "result-string fallback parsed")

# in-envelope api error classified structurally
with_spawn(stdout=json.dumps({"is_error": True, "api_error_status": 401,
                              "result": "OAuth token has expired"}), rc=1)
d = st._run_claude(["claude", "-p", "x"], 10)
ok(d["_engine_error_kind"] == "auth", "envelope 401 → auth")

# resume-not-found → _resume_failed
with_spawn(stdout=json.dumps({"is_error": True, "api_error_status": None,
                              "result": "No conversation found with session ID abc"}), rc=1)
d = st._run_claude(["claude", "-p", "x", "--resume", "abc"], 10)
ok(d.get("_resume_failed"), "resume-not-found tagged _resume_failed")

# --- cmd engine -------------------------------------------------------------
with_spawn(stdout=json.dumps(DEC), rc=0)
d = st._run_cmd(["mycli", "x"], 10)
ok(d["action"] == "steer", "cmd strict parse")
with_spawn(stderr="status 402 payment required", rc=1)
d = st._run_cmd(["mycli", "x"], 10)
ok(d["_engine_error_kind"] == "payment", "cmd rc!=0 classified")
with_spawn(stdout="not json", rc=0)
d = st._run_cmd(["mycli", "x"], 10)
ok(d["_engine_error_kind"] == "malformed", "cmd garbage tagged malformed")

# --- EngineSession session lifecycle (stubbed _call_engine) -----------------
clean_env()
e = st.EngineSession()
calls = []


def stub(prompt, timeout, flags, results=iter([])):
    calls.append((prompt, list(flags)))
    return next(stub.results)


e._call_engine = stub
# failed first call → session NOT adopted
stub.results = iter([st._engine_error_decision("transient", "boom")])
e.call("P1")
ok(e.session_id is None, "failed first call does not adopt session id")
# successful first call → adopted; then resume flags used
stub.results = iter([dict(DEC)])
e.call("P2")
sid = e.session_id
ok(sid is not None and calls[-1][1][0] == "--session-id", "success adopts session id")
stub.results = iter([dict(DEC)])
e.call("P3")
ok(calls[-1][1] == ["--resume", sid], "later calls resume the adopted session")
# resume failure → reset, NOT auto-retried (caller must re-prime w/ full pack)
rf = st._decision("wait", reasoning="resume failed")
rf["_resume_failed"] = True
stub.results = iter([rf])
d = e.call("P4")
ok(d.get("_resume_failed") and e.session_id is None,
   "resume failure resets session and returns to caller for re-priming")

# --- _compact_events keeps the NEWEST events as valid JSON ------------------
evts = [{"kind": "tool_use", "n": i, "pad": "x" * 200} for i in range(100)]
out = st._compact_events(evts, budget=2000)
parsed = json.loads(out)
ok(parsed["dropped_oldest_events"] > 0, "compaction reports dropped count")
ok(parsed["events"][-1]["n"] == 99, "compaction keeps the newest event")
ok(len(out) <= 2000, "compaction respects budget")
one_huge = [{"kind": "tool_result", "blob": "y" * 5000}]
out = st._compact_events(one_huge, budget=1000)
json.loads(out)  # must stay valid JSON
ok(len(out) <= 1000, "single-huge-event fallback bounded and valid")
# quote/backslash-heavy content roughly DOUBLES under the outer re-escape —
# the fallback must still respect the final-output budget
nasty = [{"kind": "tool_result", "blob": '\\"' * 2500}]
out = st._compact_events(nasty, budget=1000)
json.loads(out)
ok(len(out) <= 1000, "quote-heavy fallback still within budget after re-escape")

print(f"OK — {PASS} assertions passed")
