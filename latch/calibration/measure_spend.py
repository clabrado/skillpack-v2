#!/usr/bin/env python3
"""Measure real grok token spend from ~/.grok/logs/unified.jsonl in a window.
Usage: measure_spend.py <since_iso_utc>   e.g. 2026-07-12T14:40:00Z
Sums every shell.turn.inference_done at/after <since>. Counts ALL grok calls on
the machine in that window (steerer + any interactive), so run tests in isolation."""
import json, sys
from datetime import datetime, timezone

since = sys.argv[1]
def parse(ts): return datetime.fromisoformat(ts.replace("Z","+00:00"))
since_dt = parse(since)

calls = 0
tot = {"prompt_tokens":0,"cached_prompt_tokens":0,"completion_tokens":0,"reasoning_tokens":0}
rows = []
with open("/Users/beans/.grok/logs/unified.jsonl") as f:
    for line in f:
        try: e = json.loads(line)
        except: continue
        if e.get("msg") != "shell.turn.inference_done": continue
        ts = e.get("ts")
        if not ts or parse(ts) < since_dt: continue
        ctx = e.get("ctx",{})
        calls += 1
        for k in tot: tot[k] += ctx.get(k,0) or 0
        rows.append((ts, ctx.get("prompt_tokens",0), ctx.get("cached_prompt_tokens",0),
                     ctx.get("completion_tokens",0), ctx.get("reasoning_tokens",0)))

print(f"=== grok spend since {since} ===")
print(f"calls: {calls}")
if calls:
    billable_in = tot["prompt_tokens"] - tot["cached_prompt_tokens"]
    print(f"prompt_tokens        : {tot['prompt_tokens']:>9,}  (input)")
    print(f"  cached (cheaper)   : {tot['cached_prompt_tokens']:>9,}  ({100*tot['cached_prompt_tokens']//max(tot['prompt_tokens'],1)}% cache hit)")
    print(f"  uncached (billable): {billable_in:>9,}")
    print(f"completion_tokens    : {tot['completion_tokens']:>9,}  (output)")
    print(f"reasoning_tokens     : {tot['reasoning_tokens']:>9,}  (effort burn)")
    print(f"--- per call: {tot['prompt_tokens']//calls:,} in / {tot['completion_tokens']//calls:,} out / {tot['reasoning_tokens']//calls:,} reasoning ---")
    print("--- per-call detail (ts, prompt, cached, completion, reasoning) ---")
    for r in rows: print("  ", r[0], f"{r[1]:>7,} {r[2]:>6,} {r[3]:>5,} {r[4]:>5,}")
