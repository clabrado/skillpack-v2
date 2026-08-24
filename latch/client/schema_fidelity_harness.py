#!/usr/bin/env python3
"""
M2 — SCHEMA FIDELITY HARNESS (measure-before-depend).

Question: does the GX10's local engine (nvidia/Qwen3.6-35B-A3B-NVFP4, served as
`qwen3.6-35b` on http://10.10.10.2:8001) emit latch's steering DECISION_SCHEMA
faithfully enough for the localsteer engine shim to depend on it?

The bar is NOT "looks like JSON" — it is latch's own `_interpret()` accepting the
response as a decision. This harness imports the real DECISION_SCHEMA,
build_decision_prompts(), and _interpret() from client/steerer.py; nothing is
re-implemented.

PROMPT PROVENANCE (read this before trusting the numbers)
  latch does NOT persist its decision prompts anywhere. ~/.latch/audit.jsonl
  records only {ts, sid, mode, result, data_preview, source_ip, when}, and
  ~/.latch/logs/*.raw.log are raw PTY captures of the steered session, not
  engine calls. So verbatim historical prompts do not exist to harvest.
  What IS real and on disk:
    * 62 real goalpacks   — ~/.latch/steerers/*.goal.md
    * 449 real transcripts — ~/.claude/projects/*/*.jsonl
  This harness rebuilds decision prompts from those two real sources through
  latch's REAL code path: transcript records -> latchlib.jsonl_tail.map_record()
  (the same converter the live steerer's event stream uses) -> _compact_events()
  -> build_decision_prompts(). The goalpacks, the event content, the system
  ruleset, the factual-discipline block and the assembly are all real; only the
  pairing of a given goalpack with a given event window is synthetic.
  Label results accordingly: REAL INGREDIENTS, RECONSTRUCTED PAIRING.

Variants
  A  guided decoding via response_format json_schema (strict)
  B  prompt-enforced JSON (no response_format) — latch's own instruction text

Usage
  python3 schema_fidelity_harness.py --variant a --n 50
  python3 schema_fidelity_harness.py --variant b --n 50 --out /tmp/b.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

_CLIENT_DIR = Path(__file__).resolve().parent
_REPO = _CLIENT_DIR.parent
for p in (str(_CLIENT_DIR), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import steerer  # noqa: E402  (real latch code — schema, prompt builder, interpreter)
from latchlib.jsonl_tail import map_record  # noqa: E402

ENDPOINT = "http://10.10.10.2:8001/v1/chat/completions"
MODELS_URL = "http://10.10.10.2:8001/v1/models"
MODEL = "qwen3.6-35b"

GOALPACK_DIR = Path.home() / ".latch" / "steerers"
TRANSCRIPT_GLOB = Path.home() / ".claude" / "projects"

# gate_reason strings the live SteerGate / pre-gate actually emit (steerer.py
# should_decide() and _pregate_escalate()).
GATE_REASONS = [
    "turn-boundary/idle (needs direction)",
    "notification pending (permission/idle prompt)",
    "error signal — never gated",
    "materiality 5>=3 (test result, 2 distinct target(s))",
    "materiality 7>=3 (commit/merge, 3 distinct target(s))",
    "dead-man's-switch: 302s with no material change",
    "tool error",
    "stall (repeated tool call)",
]


def extract_system_ruleset() -> str:
    """The steerer's sovereign ruleset is a local in main(); pull the literal out
    of the source so this harness cannot drift from what latch really sends."""
    src = (_CLIENT_DIR / "steerer.py").read_text()
    marker = '    system = """'
    i = src.index(marker)
    start = i + len(marker)
    end = src.index('"""', start)
    return src[start:end]


# ---------------------------------------------------------------- corpus build
def load_goalpacks() -> list[tuple[str, str]]:
    out = []
    for p in sorted(GOALPACK_DIR.glob("*.goal.md")):
        try:
            t = p.read_text(errors="replace").strip()
        except OSError:
            continue
        if len(t) > 200:
            out.append((p.name, t))
    return out


