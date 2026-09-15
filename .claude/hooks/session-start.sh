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

# claude-mem's own installer registers its marketplace by copying
# files directly rather than cloning, which omits .claude-plugin/
# and leaves the plugin stuck as "failed to load: cache-miss". Force
# a proper re-clone through Claude Code's own marketplace refresh.
claude plugin marketplace update thedotmack >/dev/null 2>&1 || true

# Install the bkit plugin if this container doesn't already have it
# (a fresh container has no user-scope plugin installs).
if ! claude plugin list 2>/dev/null | grep -q "bkit@bkit-marketplace"; then
  claude plugin marketplace add popup-studio-ai/bkit-claude-code >/dev/null 2>&1 || true
  claude plugin install bkit@bkit-marketplace >/dev/null 2>&1 || true
fi

# Install the headroom plugin (context-compression startup hooks) if
# this container doesn't already have it.
if ! claude plugin list 2>/dev/null | grep -q "headroom@headroom-marketplace"; then
  claude plugin marketplace add chopratejas/headroom >/dev/null 2>&1 || true
  claude plugin install headroom@headroom-marketplace >/dev/null 2>&1 || true
fi

# Install the headroom CLI itself (the plugin's hooks only ensure a
# durable `headroom init` deployment; they need the binary present).
# uv keeps this isolated from system pip and avoids Debian package
# conflicts (see PyJWT).
if ! command -v headroom >/dev/null 2>&1 && command -v uv >/dev/null 2>&1; then
  uv tool install --python 3.13 "headroom-ai[all]" >/tmp/headroom-install.log 2>&1 || true
fi
