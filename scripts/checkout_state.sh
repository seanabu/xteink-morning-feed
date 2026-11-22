#!/usr/bin/env bash
# Check out the `state` branch at ./state (creating it on first use).
set -euo pipefail
if git fetch -q origin state 2>/dev/null; then
  git worktree add -q -B state state FETCH_HEAD
else
  git worktree add -q --orphan -b state state
fi