def load_event_windows(limit: int, rng: random.Random) -> list[tuple[str, list[dict]]]:
    """Real Claude Code transcript records -> real latch frames, sliced into
    contiguous windows the size a live `pending` batch actually reaches."""
    files = [p for p in TRANSCRIPT_GLOB.glob("*/*.jsonl") if p.stat().st_size > 40_000]
    rng.shuffle(files)
    windows: list[tuple[str, list[dict]]] = []
    for f in files:
        if len(windows) >= limit:
            break
        try:
            lines = f.read_text(errors="replace").splitlines()
        except OSError:
            continue
        frames: list[dict] = []
        for ln in lines:
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            try:
                frames.extend(map_record(rec, "harness"))
            except Exception:
                continue
        if len(frames) < 12:
            continue
        # up to 2 windows per transcript, so the corpus spans many sessions
        for _ in range(2):
            if len(windows) >= limit:
                break
            n = rng.randint(4, 14)
            if len(frames) <= n:
                break
            s = rng.randrange(0, len(frames) - n)
            win = frames[s:s + n]
            # a live decision batch usually ends at a turn boundary
            if rng.random() < 0.5:
                win = win + [{
                    "kind": "turn_stopped",
                    "screen_tail": _screen_tail(win),
                }]
            windows.append((f"{f.parent.name}/{f.name}#{s}", win))
    return windows


def _screen_tail(win: list[dict]) -> str:
    for e in reversed(win):
        if e.get("kind") == "assistant_text" and e.get("text"):
            return e["text"][-600:]
        if e.get("kind") == "tool_result" and e.get("preview"):
            return str(e["preview"])[-600:]
    return "(no visible output)"


def build_corpus(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    packs = load_goalpacks()
    if not packs:
        sys.exit("no goalpacks found under ~/.latch/steerers/")
    windows = load_event_windows(n, rng)
    if not windows:
        sys.exit("no transcript event windows could be built")
    ruleset = extract_system_ruleset()
    corpus = []
    for i in range(n):
        gp_name, goal = packs[i % len(packs)]
        win_id, win = windows[i % len(windows)]
        midturn = rng.random() < 0.6
        phase = (
            "Claude is MID-TURN (still working). wait unless intervention beats waiting; "
            "redirect interrupts the turn."
            if midturn
            else "Claude just finished a turn (idle). steer types into the free composer."
        )
        gate_reason = rng.choice(GATE_REASONS)
        prompt, _full = steerer.build_decision_prompts(
            ruleset,
            goal,
            gate_reason,
            phase,
            steerer._compact_events(win),
            [],
            primed=False,  # stateless OpenAI-compatible shim: full pack every call
        )
        corpus.append({
            "idx": i,
            "goalpack": gp_name,
            "events": win_id,
            "midturn": midturn,
            "gate_reason": gate_reason,
            "prompt": prompt,
        })
    return corpus


# ------------------------------------------------------------------- engine io
def wait_for_engine(timeout_s: int = 900) -> float:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(MODELS_URL, timeout=5) as r:
                body = json.loads(r.read().decode())
            if any(m.get("id") == MODEL for m in body.get("data", [])):
                return time.time() - t0
        except Exception:
            pass
        time.sleep(20)
    sys.exit(f"engine never served {MODEL} within {timeout_s}s")


def call_engine(prompt: str, variant: str, timeout: int = 240, max_tokens: int = 1024) -> dict:
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": steerer.CLAUDE_ENGINE_SYSPROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "top_p": 0.95,
    }
    if variant == "a":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "decision",
                "schema": json.loads(steerer.DECISION_SCHEMA),
                "strict": True,
            },
        }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        return {"status": e.code, "latency": time.time() - t0,
                "raw": e.read().decode()[:4000], "content": None}
    except Exception as e:
        return {"status": None, "latency": time.time() - t0,
                "raw": f"{type(e).__name__}: {e}", "content": None}
    lat = time.time() - t0
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": status, "latency": lat, "raw": raw[:4000], "content": None}
    ch = (obj.get("choices") or [{}])[0]
    return {
        "status": status,
        "latency": lat,
        "content": (ch.get("message") or {}).get("content"),
        "finish_reason": ch.get("finish_reason"),
        "completion_tokens": (obj.get("usage") or {}).get("completion_tokens"),
        "prompt_tokens": (obj.get("usage") or {}).get("prompt_tokens"),
        "raw": None,
    }


