#!/usr/bin/env bash
# Block local development artifacts from being committed.
# Add patterns here for any file that must never reach the remote repo.
set -euo pipefail

BLOCKED_PATTERNS=(
  "^threads/"
  "^REDESIGN_PROPOSAL\.md$"
)

staged=$(git diff --cached --name-only)
found=""

for pattern in "${BLOCKED_PATTERNS[@]}"; do
  matches=$(echo "$staged" | grep -E "$pattern" || true)
  if [[ -n "$matches" ]]; then
    found="$found\n$matches"
  fi
done

if [[ -n "$found" ]]; then
  echo "ERROR: local development artifact staged for commit — unstage it first:"
  echo -e "$found"
  exit 1
fi

exit 0
