#!/usr/bin/env bash
# codemap-sync-check.sh
#
# Pre-commit gate (Lane A of doc-sync).
# Blocks commits that change a registry/CLI/language/formatter surface
# WITHOUT staging the corresponding docs/CODEMAPS/*.md update.
#
# Detection is by DIFF CONTENT, not file touch — a docstring tweak on
# _tool_registry.py will NOT trigger. We only fire on added lines (^+)
# that match a surface-extension pattern.
#
# Escape hatch:  SKIP_CODEMAP_SYNC=1 git commit ...
#
# Self-check:    bash scripts/codemap-sync-check.sh --self-check
#                Applies every detector pattern to the live production files
#                and fails if one of them matches nothing — i.e. if production
#                has changed shape and the detector has gone dead. Exercised by
#                tests/integration/test_codemap_sync_hook.sh (test 0).
#
# Safety:        If anything in this script fails (git missing, etc.),
#                we exit 0 — a buggy hook must never block commits.

set -uo pipefail

# --- surface definitions (single source of truth for both modes) ---------
# Any change to these must keep --self-check green, or the gate is dead.

# MCP tool registry. Registration entries are ``("name", <factory-or-class>(...))``
# tuples. Since the 8-facade cutover they read ``("search", build_search_facade(
# project_root))``; before that they read ``("check_code_scale", AnalyzeScaleTool(
# project_root))``. We match the *semantic* shape — a quoted tool name mapped to a
# constructed object — so both forms, and the next one, trip the gate.
REGISTRY_PATH="tree_sitter_analyzer/mcp/_tool_registry.py"
REGISTRY_RE='\("[a-zA-Z_][a-zA-Z0-9_]*"[[:space:]]*,[[:space:]]*[A-Za-z_][A-Za-z0-9_]*\('
CODEMAP_MCP="docs/CODEMAPS/mcp-tools.md"

# CLI argument surface. argument_parser_builder.py only assembles the groups —
# every actual add_argument() call lives in cli/argument_groups/_*.py. Watch the
# whole surface so a flag added in either place trips the gate.
CLI_PATH_RE='^tree_sitter_analyzer/cli/(argument_parser_builder\.py|argument_groups/[^/]+\.py)$'
CLI_RE='add_argument\('
CODEMAP_CLI="docs/CODEMAPS/cli.md"

CODEMAP_LANGS="docs/CODEMAPS/languages.md"
CODEMAP_FMT="docs/CODEMAPS/formatters.md"

# --- --self-check mode ---------------------------------------------------
# Not part of the commit gate: a maintenance assertion that each detector still
# matches the code it claims to guard.
if [[ "${1:-}" == "--self-check" ]]; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  DEAD=0

  n=$(grep -Ec "$REGISTRY_RE" "$ROOT/$REGISTRY_PATH" 2>/dev/null || true)
  echo "[codemap-sync] detector 'mcp-registry': $n matching line(s) in $REGISTRY_PATH"
  if [[ "${n:-0}" -eq 0 ]]; then
    echo "[codemap-sync] DEAD DETECTOR: pattern $REGISTRY_RE no longer matches $REGISTRY_PATH." >&2
    DEAD=$((DEAD + 1))
  fi

  n=$(cd "$ROOT" && git ls-files \
        | grep -E "$CLI_PATH_RE" \
        | tr '\n' '\0' \
        | xargs -0 grep -Ec "$CLI_RE" 2>/dev/null \
        | awk -F: '{ s += $NF } END { print s + 0 }')
  echo "[codemap-sync] detector 'cli-arguments': $n matching line(s) under the CLI argument surface"
  if [[ "${n:-0}" -eq 0 ]]; then
    echo "[codemap-sync] DEAD DETECTOR: pattern $CLI_RE no longer matches $CLI_PATH_RE." >&2
    DEAD=$((DEAD + 1))
  fi

  for d in tree_sitter_analyzer/languages tree_sitter_analyzer/formatters; do
    if [[ ! -d "$ROOT/$d" ]]; then
      echo "[codemap-sync] DEAD DETECTOR: watched directory $d no longer exists." >&2
      DEAD=$((DEAD + 1))
    fi
  done

  for m in "$CODEMAP_MCP" "$CODEMAP_CLI" "$CODEMAP_LANGS" "$CODEMAP_FMT"; do
    if [[ ! -f "$ROOT/$m" ]]; then
      echo "[codemap-sync] DEAD DETECTOR: codemap $m no longer exists." >&2
      DEAD=$((DEAD + 1))
    fi
  done

  if (( DEAD > 0 )); then
    echo "[codemap-sync] self-check FAILED: $DEAD dead detector(s). The gate is not gating." >&2
    exit 1
  fi
  echo "[codemap-sync] self-check OK"
  exit 0