# -------------------------------------------------------------------- scoring
VALID_ACTIONS = ("steer", "redirect", "wait", "done", "blocked")


def score(content: str | None) -> dict:
    """Acceptance = latch's OWN _interpret(); schema check is reported separately."""
    if content is None:
        return {"parsed_json": False, "schema_ok": False, "interpret_ok": False,
                "action": None, "error_kind": "no_content"}
    parsed = None
    try:
        parsed = json.loads(content.strip())
    except json.JSONDecodeError:
        parsed = None
    schema_ok = (
        isinstance(parsed, dict)
        and parsed.get("action") in VALID_ACTIONS
        and all(k in parsed for k in ("action", "message", "reasoning", "evidence"))
        and all(isinstance(parsed.get(k), str) for k in ("message", "reasoning", "evidence"))
    )
    d = steerer._interpret(content, "")
    ok = not d.get("_engine_error_kind")
    return {
        "parsed_json": isinstance(parsed, dict),
        "schema_ok": bool(schema_ok),
        "interpret_ok": ok,
        "action": d.get("action") if ok else None,
        "error_kind": d.get("_engine_error_kind"),
        "error": d.get("_engine_error"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["a", "b"], required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1729)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--skip-wait", action="store_true")
    args = ap.parse_args()

    waited = 0.0 if args.skip_wait else wait_for_engine()
    print(f"[engine] ready after {waited:.0f}s", file=sys.stderr)

    corpus = build_corpus(args.n, args.seed)
    print(f"[corpus] {len(corpus)} prompts; "
          f"mean prompt chars={statistics.mean(len(c['prompt']) for c in corpus):.0f}",
          file=sys.stderr)

    rows = []
    for c in corpus:
        r = call_engine(c["prompt"], args.variant, max_tokens=args.max_tokens)
        s = score(r.get("content"))
        row = {**{k: c[k] for k in ("idx", "goalpack", "events", "midturn", "gate_reason")},
               **{k: r.get(k) for k in ("status", "latency", "finish_reason",
                                        "completion_tokens", "prompt_tokens")},
               **s,
               "content": (r.get("content") or r.get("raw") or "")[:1500]}
        rows.append(row)
        print(f"[{c['idx']:>3}] http={r.get('status')} {r.get('latency',0):5.1f}s "
              f"fin={r.get('finish_reason')} json={s['parsed_json']} "
              f"schema={s['schema_ok']} interp={s['interpret_ok']} act={s['action']}",
              file=sys.stderr)

    n = len(rows)
    ok200 = [r for r in rows if r["status"] == 200]
    parse = sum(1 for r in rows if r["parsed_json"])
    schem = sum(1 for r in rows if r["schema_ok"])
    interp = sum(1 for r in rows if r["interpret_ok"])
    lats = [r["latency"] for r in ok200]
    dist = Counter(r["action"] for r in rows if r["interpret_ok"])

    summary = {
        "variant": args.variant, "n": n, "max_tokens": args.max_tokens, "engine_wait_s": round(waited),
        "http_200": len(ok200),
        "parse_rate": round(100 * parse / n, 1),
        "schema_rate": round(100 * schem / n, 1),
        "interpret_rate": round(100 * interp / n, 1),
        "mean_latency_s": round(statistics.mean(lats), 2) if lats else None,
        "p95_latency_s": round(sorted(lats)[int(0.95 * len(lats)) - 1], 2) if lats else None,
        "mean_completion_tokens": round(statistics.mean(
            [r["completion_tokens"] for r in ok200 if r["completion_tokens"]]), 1) if ok200 else None,
        "action_distribution": dict(dist),
        "finish_reasons": dict(Counter(r["finish_reason"] for r in rows)),
        "failures": [{"idx": r["idx"], "status": r["status"],
                      "error_kind": r["error_kind"], "content": r["content"][:400]}
                     for r in rows if not r["interpret_ok"]][:10],
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
