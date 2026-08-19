#!/usr/bin/env bash
# Integration test for scripts/codemap-sync-check.sh
#
# The fixture is built from the REAL production files (the live tool registry,
# the live CLI argument-group modules, the live docs/CODEMAPS/*.md), never from
# a hand-written imitation of them. Mutations are derived by cloning a real
# matching line out of those files.
#
# Why that matters (this test previously synthesised an old-shape registry):
# a synthetic fixture keeps passing after production changes shape, so both hook
# detectors silently matched nothing for months while every test stayed green.
# Test 0 below closes that hole permanently: it runs the hook's own --self-check,
# which applies each detector's real regex to the real production paths and
# fails when a detector stops matching anything.
#
# Run: bash tests/integration/test_codemap_sync_hook.sh

set -euo pipefail

# --- locate the script under test relative to this test file -------------
TEST_FILE="${BASH_SOURCE[0]}"
TEST_DIR="$(cd "$(dirname "$TEST_FILE")" && pwd)"
REPO_ROOT="$(cd "$TEST_DIR/../.." && pwd)"
HOOK_SCRIPT="$REPO_ROOT/scripts/codemap-sync-check.sh"

if [[ ! -f "$HOOK_SCRIPT" ]]; then
  echo "FATAL: hook script not found: $HOOK_SCRIPT" >&2
  exit 2
fi

# --- real production paths the hook guards -------------------------------
REAL_REGISTRY="tree_sitter_analyzer/mcp/_tool_registry.py"
REAL_ARG_GROUPS="tree_sitter_analyzer/cli/argument_groups"
REAL_ARG_BUILDER="tree_sitter_analyzer/cli/argument_parser_builder.py"

for p in "$REAL_REGISTRY" "$REAL_ARG_GROUPS" "$REAL_ARG_BUILDER" "docs/CODEMAPS"; do
  if [[ ! -e "$REPO_ROOT/$p" ]]; then
    echo "FATAL: production path missing, fixture cannot be built from reality: $p" >&2
    exit 2
  fi
done

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

# --- mutation lines cloned from the real files ---------------------------
# A real registration line, e.g.  ("search", build_search_facade(project_root)),
# renamed so the fixture adds a *new* entry rather than re-adding an old one.
REAL_REG_LINE="$(grep -E '^\s*\("[a-zA-Z_][a-zA-Z0-9_]*"\s*,' "$REPO_ROOT/$REAL_REGISTRY" | head -1)"
if [[ -z "$REAL_REG_LINE" ]]; then
  echo "FATAL: no registration-shaped line found in $REAL_REGISTRY — fixture cannot be derived." >&2
  exit 2
fi
NEW_REG_LINE="$(printf '%s\n' "$REAL_REG_LINE" | sed -E 's/\("[a-zA-Z_][a-zA-Z0-9_]*"/("tsa_fixture_facade"/')"

# A real `add_argument(` line out of the live argument-group modules.
REAL_ARG_SRC="$(grep -rlE 'add_argument\(' "$REPO_ROOT/$REAL_ARG_GROUPS"/*.py | head -1)"
if [[ -z "$REAL_ARG_SRC" ]]; then
  echo "FATAL: no add_argument( call found under $REAL_ARG_GROUPS — fixture cannot be derived." >&2
  exit 2
fi
REAL_ARG_REL="$REAL_ARG_GROUPS/$(basename "$REAL_ARG_SRC")"

