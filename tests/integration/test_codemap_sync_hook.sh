#!/usr/bin/env bash
# Integration test for scripts/codemap-sync-check.sh
#
# Runs 7 synthetic git states in an isolated temp repo and asserts the
# hook's exit code matches the expected outcome.
#
# Self-contained: no fixture files, no taint on the real repo.
#
# Run: bash tests/integration/test_codemap_sync_hook.sh

set -euo pipefail

# --- locate the script under test relative to this test file -------------
TEST_FILE="${BASH_SOURCE[0]}"
TEST_DIR="$(cd "$(dirname "$TEST_FILE")" && pwd)"
REPO_ROOT="$(cd "$TEST_DIR/../.." && pwd)"
HOOK_SCRIPT="$REPO_ROOT/scripts/codemap-sync-check.sh"

if [[ ! -x "$HOOK_SCRIPT" ]]; then
  echo "FATAL: hook script not executable: $HOOK_SCRIPT" >&2
  exit 2
fi

# --- temp workspace ------------------------------------------------------
WORK="$(mktemp -d -t tsa-codemap-sync-XXXXXX)"
CURRENT_TEST="<startup>"
cleanup() {
  rm -rf "$WORK"
}
on_err() {
  echo "" >&2
  echo "FAIL: test '$CURRENT_TEST' errored out (line $1)" >&2
  cleanup
  exit 1
}
trap 'on_err $LINENO' ERR
trap cleanup EXIT

PASS=0
FAIL=0
report() {
  local name="$1" want="$2" got="$3"
  if [[ "$want" == "$got" ]]; then
    echo "  PASS  $name  (exit=$got)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name  (expected exit=$want, got exit=$got)"
    FAIL=$((FAIL + 1))
  fi
}

# Initialize a clean git repo with a "baseline" commit so `git diff --cached`
# behaves the same way it does in real usage.
init_repo() {
  rm -rf "$WORK/repo"
  mkdir -p "$WORK/repo"
  cd "$WORK/repo"
  git init -q -b main
  git config user.email "test@example.com"
  git config user.name "tsa-test"
  git config commit.gpgsign false
  mkdir -p tree_sitter_analyzer/mcp \
           tree_sitter_analyzer/cli \
           tree_sitter_analyzer/languages \
           tree_sitter_analyzer/formatters \
           docs/CODEMAPS

  # Baseline registry — already has one tool, no new ones added in baseline.
  cat > tree_sitter_analyzer/mcp/_tool_registry.py <<'PY'
"""Tool registry."""
def build_registry(project_root):
    return [
        ("check_code_scale", AnalyzeScaleTool(project_root)),
    ]
PY

  cat > tree_sitter_analyzer/cli/argument_parser_builder.py <<'PY'
"""CLI parser."""
def build_parser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    return parser
PY

  cat > docs/CODEMAPS/mcp-tools.md <<'MD'
# MCP Tools
| tool | description |
| ---- | ----------- |
| check_code_scale | scale check |
MD
  cat > docs/CODEMAPS/cli.md <<'MD'
# CLI
| flag | description |
| ---- | ----------- |
| file_path | positional |
MD
  cat > docs/CODEMAPS/languages.md <<'MD'
# Languages
MD
  cat > docs/CODEMAPS/formatters.md <<'MD'
# Formatters
MD

  git add -A >/dev/null
  git commit -q -m "baseline"
}

run_hook() {
  # Return the hook's exit code without aborting due to set -e.
  set +e
  bash "$HOOK_SCRIPT" >/dev/null 2>&1
  local rc=$?
  set -e
  echo "$rc"
}

# --- Test 1: registry change without codemap → BLOCK ---------------------
CURRENT_TEST="1: registry add, no codemap"
init_repo
cat >> tree_sitter_analyzer/mcp/_tool_registry.py <<'PY'
        ("codegraph_NEW_TOOL", CodeGraphNewTool(project_root)),
PY
git add tree_sitter_analyzer/mcp/_tool_registry.py >/dev/null
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 2: registry change WITH codemap → PASS -------------------------
CURRENT_TEST="2: registry add + codemap"
init_repo
cat >> tree_sitter_analyzer/mcp/_tool_registry.py <<'PY'
        ("codegraph_NEW_TOOL", CodeGraphNewTool(project_root)),
PY
echo "| codegraph_NEW_TOOL | new |" >> docs/CODEMAPS/mcp-tools.md
git add tree_sitter_analyzer/mcp/_tool_registry.py docs/CODEMAPS/mcp-tools.md >/dev/null
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 3: docstring-only edit → PASS (false-positive guard) -----------
CURRENT_TEST="3: docstring-only change"
init_repo
# Rewrite the docstring but add NO new tool entries.
cat > tree_sitter_analyzer/mcp/_tool_registry.py <<'PY'
"""Tool registry — now with a longer docstring explaining design intent."""
def build_registry(project_root):
    return [
        ("check_code_scale", AnalyzeScaleTool(project_root)),
    ]
PY
git add tree_sitter_analyzer/mcp/_tool_registry.py >/dev/null
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 4: CLI add_argument without cli.md → BLOCK ---------------------
CURRENT_TEST="4: CLI arg add, no codemap"
init_repo
cat >> tree_sitter_analyzer/cli/argument_parser_builder.py <<'PY'
def add_new_flag(parser):
    parser.add_argument("--new-flag", help="brand new flag")
PY
git add tree_sitter_analyzer/cli/argument_parser_builder.py >/dev/null
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 5: new language plugin without languages.md → BLOCK ------------
CURRENT_TEST="5: new language plugin, no codemap"
init_repo
cat > tree_sitter_analyzer/languages/fake_plugin.py <<'PY'
"""Fake language plugin."""
PY
git add tree_sitter_analyzer/languages/fake_plugin.py >/dev/null
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 6: new formatter without formatters.md → BLOCK -----------------
CURRENT_TEST="6: new formatter, no codemap"
init_repo
cat > tree_sitter_analyzer/formatters/fake_formatter.py <<'PY'
"""Fake formatter."""
PY
git add tree_sitter_analyzer/formatters/fake_formatter.py >/dev/null
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 7: registry change + SKIP_CODEMAP_SYNC=1 → PASS ----------------
CURRENT_TEST="7: SKIP_CODEMAP_SYNC escape hatch"
init_repo
cat >> tree_sitter_analyzer/mcp/_tool_registry.py <<'PY'
        ("codegraph_NEW_TOOL", CodeGraphNewTool(project_root)),
PY
git add tree_sitter_analyzer/mcp/_tool_registry.py >/dev/null
set +e
SKIP_CODEMAP_SYNC=1 bash "$HOOK_SCRIPT" >/dev/null 2>&1
RC=$?
set -e
report "$CURRENT_TEST" 0 "$RC"

# --- summary -------------------------------------------------------------
echo ""
echo "===================================================="
echo "  codemap-sync-check.sh integration test summary"
echo "  PASS: $PASS    FAIL: $FAIL    TOTAL: $((PASS + FAIL))"
echo "===================================================="

if (( FAIL > 0 )); then
  exit 1
fi
exit 0
