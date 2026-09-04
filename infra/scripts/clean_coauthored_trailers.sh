#!/usr/bin/env bash
# clean_coauthored_trailers.sh — strip Co-authored-by trailers from git log.
#
# Usage: ./clean_coauthored_trailers.sh <commit-range>
# Example: ./clean_coauthored_trailers.sh origin/main..origin/dev
#
# This is INFORMATIONAL — does NOT rewrite history. To apply:
#   git rebase -i <commit-range-base> --exec 'git commit --amend --no-edit -F <(git log -1 --format=%B | grep -v "^Co-authored-by:")'
#
# Why this exists: the project's `gentle-ai-sub-agent` git identity
# produces `Co-authored-by: gentle-ai-sub-agent <sub-agent@local>` on
# squash-merged commits, which violates the project's no-AI-attribution
# canon (see AGENTS.md "Git identity for sub-agent work"). On a future
# release branch (dev -> main) the maintainer can run this script to
# inventory affected commits, then rewrite history with the rebase
# invocation above to strip them.
#
# This script does NOT modify history on its own — history rewrites
# are a maintainer-only operation and require explicit coordination
# with the team.
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "Usage: $0 <commit-range>"
  exit 1
fi
range="$1"
echo "=== Commits with 'Co-authored-by' trailers in range $range ==="
git log "$range" --format='%H %s' | while read -r sha subject; do
  body="$(git log -1 --format='%b' "$sha")"
  if echo "$body" | grep -q '^Co-authored-by:'; then
    echo "$sha $subject"
    echo "$body" | grep '^Co-authored-by:'
    echo "---"
  fi
done