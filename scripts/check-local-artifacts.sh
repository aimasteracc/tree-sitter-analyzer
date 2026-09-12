#!/usr/bin/env bash
# Block local development artifacts from being committed.
# Add patterns here for any file that must never reach the remote repo.
set -euo pipefail

BLOCKED_PATTERNS=(
  "^threads/"
  "^REDESIGN_PROPOSAL\.md$"
)

# Print the blocked-path matches in $1, a newline-separated list of staged paths.
# Always returns 0; callers test whether the output is empty.
#
# This gate watches every staged path, so its coverage invariant is the one
# §3.2 names for a static denylist: the pattern set must be non-empty and each
# pattern must still match, which is what self_check asserts below.
detect_blocked() {
  local staged="$1"
  local matches found=""
  # Guard the loop: under `set -u`, bash 3.2 treats an empty array expansion as
  # an unbound variable, which would crash before the self-check can report it.
  if [[ ${#BLOCKED_PATTERNS[@]} -eq 0 ]]; then
    return 0
  fi
  if [[ -z "$staged" ]]; then
    return 0
  fi
  for pattern in "${BLOCKED_PATTERNS[@]}"; do
    matches=$(printf '%s\n' "$staged" | grep -E "$pattern" || true)
    if [[ -n "$matches" ]]; then
      found="${found}${matches}"$'\n'
    fi
  done
  if [[ -n "$found" ]]; then
    printf '%s' "$found"
  fi
  return 0
}

self_check() {
  local failures=0 got expected

  if [[ ${#BLOCKED_PATTERNS[@]} -eq 0 ]]; then
    echo "  BLOCKED_PATTERNS is empty; the gate cannot fire" >&2
    failures=1
  fi

  # Exact set equality on the real Paths: each pattern must still match, and
  # nothing else may be reported alongside it.
  expected="threads/notes.md"$'\n'
  got=$(detect_blocked "threads/notes.md")
  got="${got}"$'\n'
  if [[ "$got" != "$expected" ]]; then
    echo "  threads/ not detected exactly: expected '$expected', got '$got'" >&2
    failures=1
  fi

  expected="REDESIGN_PROPOSAL.md"$'\n'
  got=$(detect_blocked "REDESIGN_PROPOSAL.md")
  got="${got}"$'\n'
  if [[ "$got" != "$expected" ]]; then
    echo "  REDESIGN_PROPOSAL.md not detected exactly: expected '$expected', got '$got'" >&2
    failures=1
  fi

  # No false positive on ordinary staged paths, including ones that share a
  # prefix or a directory name with a blocked pattern.
  got=$(detect_blocked $'README.md\ntests/unit/test_x.py\nthreads_notes.md\nsub/REDESIGN_PROPOSAL.md')
  if [[ -n "$got" ]]; then
    echo "  innocent staged paths flagged: '$got'" >&2
    failures=1
  fi

  if [[ $failures -ne 0 ]]; then
    echo "check-local-artifacts --self-check FAILED" >&2
    return 1
  fi
  echo "check-local-artifacts --self-check: ${#BLOCKED_PATTERNS[@]} blocked patterns, each matched exactly and none matching innocent paths"
  return 0
}

if [[ "${1:-}" == "--self-check" ]]; then
  self_check
  exit $?
fi

staged=$(git diff --cached --name-only || true)
found=$(detect_blocked "$staged")

if [[ -n "$found" ]]; then
  echo "ERROR: local development artifact staged for commit — unstage it first:"
  printf '%s\n' "$found"
  exit 1
fi

exit 0
