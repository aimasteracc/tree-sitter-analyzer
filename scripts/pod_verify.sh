#!/usr/bin/env bash
# Pod acceptance gate — run after every dev/fix pod reports completion.
#   scripts/pod_verify.sh <branch>
# Checks (exit non-zero on any failure):
#   1. branch exists on origin
#   2. diff vs origin/develop is NON-EMPTY (the #1 pod lie: "pushed" but empty)
#   3. no leftover conflict markers in the diff
#   4. prints the stat so the lead sees exactly what landed
set -euo pipefail
BRANCH="${1:?usage: pod_verify.sh <branch>}"

git fetch origin develop "$BRANCH" --quiet

if ! git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
  echo "FAIL: origin/$BRANCH does not exist" >&2
  exit 1
fi

DIFF_LINES=$(git diff "origin/develop...origin/$BRANCH" | wc -l | tr -d ' ')
if [ "$DIFF_LINES" -eq 0 ]; then
  echo "FAIL: empty diff vs origin/develop — commit likely stranded in a worktree-agent-* branch" >&2
  echo "      salvage: ls .claude/worktrees/ ; git -C <wt> log --oneline -3 ; git cherry-pick <sha>" >&2
  exit 2
fi

if git diff "origin/develop...origin/$BRANCH" | grep -qE "^\+.*(<<<<<<<|>>>>>>>)"; then
  echo "FAIL: conflict markers present in diff" >&2
  exit 3
fi

echo "OK: origin/$BRANCH carries a real diff ($DIFF_LINES diff lines):"
git diff "origin/develop...origin/$BRANCH" --stat | tail -15
