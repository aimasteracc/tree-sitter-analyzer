#!/bin/bash
# Language Completeness Checker
#
# Usage: ./scripts/check_language_completeness.sh <language> <extension>
# Example: ./scripts/check_language_completeness.sh csharp cs

set -e

LANG=$1
EXT=$2

if [ -z "$LANG" ] || [ -z "$EXT" ]; then
    echo "Usage: $0 <language> <extension>"
    echo "Example: $0 csharp cs"
    exit 1
fi

echo "================================================"
echo "Language Completeness Check: $LANG"
echo "================================================"
echo ""

TOTAL=0
PASSED=0

check_item() {
    local description=$1
    local condition=$2

    TOTAL=$((TOTAL + 1))

    if eval "$condition"; then
        echo "✓ $description"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo "✗ $description"
        return 1
    fi
}

echo "=== Core Components ==="
check_item "Plugin file exists" "[ -f 'tree_sitter_analyzer/languages/${LANG}_plugin.py' ]"
check_item "Query file exists" "[ -f 'tree_sitter_analyzer/queries/${LANG}.py' ]"
check_item "Formatter file exists" "[ -f 'tree_sitter_analyzer/formatters/${LANG}_formatter.py' ]"
echo ""

echo "=== Configuration ==="
check_item "Entry point registered in pyproject.toml" "grep -q '${LANG} = ' pyproject.toml"
check_item "Formatter config in formatter_config.py" "grep -q '\"${LANG}\":' tree_sitter_analyzer/formatters/formatter_config.py"
check_item "Formatter registered in factory" "grep -q '${LANG}' tree_sitter_analyzer/formatters/language_formatter_factory.py"
check_item "Language detector configured" "grep -q '\"\.${EXT}\"' tree_sitter_analyzer/language_detector.py"
echo ""

echo "=== Plugin Methods ==="
if [ -f "tree_sitter_analyzer/languages/${LANG}_plugin.py" ]; then
    check_item "get_queries() method exists" "grep -q 'def get_queries' tree_sitter_analyzer/languages/${LANG}_plugin.py"
    check_item "execute_query_strategy() method exists" "grep -q 'def execute_query_strategy' tree_sitter_analyzer/languages/${LANG}_plugin.py"
    check_item "get_element_categories() method exists" "grep -q 'def get_element_categories' tree_sitter_analyzer/languages/${LANG}_plugin.py"
else
    echo "⊘ Plugin methods check skipped (plugin file missing)"
    TOTAL=$((TOTAL + 3))
fi
echo ""

echo "=== Formatter Methods ==="
if [ -f "tree_sitter_analyzer/formatters/${LANG}_formatter.py" ]; then
    check_item "_format_full_table() method exists" "grep -q 'def _format_full_table' tree_sitter_analyzer/formatters/${LANG}_formatter.py"
    check_item "_format_compact_table() method exists" "grep -q 'def _format_compact_table' tree_sitter_analyzer/formatters/${LANG}_formatter.py"
    check_item "_format_csv() method exists" "grep -q 'def _format_csv' tree_sitter_analyzer/formatters/${LANG}_formatter.py"
else
    echo "⊘ Formatter methods check skipped (formatter file missing)"
    TOTAL=$((TOTAL + 3))
fi
echo ""

echo "=== Samples and Tests ==="
check_item "Sample file exists (examples/Sample.${EXT})" "[ -f 'examples/Sample.${EXT}' ]"
check_item "Test file exists (tests/test_languages/test_${LANG}_plugin.py)" "[ -f 'tests/test_languages/test_${LANG}_plugin.py' ]"
echo ""

echo "=== Documentation ==="
check_item "README.md mentions language" "grep -iq '${LANG}' README.md"
check_item "CHANGELOG.md mentions language" "grep -iq '${LANG}' CHANGELOG.md"
echo ""

echo "================================================"
echo "Results: $PASSED/$TOTAL checks passed"
echo "================================================"

if [ $PASSED -eq $TOTAL ]; then
    echo "✓ Language implementation is COMPLETE!"
    exit 0
else
    FAILED=$((TOTAL - PASSED))
    echo "✗ Language implementation is INCOMPLETE ($FAILED checks failed)"
    echo ""
    echo "Please review the failed checks above and complete the missing components."
    exit 1
fi
