#!/bin/bash
# Check completeness of all supported languages
#
# Usage: ./scripts/check_all_languages.sh

set -e

echo "================================================"
echo "Checking completeness of all supported languages"
echo "================================================"
echo ""

# Define all supported languages
declare -A LANGUAGES=(
    ["java"]="java"
    ["python"]="py"
    ["csharp"]="cs"
    ["javascript"]="js"
    ["typescript"]="ts"
    ["sql"]="sql"
    ["html"]="html"
    ["css"]="css"
    ["markdown"]="md"
)

TOTAL_LANGS=0
COMPLETE_LANGS=0

for LANG in "${!LANGUAGES[@]}"; do
    EXT="${LANGUAGES[$LANG]}"
    TOTAL_LANGS=$((TOTAL_LANGS + 1))

    echo "--- Checking $LANG ---"

    if ./scripts/check_language_completeness.sh "$LANG" "$EXT" > /dev/null 2>&1; then
        echo "✓ $LANG is complete"
        COMPLETE_LANGS=$((COMPLETE_LANGS + 1))
    else
        echo "✗ $LANG is incomplete"
    fi
    echo ""
done

echo "================================================"
echo "Summary: $COMPLETE_LANGS/$TOTAL_LANGS languages are complete"
echo "================================================"

if [ $COMPLETE_LANGS -eq $TOTAL_LANGS ]; then
    echo "✓ All languages are complete!"
    exit 0
else
    INCOMPLETE=$((TOTAL_LANGS - COMPLETE_LANGS))
    echo "✗ $INCOMPLETE language(s) are incomplete"
    echo ""
    echo "Run individual checks for details:"
    echo "  ./scripts/check_language_completeness.sh <language> <extension>"
    exit 1
fi
