#!/bin/bash
set -euo pipefail

# Only needed on Claude Code on the web: each session runs in a fresh
# container, so a previously started background worker does not
# carry over.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Start the claude-mem memory worker if it isn't already listening.
if ! curl -s -o /dev/null http://127.0.0.1:37700 2>/dev/null; then
  nohup npx claude-mem start >/tmp/claude-mem-worker.log 2>&1 &
  disown
fi
