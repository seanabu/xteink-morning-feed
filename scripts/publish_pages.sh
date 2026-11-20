#!/usr/bin/env bash
# Publish ./site to the gh-pages branch of origin (replaces the branch contents).
# Usage: scripts/publish_pages.sh [site-dir]
set -euo pipefail
SITE="${1:-site}"
REMOTE="$(git remote get-url origin)"
[ -d "$SITE" ] || { echo "no $SITE folder; run build.py first" >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R "$SITE"/. "$TMP"/
touch "$TMP/.nojekyll"
cd "$TMP"
git init -q -b gh-pages
git add -A
git -c user.name="morning-feed" -c user.email="morning-feed@users.noreply.github.com" \
  commit -q -m "Publish catalog $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q -f "$REMOTE" gh-pages
echo "Pushed $SITE to gh-pages"
