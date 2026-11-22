#!/usr/bin/env bash
# Commit and push the state worktree (./state), retrying on concurrent pushes.
# Every writer adds or removes whole files, so a rebase never conflicts.
set -euo pipefail
MSG="${1:-Update state}"
cd "${STATE_DIR:-state}"
git add -A
if git diff --cached --quiet; then echo "state unchanged"; exit 0; fi
git -c user.name="morning-feed" -c user.email="morning-feed@users.noreply.github.com" commit -q -m "$MSG"
for i in 1 2 3 4 5 6; do
  if git push -q origin HEAD:state; then echo "state pushed"; exit 0; fi
  sleep $((i * 3))
  git pull -q --rebase origin state
done
echo "could not push state" >&2; exit 1
