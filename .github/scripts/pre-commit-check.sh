#!/bin/bash
# Git Pre-Commit Hook
# 自动在提交前运行 CI 检查

# 只检查已 staged 的文件
STAGED_PY_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)

if [ -z "$STAGED_PY_FILES" ]; then
    echo "No Python files staged, skipping CI checks"
    exit 0
fi

echo "🔍 Running pre-commit CI checks on staged files..."
echo ""

# Run Ruff on staged files only
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Ruff Check (staged files)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for file in $STAGED_PY_FILES; do
    if ! uv run ruff check "$file"; then
        echo ""
        echo "❌ Ruff check failed for: $file"
        echo "💡 Run 'uv run ruff check $file --fix' to auto-fix"
        exit 1
    fi
done
echo "✅ Ruff: PASSED"
echo ""

# Run MyPy on staged files
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "MyPy Check (staged files in tree_sitter_analyzer/)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TSA_FILES=$(echo "$STAGED_PY_FILES" | grep '^tree_sitter_analyzer/' || true)
if [ -n "$TSA_FILES" ]; then
    if ! uv run mypy $TSA_FILES --strict; then
        echo ""
        echo "❌ MyPy check failed"
        exit 1
    fi
    echo "✅ MyPy: PASSED"
else
    echo "⏭️  No files in tree_sitter_analyzer/, skipping MyPy"
fi
echo ""

echo "✅ All pre-commit checks passed!"