# Initialize a clean git repo seeded with copies of the real production files
# plus a "baseline" commit, so `git diff --cached` behaves the way it does in
# real usage.
init_repo() {
  rm -rf "$WORK/repo"
  mkdir -p "$WORK/repo"
  cd "$WORK/repo"
  git init -q -b main
  git config user.email "test@example.com"
  git config user.name "tsa-test"
  git config commit.gpgsign false
  # Keep the fixture byte-identical to the real files; also silences the
  # per-file CRLF warnings that would otherwise bury the test report.
  git config core.autocrlf false

  mkdir -p "$(dirname "$REAL_REGISTRY")" \
           "$REAL_ARG_GROUPS" \
           tree_sitter_analyzer/languages \
           tree_sitter_analyzer/formatters \
           docs/CODEMAPS

  cp "$REPO_ROOT/$REAL_REGISTRY" "$REAL_REGISTRY"
  cp "$REPO_ROOT/$REAL_ARG_BUILDER" "$REAL_ARG_BUILDER"
  cp "$REPO_ROOT/$REAL_ARG_GROUPS"/*.py "$REAL_ARG_GROUPS/"
  cp "$REPO_ROOT"/docs/CODEMAPS/*.md docs/CODEMAPS/

  git add -A >/dev/null 2>&1
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

# --- Test 0: detectors still match the real production shape -------------
# This is the anti-staleness guard. --self-check applies every detector regex
# to the live files in this repo; a detector that matches nothing is dead and
# must fail here, not silently stop gating.
CURRENT_TEST="0: hook --self-check against real production files"
set +e
SELF_CHECK_OUT="$(cd "$REPO_ROOT" && bash "$HOOK_SCRIPT" --self-check 2>&1)"
RC=$?
set -e
# An unimplemented/ignored --self-check would exit 0 having done nothing, so
# require the OK marker as well: a silent pass is the exact failure mode this
# test exists to prevent.
if [[ "$RC" == "0" && "$SELF_CHECK_OUT" != *"[codemap-sync] self-check OK"* ]]; then
  RC="no-self-check-marker"
fi
report "$CURRENT_TEST" 0 "$RC"

# --- Test 1: registry facade registration without codemap → BLOCK --------
CURRENT_TEST="1: registry facade add, no codemap"
init_repo
printf '%s\n' "$NEW_REG_LINE" >> "$REAL_REGISTRY"
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 2: registry facade registration WITH codemap → PASS ------------
CURRENT_TEST="2: registry facade add + codemap"
init_repo
printf '%s\n' "$NEW_REG_LINE" >> "$REAL_REGISTRY"
echo "| tsa_fixture_facade | fixture |" >> docs/CODEMAPS/mcp-tools.md
git add "$REAL_REGISTRY" docs/CODEMAPS/mcp-tools.md >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 3: comment-only edit to the registry → PASS --------------------
CURRENT_TEST="3: registry comment-only change"
init_repo
printf '\n# fixture: prose-only edit, registers nothing.\n' >> "$REAL_REGISTRY"
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 4: CLI flag added in argument_groups without cli.md → BLOCK ----
CURRENT_TEST="4: CLI arg add in argument_groups, no codemap"
init_repo
cat >> "$REAL_ARG_REL" <<'PY'


def _tsa_fixture_group(parser):
    parser.add_argument("--tsa-fixture-flag", help="fixture flag")
PY
git add "$REAL_ARG_REL" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 5: CLI flag added in argument_groups WITH cli.md → PASS --------
CURRENT_TEST="5: CLI arg add in argument_groups + codemap"
init_repo
cat >> "$REAL_ARG_REL" <<'PY'


def _tsa_fixture_group(parser):
    parser.add_argument("--tsa-fixture-flag", help="fixture flag")
PY
echo "| --tsa-fixture-flag | fixture |" >> docs/CODEMAPS/cli.md
git add "$REAL_ARG_REL" docs/CODEMAPS/cli.md >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 6: CLI flag added in argument_parser_builder → BLOCK -----------
CURRENT_TEST="6: CLI arg add in argument_parser_builder, no codemap"
init_repo
cat >> "$REAL_ARG_BUILDER" <<'PY'


def _tsa_fixture_builder_flag(parser):
    parser.add_argument("--tsa-fixture-builder-flag", help="fixture flag")
PY
git add "$REAL_ARG_BUILDER" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 7: docs-only change → PASS (false-positive guard) --------------
CURRENT_TEST="7: docs-only change"
init_repo
echo "| --docs-only-row | no code change |" >> docs/CODEMAPS/cli.md
echo "| docs-only-row | no code change |" >> docs/CODEMAPS/mcp-tools.md
git add docs/CODEMAPS/cli.md docs/CODEMAPS/mcp-tools.md >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 8: new language plugin without languages.md → BLOCK ------------
CURRENT_TEST="8: new language plugin, no codemap"
init_repo
cat > tree_sitter_analyzer/languages/fake_plugin.py <<'PY'
"""Fake language plugin."""
PY
git add tree_sitter_analyzer/languages/fake_plugin.py >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 9: new formatter without formatters.md → BLOCK -----------------
CURRENT_TEST="9: new formatter, no codemap"
init_repo
cat > tree_sitter_analyzer/formatters/fake_formatter.py <<'PY'
"""Fake formatter."""
PY
git add tree_sitter_analyzer/formatters/fake_formatter.py >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 10: registry change + SKIP_CODEMAP_SYNC=1 → PASS ---------------
CURRENT_TEST="10: SKIP_CODEMAP_SYNC escape hatch"
init_repo
printf '%s\n' "$NEW_REG_LINE" >> "$REAL_REGISTRY"
git add "$REAL_REGISTRY" >/dev/null 2>&1
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
