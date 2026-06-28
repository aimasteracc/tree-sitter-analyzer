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

# Only check newly added test files (not modifications to existing ones)
new_test_files=$(git diff --cached --name-only --diff-filter=A | grep "^tests/.*\.py$" || true)

if [[ -z "$new_test_files" ]]; then
  exit 0
fi

found=""
for pattern in "${BANNED_PATTERNS[@]}"; do
  matches=$(echo "$new_test_files" | grep "$pattern" || true)
  if [[ -n "$matches" ]]; then
    found="$found\n$matches"
  fi
done

if [[ -n "$found" ]]; then
  echo "ERROR (T-1): banned test file name pattern — add tests to the existing test file instead:"
  echo -e "$found"
  echo ""
  echo "Banned patterns: ${BANNED_PATTERNS[*]}"
  echo "See CLAUDE.md §T-1 for the rule and legitimate exceptions."
  exit 1
fi

exit 0
