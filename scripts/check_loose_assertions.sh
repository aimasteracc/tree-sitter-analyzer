#!/bin/bash
# Layer-1 CI ratchet: block new loose assertions (>= / > 0 patterns)
#
# Usage:
#   ./scripts/check_loose_assertions.sh [<base-ref>]
#
# Defaults to origin/develop if base-ref not provided.
#
# This script enforces the loose assertion ratchet by:
# 1. Extracting ADDED lines from the PR diff (git diff <base>..HEAD)
# 2. Grepping for loose assertion patterns
# 3. Skipping lines marked with exemption comment: # ratchet: nondeterministic
# 4. Skipping files matching hypothesis property test whitelist (*propert*)
# 5. Exiting non-zero and listing offending lines if any found
#
# Exemption marker (end-of-line):
#   assert x >= 1  # ratchet: nondeterministic <reason>
#
# Whitelist (filenames):
#   *property* or *propert* in the filename skips the entire file
#
# Patterns (conservative, POSIX ERE to avoid false positives):
#   - assert .* >= [0-9]  (>= with digit)
#   - assert .* > 0[^0-9] (> 0 word boundary)
#   - assert len(...) >= [0-9]  (len() with >= digit)
#   - assert len(...) > [0-9]   (len() with > digit)

set -euo pipefail

BASE_REF="${1:-origin/develop}"

# Verify base ref exists
if ! git rev-parse --verify "${BASE_REF}" >/dev/null 2>&1; then
    echo "❌ Base ref not found: ${BASE_REF}"
    exit 1
fi

# Get list of hypothesis property test files (whitelist)
PROPERTY_FILES=$(git diff "${BASE_REF}..HEAD" --name-only -- tests | grep -E '.*[Pp]ropert.*' || true)

# Extract only ADDED lines from the diff, skip lines with exemption marker
VIOLATIONS=""
VIOLATION_COUNT=0

# Use a temporary file to avoid subshell issues
TEMP_DIFF=$(mktemp)
trap "rm -f $TEMP_DIFF" EXIT

git diff "${BASE_REF}..HEAD" -- tests > "$TEMP_DIFF" 2>/dev/null || true

# Read diff line by line, extract ADDED lines (lines starting with '+' that are not '+++')
CURRENT_FILE=""
while IFS= read -r line; do
    # Track which file we're in
    if echo "$line" | grep -q "^diff --git a/"; then
        # Extract filename from: diff --git a/path b/path
        CURRENT_FILE=$(echo "$line" | sed -E 's/^diff --git a\/(.+) b\/.+$/\1/')
        continue
    fi

    # Skip non-addition lines and diff metadata
    if ! echo "$line" | grep -q "^+[^+]"; then
        continue
    fi

    # Strip the leading '+' for content inspection
    content=$(echo "$line" | cut -c2-)

    # Skip blank lines and pure comment lines
    if echo "$content" | grep -qE '^[[:space:]]*$'; then
        continue
    fi
    if echo "$content" | grep -qE '^[[:space:]]*#'; then
        continue
    fi

    # Check if this line has exemption marker
    if echo "$content" | grep -qE '#[[:space:]]*ratchet:[[:space:]]*nondeterministic'; then
        continue
    fi

    # Skip if file is in property test whitelist
    SKIP_PROPERTY=false
    for pfile in $PROPERTY_FILES; do
        if [ "$CURRENT_FILE" = "$pfile" ]; then
            SKIP_PROPERTY=true
            break
        fi
    done
    if [ "$SKIP_PROPERTY" = "true" ]; then
        continue
    fi

    # Check loose assertion patterns (conservative, POSIX ERE)
    # Pattern 1: assert .* >= [0-9]
    if echo "$content" | grep -E 'assert[[:space:]]+.*>=[[:space:]]*[0-9]' > /dev/null; then
        VIOLATIONS+="$CURRENT_FILE: $content"$'\n'
        ((VIOLATION_COUNT++))
        continue
    fi

    # Pattern 2: assert .* > 0[^0-9] (> 0 word boundary)
    if echo "$content" | grep -E 'assert[[:space:]]+.*>[[:space:]]*0[^0-9]' > /dev/null; then
        VIOLATIONS+="$CURRENT_FILE: $content"$'\n'
        ((VIOLATION_COUNT++))
        continue
    fi

    # Pattern 3: assert len(...) >= [0-9]
    if echo "$content" | grep -E 'assert[[:space:]]+.*len\([^)]*\)[[:space:]]*>=[[:space:]]*[0-9]' > /dev/null; then
        VIOLATIONS+="$CURRENT_FILE: $content"$'\n'
        ((VIOLATION_COUNT++))
        continue
    fi

    # Pattern 4: assert len(...) > [0-9]
    if echo "$content" | grep -E 'assert[[:space:]]+.*len\([^)]*\)[[:space:]]*>[[:space:]]*[0-9]' > /dev/null; then
        VIOLATIONS+="$CURRENT_FILE: $content"$'\n'
        ((VIOLATION_COUNT++))
        continue
    fi

done < "$TEMP_DIFF"

if [ $VIOLATION_COUNT -gt 0 ]; then
    echo "❌ Found $VIOLATION_COUNT new loose assertion(s) in the PR diff:"
    echo ""
    echo "$VIOLATIONS"
    echo ""
    echo "Loose assertion patterns detected:"
    echo "  Regex 1: assert .* >= \\d"
    echo "  Regex 2: assert .* > 0[^0-9]"
    echo "  Regex 3: assert len(...) >= [0-9]"
    echo "  Regex 4: assert len(...) > [0-9]"
    echo ""
    echo "To exempt a line, add end-of-line comment:"
    echo "  assert x >= 1  # ratchet: nondeterministic <reason>"
    echo ""
    if [ -n "$PROPERTY_FILES" ]; then
        echo "Property test files (whitelist, skipped):"
        echo "$PROPERTY_FILES"
    fi
    exit 1
fi

exit 0
