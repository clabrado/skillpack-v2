#!/usr/bin/env bash
# Phase 1 acceptance smoke (non-interactive pieces)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LATCH="$ROOT/bin/latch"
export LATCH_GRACE_MS=1500

echo "== health / auth / inject via bash PTY =="
"$LATCH" run --name phase1 -- /bin/bash -c 'echo READY; while IFS= read -r line; do echo "ECHO:$line"; done' \
  >/tmp/latch-p1-out.txt 2>/tmp/latch-p1-err.txt &
LPID=$!
for i in $(seq 1 30); do
  sleep 0.2
  "$LATCH" ls 2>/dev/null | grep -q phase1 && break
done
"$LATCH" ls | grep phase1
PORT=$(python3 -c "import json,glob,os
for f in glob.glob(os.path.expanduser('~/.latch/sessions/*.json')):
 s=json.load(open(f))
 if s.get('name')=='phase1':
  print(s['port']); break")
TOKEN=$(cat ~/.latch/token)
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/v1/inject" \
  -H "Authorization: Bearer wrong" -H "Content-Type: application/json" \
  -d '{"mode":"text","data":"x","when":"now"}')
test "$code" = "401"
curl -s -X POST "http://127.0.0.1:$PORT/v1/inject" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mode":"text","data":"phase1-ping","when":"now","submit":true}' | grep -q accepted
sleep 0.5
grep -q phase1-ping /tmp/latch-p1-out.txt
kill "$LPID" 2>/dev/null || true
wait "$LPID" 2>/dev/null || true
echo "phase1 smoke OK"

echo "== exit-code fidelity =="
set +e
LATCH_GRACE_MS=300 "$LATCH" run --name p1exit -- /bin/bash -c 'exit 7' >/dev/null 2>&1
rc=$?
set -e
test "$rc" = "7" || { echo "FAIL: expected exit 7, got $rc"; exit 1; }
echo "exit-code OK (7)"

echo "== claude -p under latch =="
cd /tmp
out=$(LATCH_GRACE_MS=2000 "$LATCH" run --name phase1c -- claude -p "Reply with exactly: P1_OK" --output-format text 2>/dev/null || true)
echo "$out" | grep -q P1_OK
echo "claude -p under latch OK"
echo "ALL PHASE1 AUTOMATED GATES PASSED"
