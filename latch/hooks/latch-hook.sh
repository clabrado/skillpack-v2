#!/bin/bash
# Claude Code hooks pass a JSON payload on stdin.
# No-op unless this session was started under `latch run` (LATCH_PORT set).
[ -z "$LATCH_PORT" ] && exit 0
exec curl -s -m 2 -X POST "http://127.0.0.1:${LATCH_PORT}/v1/hook" \
  -H "Content-Type: application/json" \
  --data-binary @- > /dev/null 2>&1 || true
