"""
test/test_factual_discipline.py — the engine-owned STEERER FACTUAL DISCIPLINE
block reaches EVERY decision prompt (5.8-CC-2 deliverable e).

The block used to be pasted into each goalpack by hand; goalpacks no longer
carry it. These falsifiers hold WITHOUT any goalpack text: the goal fixtures
below deliberately contain no discipline block at all.

Run: python3 test/test_factual_discipline.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "steerer", ROOT / "client" / "steerer.py")
steerer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(steerer)

count = 0


def ok(cond, msg):
    global count
    assert cond, msg
    count += 1


GOAL = "# Goal\nShip the widget.\n\n# Constraints\n- stay in the repo\n"
ARGS = ("SYSTEM RULES", GOAL, "materiality 3>=3", "mid-work",
        "[bash] pytest -q", ["prev decision"])

# 1. Both prompt paths carry the discipline block, with a goalpack that does
#    NOT contain it — the paragraph is gone, the mechanism supplies it.
for primed in (False, True):
    prompt, full_prompt = steerer.build_decision_prompts(
        *ARGS, primed=primed, nonce="cafecafe0123")
    ok("STEERER FACTUAL DISCIPLINE" in prompt,
       f"primed={primed}: discipline block missing from decision prompt")
    ok("NOT authoritative on FACTS" in prompt,
       f"primed={primed}: discipline substance missing")
    ok("STEERER FACTUAL DISCIPLINE" in full_prompt,
       f"primed={primed}: block missing from resume-fallback prompt")

# 2. The four rules that measurably worked are all present.
block = steerer.STEERER_FACTUAL_DISCIPLINE
for needle in (
    "SEEN it in the event stream",
    "not evidence of absence",
    "Steer HARD on process",
    "pushes back on a factual claim WITH EVIDENCE",
):
    ok(needle in block, f"discipline rule lost: {needle!r}")

# 3. Structure preserved: primed path is the compact reminder, unprimed the
#    full pack; both end with the fenced untrusted events.
prompt_unprimed, full_unprimed = steerer.build_decision_prompts(
    *ARGS, primed=False, nonce="cafecafe0123")
ok(prompt_unprimed == full_unprimed, "unprimed prompt must BE the full pack")
ok("# Goalpack (this is your allegiance" in prompt_unprimed,
   "full pack lost the goalpack section")
prompt_primed, _ = steerer.build_decision_prompts(
    *ARGS, primed=True, nonce="cafecafe0123")
ok("# Goalpack (this is your allegiance" not in prompt_primed,
   "primed path must not resend the full goalpack")
ok("Still in force from turn 1" in prompt_primed,
   "primed path lost the compact reminder")
for p in (prompt_primed, prompt_unprimed):
    ok("<untrusted-session-data-cafecafe0123>" in p
       and "</untrusted-session-data-cafecafe0123>" in p,
       "untrusted-events fence lost")
    ok("# Why you're being asked now" in p, "gate reason lost")

# 4. COUNTERFACTUAL — neuter the block by its name; the falsifier must flip.
#    If presence still held with the constant emptied, these tests would be
#    testing something other than the constant.
_orig = steerer.STEERER_FACTUAL_DISCIPLINE
try:
    steerer.STEERER_FACTUAL_DISCIPLINE = ""
    neutered, _ = steerer.build_decision_prompts(
        *ARGS, primed=True, nonce="cafecafe0123")
    ok("STEERER FACTUAL DISCIPLINE" not in neutered,
       "constant neutered but block still present — presence does not "
       "depend on the constant; the falsifier above is testing nothing")
finally:
    steerer.STEERER_FACTUAL_DISCIPLINE = _orig

print(f"OK — {count} assertions passed")

# Only exit when run as a script. A bare `sys.exit(0)` here runs at IMPORT
# time, and pytest imports this file during collection — so `pytest test/`
# died with `INTERNALERROR SystemExit: 0` and ran NOTHING, not even the other
# 117 tests. The failure looked like a broken suite rather than one file's
# calling convention, which is the expensive part. The assertions above still
# execute on import (they are module-level by design); this only stops the
# process-level exit from escaping into the collector.
if __name__ == "__main__":
    sys.exit(0)