fi

# Escape hatch — print warning to stderr but allow the commit.
if [[ "${SKIP_CODEMAP_SYNC:-0}" == "1" ]]; then
  echo "[codemap-sync] SKIP_CODEMAP_SYNC=1 set — bypassing codemap sync gate (you are on the honor system)." >&2
  exit 0
fi

# Be defensive: bail out cleanly if git isn't usable.
if ! command -v git >/dev/null 2>&1; then
  exit 0
fi
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

# Snapshot the staged diff once. `--cached` = staged-for-commit.
# `-U0` keeps the diff compact — we only care about added lines.
# If diff fails for any reason, fall through to a clean exit.
DIFF="$(git diff --cached -U0 2>/dev/null)" || exit 0
[[ -z "$DIFF" ]] && exit 0

# Snapshot the staged file list — used to test "is the codemap also staged?"
STAGED_FILES="$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)" || exit 0

# Helper: does the staged set contain a given path?
is_staged() {
  local target="$1"
  printf '%s\n' "$STAGED_FILES" | grep -Fxq "$target"
}

# Helper: extract added lines (^+ but not the +++ file header) inside a
# specific staged file's hunk. Returns empty if file not in diff.
added_lines_for() {
  local path="$1"
  printf '%s\n' "$DIFF" \
    | awk -v target="$path" '
        /^diff --git / { in_file = ($0 ~ ("b/" target "$")) }
        in_file && /^\+[^+]/ { print substr($0, 2) }
      '
}

VIOLATIONS=0
emit_block() {
  echo "BLOCK: $1" >&2
  VIOLATIONS=$((VIOLATIONS + 1))
}

# --- Trigger 1: MCP tool registry ----------------------------------------
if is_staged "$REGISTRY_PATH"; then
  if printf '%s\n' "$(added_lines_for "$REGISTRY_PATH")" | grep -Eq "$REGISTRY_RE"; then
    if ! is_staged "$CODEMAP_MCP"; then
      emit_block "$REGISTRY_PATH adds a new tool registration but $CODEMAP_MCP is not staged. Run /update-codemaps or add the row manually, then re-stage."
    fi
  fi
fi

# --- Trigger 2: CLI argument surface --------------------------------------
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  [[ "$f" =~ $CLI_PATH_RE ]] || continue
  if printf '%s\n' "$(added_lines_for "$f")" | grep -Eq "$CLI_RE"; then
    if ! is_staged "$CODEMAP_CLI"; then
      emit_block "$f adds a new CLI argument but $CODEMAP_CLI is not staged. Run /update-codemaps or add the row manually, then re-stage."
    fi
    break
  fi
done <<< "$STAGED_FILES"

# --- Trigger 3: New language plugin --------------------------------------
# Any newly-added .py file under tree_sitter_analyzer/languages/
NEW_LANG_FILES="$(git diff --cached --name-only --diff-filter=A 2>/dev/null \
                    | grep -E '^tree_sitter_analyzer/languages/.+\.py$' || true)"
if [[ -n "$NEW_LANG_FILES" ]]; then
  if ! is_staged "$CODEMAP_LANGS"; then
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      emit_block "$f is a new language plugin but $CODEMAP_LANGS is not staged. Run /update-codemaps or add the row manually, then re-stage."
    done <<< "$NEW_LANG_FILES"
  fi
fi

# --- Trigger 4: New formatter --------------------------------------------
NEW_FMT_FILES="$(git diff --cached --name-only --diff-filter=A 2>/dev/null \
                   | grep -E '^tree_sitter_analyzer/formatters/.+\.py$' || true)"
if [[ -n "$NEW_FMT_FILES" ]]; then
  if ! is_staged "$CODEMAP_FMT"; then
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      emit_block "$f is a new formatter but $CODEMAP_FMT is not staged. Run /update-codemaps or add the row manually, then re-stage."
    done <<< "$NEW_FMT_FILES"
  fi
fi

if (( VIOLATIONS > 0 )); then
  echo "" >&2
  echo "[codemap-sync] $VIOLATIONS violation(s). To bypass for an emergency: SKIP_CODEMAP_SYNC=1 git commit ..." >&2
  exit 1
fi

exit 0
