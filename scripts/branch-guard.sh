#!/bin/bash
# scripts/branch-guard.sh — emit a warning to stderr when the working tree
# has drifted off feat/consolidated. Designed to be wired into Claude
# Code's PreToolUse hook for Bash so the agent sees the warning before
# every shell command and can self-correct without losing context.
#
# Behaviour:
#   • Reads tool input from stdin (Claude Code passes JSON there); ignored
#     because we don't need the tool args, just the current branch.
#   • Writes a WARNING to stderr when the current branch differs from the
#     expected one (default: feat/consolidated).
#   • Auto-switch is OPT-IN — set BRANCH_GUARD_AUTOFIX=1 to silently
#     `git checkout` back when WT is clean. Default is warn-only because
#     forcing a branch surprises humans who legitimately moved off the
#     expected branch.
#   • Exits 0 unconditionally — NEVER blocks tool execution.
#
# Environment overrides:
#   BRANCH_GUARD_EXPECTED  — override the canonical branch (default: feat/consolidated)
#   BRANCH_GUARD_AUTOFIX   — set to 1 to enable silent recovery (default: 0, warn-only)
#
# Why this matters:
#   • The Claude Code harness silently resets the working tree to the
#     session-start branch when a background agent stalls past its 600s
#     stream watchdog (observed 3 times in r37fG session). Without this
#     guard the agent doesn't notice the reset until tests fail with
#     "no items collected" or grep finds nothing.
#
# Install via .claude/settings.local.json:
#   "hooks": {
#     "PreToolUse": [{
#       "matcher": "Bash",
#       "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/scripts/branch-guard.sh"}]
#     }]
#   }

set -u

# Drain stdin without using it (Claude Code passes JSON we don't need).
cat >/dev/null 2>&1 || true

# Resolve the project dir — Claude Code sets CLAUDE_PROJECT_DIR; fall
# back to git root then cwd so the hook is robust to manual testing.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$PROJECT_DIR" ]; then
  PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
cd "$PROJECT_DIR" 2>/dev/null || exit 0

EXPECTED_BRANCH="${BRANCH_GUARD_EXPECTED:-feat/consolidated}"
CURRENT_BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null || echo 'DETACHED')"

if [ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]; then
  # Auto-switch mode (OPT-IN — default OFF): silently switch back when WT
  # is clean and no rebase/merge/cherry-pick is in flight. Set
  # BRANCH_GUARD_AUTOFIX=1 to enable. Disabled by default because forcing
  # a branch behind the human's back surprises legitimate workflows.
  if [ "${BRANCH_GUARD_AUTOFIX:-0}" = "1" ]; then
    # Treat runtime/cache artefacts as not-dirty — they get clobbered constantly.
    DIRTY="$(git status --porcelain 2>/dev/null \
      | grep -vE '^(\?\? |.M |.D | M | D )(\.ast-cache|\.claude-flow|\.swarm|\.tree-sitter-cache|ruvector\.db|agentdb\.rvf)' \
      | head -1)"
    INPROGRESS=""
    [ -d "$PROJECT_DIR/.git/rebase-merge" ] && INPROGRESS="rebase-merge"
    [ -d "$PROJECT_DIR/.git/rebase-apply" ] && INPROGRESS="rebase-apply"
    [ -f "$PROJECT_DIR/.git/MERGE_HEAD" ] && INPROGRESS="merge"
    [ -f "$PROJECT_DIR/.git/CHERRY_PICK_HEAD" ] && INPROGRESS="cherry-pick"

    if [ -z "$DIRTY" ] && [ -z "$INPROGRESS" ]; then
      if git checkout "$EXPECTED_BRANCH" >/dev/null 2>&1; then
        echo "branch-guard: AUTO-FIXED — was on '${CURRENT_BRANCH}', switched back to '${EXPECTED_BRANCH}'." >&2
        exit 0
      fi
    fi
  fi

  cat >&2 <<EOF
BRANCH-GUARD WARNING: working tree is on '${CURRENT_BRANCH}', not '${EXPECTED_BRANCH}'.
  • If you didn't intentionally switch, the Claude Code harness probably reset the working tree after a stalled background agent.
  • Recover with:  git checkout ${EXPECTED_BRANCH}
  • If the recovery checkout fails on unstaged changes, first reset runtime files:
      git checkout HEAD -- .claude-flow/ .swarm/ ruvector.db 2>/dev/null
  • Override expected branch:    BRANCH_GUARD_EXPECTED=main
  • Enable auto-switch (opt-in): BRANCH_GUARD_AUTOFIX=1
EOF
fi

exit 0
