#!/bin/bash
# scripts/spawn-isolated-dogfood-worktree.sh — create a git worktree
# pinned to feat/consolidated in a sibling directory so the dogfood
# loop can run isolated from the main checkout.
#
# Why:
#   Claude Code's harness silently resets the working tree on background
#   agent stalls. The reset is bounded to the *current* working tree —
#   a separate worktree at a different path is immune. Use this when
#   running multiple parallel dogfood loops, or when you want to keep
#   the main checkout on main / a feature branch while still iterating.
#
# Usage:
#   bash scripts/spawn-isolated-dogfood-worktree.sh [WORKTREE_PATH]
#
# Default WORKTREE_PATH: ../tree-sitter-analyzer-dogfood

set -euo pipefail

WORKTREE_PATH="${1:-../tree-sitter-analyzer-dogfood}"
WORKTREE_ABS="$(cd "$(dirname "$WORKTREE_PATH")" && pwd)/$(basename "$WORKTREE_PATH")"

if [ -d "$WORKTREE_ABS" ]; then
  echo "ERROR: worktree path already exists: $WORKTREE_ABS" >&2
  exit 1
fi

if ! git show-ref --verify --quiet refs/heads/feat/consolidated; then
  echo "ERROR: feat/consolidated branch does not exist locally." >&2
  exit 1
fi

if git show-ref --verify --quiet refs/heads/dogfood-loop; then
  echo "Reusing existing dogfood-loop branch."
else
  git branch dogfood-loop feat/consolidated
  echo "Created dogfood-loop branch from feat/consolidated."
fi

git worktree add "$WORKTREE_ABS" dogfood-loop

cat <<EOF

Worktree spawned at: $WORKTREE_ABS
cd "$WORKTREE_ABS" to use it.

Fold back when done:
  git checkout feat/consolidated
  git merge --ff-only dogfood-loop
  git worktree remove "$WORKTREE_ABS"
  git branch -d dogfood-loop
EOF
