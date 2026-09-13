#!/usr/bin/env bash
# T-1 gate: reject new test files with banned name patterns.
# New test files for existing plugins must be added to the existing test file,
# not as a new file. See CLAUDE.md §T-1 for the full rule.
set -euo pipefail

BANNED_PATTERNS=(
  "_comprehensive"
  "_edge_cases"
  "_coverage"
  "_coverage_boost"
  "_extended"
  "_optimized"
)

# Print the banned-name matches in $1, a newline-separated list of added paths.
# Always returns 0; callers test whether the output is empty.
#
# The watch filter lives here rather than at the call site so the detector and
# its self-check cannot disagree about which paths are in scope. Only paths
# under tests/ are eligible: this gate only owns newly added test files.
detect_banned() {
  local files="$1"
  local eligible matches found=""
  # Guard the loop: under `set -u`, bash 3.2 treats an empty array expansion as
  # an unbound variable, which would crash before the self-check can report it.
  if [[ ${#BANNED_PATTERNS[@]} -eq 0 ]]; then
    return 0
  fi
  eligible=$(printf '%s\n' "$files" | grep "^tests/.*\.py$" || true)
  if [[ -z "$eligible" ]]; then
    return 0
  fi
  for pattern in "${BANNED_PATTERNS[@]}"; do
    matches=$(printf '%s\n' "$eligible" | grep "$pattern" || true)
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

  if [[ ${#BANNED_PATTERNS[@]} -eq 0 ]]; then
    echo "  BANNED_PATTERNS is empty; the detector cannot fire" >&2
    failures=1
  fi

  # Exact set equality: a planted banned name under tests/ is reported, and
  # reported as nothing else.
  expected="tests/test_widget_edge_cases.py"$'\n'
  got=$(detect_banned "tests/test_widget_edge_cases.py")
  got="${got}"$'\n'
  if [[ "$got" != "$expected" ]]; then
    echo "  banned name not detected exactly: expected '$expected', got '$got'" >&2
    failures=1
  fi

  # No false positive on an innocent new test file.
  got=$(detect_banned "tests/test_widget.py")
  if [[ -n "$got" ]]; then
    echo "  innocent name flagged: '$got'" >&2
    failures=1
  fi

  # Coverage invariant: a banned name outside tests/ is outside this gate's
  # watch filter, and must not be reported as though it were inside it.
  got=$(detect_banned "src/widget_edge_cases.py")
  if [[ -n "$got" ]]; then
    echo "  path outside the tests/ filter was reported: '$got'" >&2
    failures=1
  fi

  if [[ $failures -ne 0 ]]; then
    echo "check-test-file-names --self-check FAILED" >&2
    return 1
  fi
  echo "check-test-file-names --self-check: ${#BANNED_PATTERNS[@]} banned patterns; detects a planted banned name under tests/ and ignores one outside the filter"
  return 0
}

if [[ "${1:-}" == "--self-check" ]]; then
  self_check
  exit $?
fi

# Only check newly added test files (not modifications to existing ones)
new_test_files=$(git diff --cached --name-only --diff-filter=A || true)
found=$(detect_banned "$new_test_files")

if [[ -n "$found" ]]; then
  echo "ERROR (T-1): banned test file name pattern — add tests to the existing test file instead:"
  printf '%s\n' "$found"
  echo ""
  echo "Banned patterns: ${BANNED_PATTERNS[*]}"
  echo "See CLAUDE.md §T-1 for the rule and legitimate exceptions."
  exit 1
fi

exit 0
