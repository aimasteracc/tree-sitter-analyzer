#!/usr/bin/env bash
# Integration test for scripts/codemap-sync-check.sh
#
# The fixture is built from the REAL production files (the live tool registry, the
# live tree_sitter_analyzer/cli tree, the live docs/CODEMAPS/*.md), never from a
# hand-written imitation of them. Mutations are derived by cloning a real matching
# line out of those files.
#
# Why that matters (this test previously synthesised an old-shape registry):
# a synthetic fixture keeps passing after production changes shape, so both hook
# detectors silently matched nothing for months while every test stayed green.
# Test 0 closes that permanently by running the hook's own --self-check, which
# asserts EXACT set equality between what the gate can see and the authoritative
# runtime enumerations.
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
REAL_CLI_DIR="tree_sitter_analyzer/cli"
REAL_ARG_GROUPS="$REAL_CLI_DIR/argument_groups"
REAL_ARG_BUILDER="$REAL_CLI_DIR/argument_parser_builder.py"
REAL_STANDALONE="$REAL_CLI_DIR/commands/list_files_cli.py"

for p in "$REAL_REGISTRY" "$REAL_ARG_GROUPS" "$REAL_ARG_BUILDER" "$REAL_STANDALONE" "docs/CODEMAPS"; do
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
# POSIX bracket class, not GNU-only \s: this test must run on macOS/BSD grep too.
REAL_REG_LINE="$(grep -E '^[[:space:]]*\("[a-zA-Z_][a-zA-Z0-9_]*"[[:space:]]*,' "$REPO_ROOT/$REAL_REGISTRY" | head -1)"
if [[ -z "$REAL_REG_LINE" ]]; then
  echo "FATAL: no registration-shaped line found in $REAL_REGISTRY — fixture cannot be derived." >&2
  exit 2
fi
NEW_REG_LINE="$(printf '%s\n' "$REAL_REG_LINE" | sed -E 's/\("[a-zA-Z_][a-zA-Z0-9_]*"/("tsa_fixture_facade"/')"

# A real add_argument( bearing file out of the live argument-group modules.
REAL_ARG_SRC="$(grep -rlE 'add_argument\(' "$REPO_ROOT/$REAL_ARG_GROUPS"/*.py | head -1)"
if [[ -z "$REAL_ARG_SRC" ]]; then
  echo "FATAL: no add_argument( call found under $REAL_ARG_GROUPS — fixture cannot be derived." >&2
  exit 2
fi
REAL_ARG_REL="$REAL_ARG_GROUPS/$(basename "$REAL_ARG_SRC")"

FIXTURE_FLAG_SNIPPET='

def _tsa_fixture_group(parser):
    parser.add_argument("--tsa-fixture-flag", help="fixture flag")
'

