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
# Safety:        If anything in this script fails (git missing, etc.),
#                we exit 0 — a buggy hook must never block commits.

set -uo pipefail

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
# A new tool registration looks like:  ("tool_name", SomeTool(project_root))
# Match added lines containing an opening paren + quoted identifier + comma
# inside _tool_registry.py. The pattern is intentionally broader than
# "codegraph_" — any new ("name", ...Tool(...)) entry counts.
REGISTRY_PATH="tree_sitter_analyzer/mcp/_tool_registry.py"
CODEMAP_MCP="docs/CODEMAPS/mcp-tools.md"
if is_staged "$REGISTRY_PATH"; then
  ADDED="$(added_lines_for "$REGISTRY_PATH")"
  # Look for added lines that introduce a new ("name", ...Tool(...)) tuple.
  if printf '%s\n' "$ADDED" | grep -Eq '\("[a-zA-Z_][a-zA-Z0-9_]*"[[:space:]]*,[[:space:]]*[A-Za-z_]*Tool'; then
    if ! is_staged "$CODEMAP_MCP"; then
      emit_block "$REGISTRY_PATH adds a new tool registration but $CODEMAP_MCP is not staged. Run /update-codemaps or add the row manually, then re-stage."
    fi
  fi
fi

# --- Trigger 2: CLI argument parser --------------------------------------
ARGS_PATH="tree_sitter_analyzer/cli/argument_parser_builder.py"
CODEMAP_CLI="docs/CODEMAPS/cli.md"
if is_staged "$ARGS_PATH"; then
  ADDED="$(added_lines_for "$ARGS_PATH")"
  if printf '%s\n' "$ADDED" | grep -Eq 'add_argument\('; then
    if ! is_staged "$CODEMAP_CLI"; then
      emit_block "$ARGS_PATH adds a new CLI argument but $CODEMAP_CLI is not staged. Run /update-codemaps or add the row manually, then re-stage."
    fi
  fi
fi

# --- Trigger 3: New language plugin --------------------------------------
# Any newly-added .py file under tree_sitter_analyzer/languages/
CODEMAP_LANGS="docs/CODEMAPS/languages.md"
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
CODEMAP_FMT="docs/CODEMAPS/formatters.md"
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