# Build the fixture repo ONCE: a clean git repo seeded with copies of the real
# production files plus a "baseline" commit, so `git diff --cached` behaves the
# way it does in real usage. Per-test isolation is then a cheap `reset --hard`
# rather than re-copying the whole cli tree 20+ times.
setup_repo() {
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
           tree_sitter_analyzer/languages \
           tree_sitter_analyzer/formatters \
           docs/CODEMAPS

  cp "$REPO_ROOT/$REAL_REGISTRY" "$REAL_REGISTRY"
  # The whole cli tree: the flag surface includes the find-and-grep / list-files /
  # search-content console scripts, not just argument_groups.
  cp -R "$REPO_ROOT/$REAL_CLI_DIR" "$REAL_CLI_DIR"
  find "$REAL_CLI_DIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
  cp "$REPO_ROOT"/docs/CODEMAPS/*.md docs/CODEMAPS/

  git add -A >/dev/null 2>&1
  git commit -q -m "baseline"
}

# Restore the fixture to its baseline commit between tests.
init_repo() {
  cd "$WORK/repo"
  git reset -q --hard HEAD
  git clean -qfd
  # languages/ and formatters/ hold no tracked files in the fixture, so
  # `git clean -fd` deletes them; the new-plugin / new-formatter tests need them.
  mkdir -p tree_sitter_analyzer/languages tree_sitter_analyzer/formatters
  rm -f .git/codemap-sync-bypass.log
}

# NOTE: every hook invocation must go through a helper that ENDS on a successful
# command. This shell fires the ERR trap for a failing command-substitution
# assignment even under `set +e`, so a bare RC="$(... exit 1 ...)" aborts the run.
run_hook() {
  # Return the hook's exit code without aborting due to set -e.
  set +e
  bash "$HOOK_SCRIPT" >/dev/null 2>&1
  local rc=$?
  set -e
  echo "$rc"
}

# Same, but with env assignments applied and combined output captured to
# $WORK/hook.out for assertions about what the hook actually said.
run_hook_env() {
  set +e
  env "$@" bash "$HOOK_SCRIPT" > "$WORK/hook.out" 2>&1
  local rc=$?
  set -e
  echo "$rc"
}

run_self_check() {
  set +e
  (cd "$REPO_ROOT" && bash "$HOOK_SCRIPT" --self-check) > "$WORK/selfcheck.out" 2>&1
  local rc=$?
  set -e
  echo "$rc"
}

run_hook_arg() {
  set +e
  bash "$HOOK_SCRIPT" "$1" >/dev/null 2>&1
  local rc=$?
  set -e
  echo "$rc"
}

# Run the hook with an extra global gitconfig in force, to prove that no
# developer diff.* / core.* setting can change the verdict.
run_hook_with_gitconfig() {
  local config_body="$1"
  local cfg="$WORK/extra-gitconfig"
  printf '%s\n' "$config_body" > "$cfg"
  set +e
  GIT_CONFIG_GLOBAL="$cfg" GIT_CONFIG_NOSYSTEM=1 bash "$HOOK_SCRIPT" >/dev/null 2>&1
  local rc=$?
  set -e
  echo "$rc"
}

setup_repo

# --- Test 0: detectors still match the real production surface -----------
# The anti-staleness guard. --self-check asserts EXACT set equality between the
# gate's static extractor and the authoritative runtime enumerations, plus the
# coverage invariant (zero add_argument flags under cli/** outside the filter).
CURRENT_TEST="0: hook --self-check against real production files"
RC="$(run_self_check)"
SELF_CHECK_OUT="$(cat "$WORK/selfcheck.out")"
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
CURRENT_TEST="4: CLI flag add in argument_groups, no codemap"
init_repo
printf '%s' "$FIXTURE_FLAG_SNIPPET" >> "$REAL_ARG_REL"
git add "$REAL_ARG_REL" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 5: CLI flag added in argument_groups WITH cli.md → PASS --------
CURRENT_TEST="5: CLI flag add in argument_groups + codemap"
init_repo
printf '%s' "$FIXTURE_FLAG_SNIPPET" >> "$REAL_ARG_REL"
echo "| --tsa-fixture-flag | fixture |" >> docs/CODEMAPS/cli.md
git add "$REAL_ARG_REL" docs/CODEMAPS/cli.md >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 6: CLI flag added in argument_parser_builder → BLOCK -----------
CURRENT_TEST="6: CLI flag add in argument_parser_builder, no codemap"
init_repo
printf '%s' "$FIXTURE_FLAG_SNIPPET" >> "$REAL_ARG_BUILDER"
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

# --- Test 10: SKIP_CODEMAP_SYNC=1 no longer silently bypasses ------------
# Reviewer P2-3: pre-commit only surfaces output from FAILING hooks, so the old
# warn-and-exit-0 bypass was invisible; `export SKIP_CODEMAP_SYNC=1` disabled the
# gate for an entire session with zero signal. =1 must now fail visibly.
CURRENT_TEST="10: SKIP_CODEMAP_SYNC=1 fails visibly instead of silently passing"
init_repo
printf '%s\n' "$NEW_REG_LINE" >> "$REAL_REGISTRY"
git add "$REAL_REGISTRY" >/dev/null 2>&1
RC="$(run_hook_env SKIP_CODEMAP_SYNC=1)"
SKIP_OUT="$(cat "$WORK/hook.out")"
if [[ "$RC" == "1" && "$SKIP_OUT" != *"SKIP_CODEMAP_SYNC=force"* ]]; then
  RC="no-force-guidance"
fi
report "$CURRENT_TEST" 1 "$RC"

# --- Test 11: SKIP_CODEMAP_SYNC=force bypasses, on the record ------------
CURRENT_TEST="11: SKIP_CODEMAP_SYNC=force bypasses and logs an audit line"
init_repo
printf '%s\n' "$NEW_REG_LINE" >> "$REAL_REGISTRY"
git add "$REAL_REGISTRY" >/dev/null 2>&1
RC="$(run_hook_env SKIP_CODEMAP_SYNC=force)"
if [[ "$RC" == "0" && ! -s "$WORK/repo/.git/codemap-sync-bypass.log" ]]; then
  RC="no-audit-log"
fi
report "$CURRENT_TEST" 0 "$RC"

# --- Test 12: diff.noprefix=true cannot kill the gate -------------------
# Reviewer P1-1: the old detector anchored on the literal "b/<path>$" diff header,
# so this widely-copied dotfile setting made the gate exit 0 for EVERY file while
# --self-check still printed OK. The gate no longer parses diff text at all.
CURRENT_TEST="12: diff.noprefix=true still blocks"
init_repo
printf '%s\n' "$NEW_REG_LINE" >> "$REAL_REGISTRY"
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook_with_gitconfig '[diff]
	noprefix = true')"

# --- Test 13: diff.mnemonicPrefix=true cannot kill the gate -------------
# Reviewer P1-1: produced 'diff --git c/... i/...' headers, same silent death.
CURRENT_TEST="13: diff.mnemonicPrefix=true still blocks"
init_repo
printf '%s' "$FIXTURE_FLAG_SNIPPET" >> "$REAL_ARG_REL"
git add "$REAL_ARG_REL" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook_with_gitconfig '[diff]
	mnemonicPrefix = true')"

# --- Test 14: standalone console-script flags are watched ---------------
# Reviewer P1-3: 82 of 405 add_argument calls lived in cli/commands/*_cli*.py —
# documented console entry points in docs/CODEMAPS/cli.md — and were unwatched.
CURRENT_TEST="14: CLI flag add in a standalone console script, no codemap"
init_repo
printf '%s' "$FIXTURE_FLAG_SNIPPET" >> "$REAL_STANDALONE"
git add "$REAL_STANDALONE" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 15: renaming a registry parameter is not a surface change ------
# Reviewer P2-1: a 60+/60- rename diff added zero tools yet false-blocked.
CURRENT_TEST="15: registry parameter rename does not block"
init_repo
sed -i.bak 's/project_root/proj_root/g' "$REAL_REGISTRY" && rm -f "$REAL_REGISTRY.bak"
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 16: reordering the registrations is not a surface change -------
# Reviewer P2-2: alphabetising the 8 existing registrations false-blocked.
CURRENT_TEST="16: reordering registrations does not block"
init_repo
python - "$REAL_REGISTRY" <<'PY'
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    lines = fh.readlines()
entry = re.compile(r'^\s*\("[a-zA-Z_][a-zA-Z0-9_]*"\s*,')
idx = [i for i, line in enumerate(lines) if entry.match(line)]
block = sorted(lines[i] for i in idx)
for slot, line in zip(idx, block):
    lines[slot] = line
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(lines)
PY
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 17: a comment mentioning add_argument( is not a flag ----------
# Reviewer P2-4: "# NOTE: do not call parser.add_argument( here" false-blocked.
CURRENT_TEST="17: comment mentioning add_argument( does not block"
init_repo
printf '\n# NOTE: do not call parser.add_argument("--nope") here.\n' >> "$REAL_ARG_REL"
git add "$REAL_ARG_REL" >/dev/null 2>&1
report "$CURRENT_TEST" 0 "$(run_hook)"

# --- Test 18: a dict-literal registration is caught ---------------------
# Reviewer: added-line matching missed this shape entirely.
CURRENT_TEST="18: dict-literal registration, no codemap"
init_repo
cat >> "$REAL_REGISTRY" <<'PY'


def _fixture_extra_registry(project_root):
    return {"tsa_dict_facade": build_search_facade(project_root)}
PY
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 19: an append-in-a-loop registration is caught ----------------
CURRENT_TEST="19: append-in-a-loop registration, no codemap"
init_repo
cat >> "$REAL_REGISTRY" <<'PY'


def _fixture_append_registry(project_root, sink):
    for _ in range(1):
        sink.append(("tsa_append_facade", build_search_facade(project_root)))
PY
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 20: REMOVING a tool from the surface is caught ----------------
# Reviewer P3-3: added-line matching structurally cannot see a removal.
CURRENT_TEST="20: registry removal, no codemap"
init_repo
python - "$REAL_REGISTRY" <<'PY'
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    lines = fh.readlines()
entry = re.compile(r'^\s*\("[a-zA-Z_][a-zA-Z0-9_]*"\s*,')
for i, line in enumerate(lines):
    if entry.match(line):
        del lines[i]
        break
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(lines)
PY
git add "$REAL_REGISTRY" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 21: a non-ASCII staged path does not bypass the gate ----------
# Reviewer P3-4: under default core.quotePath, git quotes such paths in
# --name-only output and the old literal path match failed to see them.
CURRENT_TEST="21: non-ASCII staged path still blocks"
init_repo
printf 'def _cafe(parser):\n    parser.add_argument("--tsa-cafe-flag", help="fixture")\n' \
  > "$REAL_ARG_GROUPS/_café.py"
git add "$REAL_ARG_GROUPS/_café.py" >/dev/null 2>&1
report "$CURRENT_TEST" 1 "$(run_hook)"

# --- Test 22: an unknown argument is an error, not a silent gate run ----
# Reviewer P3-5: the typo `--selfcheck` fell through to gate mode with no output.
CURRENT_TEST="22: unknown argument is rejected"
init_repo
RC="$(run_hook_arg --selfcheck)"
report "$CURRENT_TEST" 2 "$RC"

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
