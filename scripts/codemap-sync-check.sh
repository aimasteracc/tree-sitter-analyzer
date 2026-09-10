#!/usr/bin/env bash
# codemap-sync-check.sh
#
# Pre-commit gate (Lane A of doc-sync).
# Blocks commits that change the MCP tool surface or the CLI flag surface
# WITHOUT staging the corresponding docs/CODEMAPS/*.md update.
#
# HOW IT DECIDES
#   By comparing the *surface set* at HEAD against the surface set in the index —
#   not by pattern-matching added diff lines. Added-line matching was wrong from
#   both ends: a comment or docstring mentioning a registration triggered it,
#   while a dict-literal or append-in-a-loop registration slipped past it, and it
#   could never see a *removal* at all. Set comparison is immune to comments,
#   docstrings, reordering, parameter renames and literal shape.
#
#   Enumeration lives in scripts/codemap_surface.py (static ast, no package
#   import: ~2.2 s worst case on Windows for the whole surface, and it only runs
#   when a watched file is actually staged). The authoritative runtime
#   enumerations from CLAUDE.md cost ~640 ms of import time each, so they are not
#   on the commit path — instead --self-check asserts the static extractor agrees
#   with them exactly, and tests/contracts/test_agent_docs_contract.py asserts
#   the same thing in CI.
#
#   No git-diff *text* is parsed anywhere, so diff.noprefix, diff.mnemonicPrefix,
#   diff.external and core.quotePath cannot affect the verdict. Staged paths are
#   read NUL-separated.
#
# MODES
#   (no args)       gate mode — the pre-commit path
#   --self-check    assert every detector still matches the live surface exactly
#   --help          this text
#   anything else   usage error, exit 2 (a typo must never look like a pass)
#
# ESCAPE HATCH
#   SKIP_CODEMAP_SYNC=1      when a block WOULD have happened, this now fails
#                            loudly and tells you to use =force. pre-commit only
#                            surfaces output from failing hooks, so a silent
#                            "warning" is invisible — a session-wide
#                            `export SKIP_CODEMAP_SYNC=1` used to disable the
#                            gate with zero signal.
#   SKIP_CODEMAP_SYNC=force  bypass, appending an audit line to
#                            $GIT_DIR/codemap-sync-bypass.log. The CI parity
#                            tests remain the net; bypass is local-only.
#
# SAFETY
#   Git unusable / not a repo → exit 0. Beyond that the gate prefers a visible
#   failure to a silent pass: a missing Python interpreter degrades to a
#   conservative path-based block, never to exit 0.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SURFACE_TOOL="$SCRIPT_DIR/codemap_surface.py"

CODEMAP_MCP="docs/CODEMAPS/mcp-tools.md"
CODEMAP_CLI="docs/CODEMAPS/cli.md"
CODEMAP_LANGS="docs/CODEMAPS/languages.md"
CODEMAP_FMT="docs/CODEMAPS/formatters.md"

# Watched surface. Must stay in sync with codemap_surface.py's MCP_REGISTRY /
# CLI_PREFIX; --self-check asserts the CLI half covers the whole documented
# surface (zero add_argument calls under cli/** outside the filter).
MCP_REGISTRY="tree_sitter_analyzer/mcp/_tool_registry.py"
CLI_PREFIX="tree_sitter_analyzer/cli/"

usage() {
  sed -n '2,48p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Resolve a Python interpreter. Order matters: `py -3` last because it is a
# Windows launcher shim and slower to start.
find_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  if command -v py >/dev/null 2>&1; then
    printf '%s\n' "py -3"
    return 0
  fi
  return 1
}

# Resolve a Python that can IMPORT the package. --self-check compares the static
# extractor against the authoritative runtime enumerations, which needs project
# deps; the gate path deliberately needs none, so it uses find_python above.
find_project_python() {
  local root="$1"
  if [[ -x "$root/.venv/Scripts/python.exe" ]]; then
    printf '%s\n' "$root/.venv/Scripts/python.exe"
    return 0
  fi
  if [[ -x "$root/.venv/bin/python" ]]; then
    printf '%s\n' "$root/.venv/bin/python"
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    printf '%s\n' "uv run --quiet python"
    return 0
  fi
  find_python
}

# --- --self-check --------------------------------------------------------
# Not part of the commit gate. Asserts that what the gate can see equals the
# real surface, EXACTLY. A count>0 check would not do: a reviewer built a tree
# where each detector matched exactly one stale line (an archaeology mention in
# a docstring; one leftover legacy file) and a count>0 self-check passed while
# both detectors were functionally dead. A loose lower bound on a deterministic
# count is also precisely what CLAUDE.md's exact-assertion rule bans.
self_check() {
  local root py rc=0
  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  cd "$root" || return 1
  if ! py="$(find_project_python "$root")"; then
    echo "[codemap-sync] self-check FAILED: no Python interpreter found." >&2
    return 1
  fi

  # shellcheck disable=SC2086
  $py - <<'PY'
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import codemap_surface as cs

problems = []

# 1. MCP: static extraction must equal the authoritative registry, exactly.
static_mcp = cs.surface(cs.WORKTREE, "mcp")
try:
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    runtime_mcp = {name for name, _ in create_tool_registry(".")[0]}
except Exception as exc:  # pragma: no cover - environment problem, not a shape problem
    problems.append(f"could not enumerate the runtime MCP registry: {exc}")
    runtime_mcp = None
if runtime_mcp is not None:
    print(f"[codemap-sync] mcp surface: {len(static_mcp)} static / {len(runtime_mcp)} runtime")
    if static_mcp != runtime_mcp:
        problems.append(
            "static MCP extraction != runtime registry; "
            f"static-only={sorted(static_mcp - runtime_mcp)} "
            f"runtime-only={sorted(runtime_mcp - static_mcp)}"
        )

# 2. CLI: static extraction over the watched surface must equal the
#    authoritative parser's option strings, modulo argparse's synthesised -h/--help.
static_cli = cs.surface(cs.WORKTREE, "cli")
try:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    runtime_cli = {
        s for a in create_argument_parser()._actions for s in a.option_strings
    }
except Exception as exc:  # pragma: no cover
    problems.append(f"could not enumerate the runtime CLI parser: {exc}")
    runtime_cli = None
if runtime_cli is not None:
    missing = runtime_cli - static_cli - cs.ARGPARSE_IMPLICIT_FLAGS
    print(
        f"[codemap-sync] cli surface: {len(static_cli)} static / "
        f"{len(runtime_cli)} runtime (+{len(cs.ARGPARSE_IMPLICIT_FLAGS)} argparse-implicit)"
    )
    if missing:
        problems.append(
            f"parser exposes flags the gate cannot see: {sorted(missing)}"
        )

# 3. Coverage invariant: zero add_argument calls under tree_sitter_analyzer/cli/**
#    may fall outside the watched path filter. This is the property that actually
#    matters -- 82 of 405 calls (the find-and-grep / list-files / search-content
#    console scripts, all documented entry points) were unwatched before.
tracked = subprocess.run(
    ["git", "ls-files", "-z", "--", "tree_sitter_analyzer/cli/"],
    capture_output=True, check=True,
).stdout.decode("utf-8", "replace")
unwatched = 0
for rel in (p for p in tracked.split("\0") if p.endswith(".py")):
    if rel.startswith(cs.CLI_PREFIX):
        continue
    unwatched += len(cs.extract_cli_flags(Path(rel).read_text(encoding="utf-8")))
print(f"[codemap-sync] cli coverage: {unwatched} flag(s) outside the watch filter")
if unwatched:
    problems.append(f"{unwatched} add_argument flag(s) under cli/** are unwatched")

# 4. The watched paths must be non-empty -- a rename that empties the filter is a
#    dead detector even if everything above happens to agree.
paths = cs.list_paths(cs.WORKTREE)
if cs.MCP_REGISTRY not in paths:
    problems.append(f"{cs.MCP_REGISTRY} is not tracked; the MCP detector watches nothing")
if not any(p.startswith(cs.CLI_PREFIX) for p in paths):
    problems.append(f"no tracked files under {cs.CLI_PREFIX}; the CLI detector watches nothing")

for codemap in (
    "docs/CODEMAPS/mcp-tools.md",
    "docs/CODEMAPS/cli.md",
    "docs/CODEMAPS/languages.md",
    "docs/CODEMAPS/formatters.md",
):
    if not Path(codemap).is_file():
        problems.append(f"codemap {codemap} no longer exists")

for directory in ("tree_sitter_analyzer/languages", "tree_sitter_analyzer/formatters"):
    if not Path(directory).is_dir():
        problems.append(f"watched directory {directory} no longer exists")

if problems:
    for problem in problems:
        print(f"[codemap-sync] DEAD DETECTOR: {problem}", file=sys.stderr)
    print(
        f"[codemap-sync] self-check FAILED: {len(problems)} problem(s). "
        "The gate is not gating.",
        file=sys.stderr,
    )
    sys.exit(1)
print("[codemap-sync] self-check OK")
PY
  rc=$?
  return $rc
}

# --- argument handling (a typo must not silently fall through to gate mode) ---
case "${1:-}" in
  "")
    ;;
  --self-check)
    self_check
    exit $?
    ;;
  --help|-h)
    usage
    exit 0
    ;;
  *)
    echo "[codemap-sync] unknown argument: $1" >&2
    echo "[codemap-sync] usage: codemap-sync-check.sh [--self-check | --help]" >&2
    exit 2
    ;;
esac

# Be defensive: bail out cleanly if git isn't usable.
command -v git >/dev/null 2>&1 || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Staged paths, NUL-separated. No diff text is parsed, so no diff.* or
# core.quotePath setting can hide a path from us; -z also means git never quotes
# a non-ASCII path.
#
# Read via process substitution, NOT command substitution: bash silently DROPS
# NUL bytes inside $(...), which would concatenate every staged path into one
# meaningless string and make the gate see nothing.
STAGED_FILES=()
while IFS= read -r -d '' path; do
  STAGED_FILES+=("$path")
done < <(git diff --cached --name-only -z --diff-filter=ACMRD 2>/dev/null)
(( ${#STAGED_FILES[@]} > 0 )) || exit 0

is_staged() {
  local target="$1" path
  for path in "${STAGED_FILES[@]}"; do
    [[ "$path" == "$target" ]] && return 0
  done
  return 1
}

# Did the staged set touch the watched surface at all? Cheap pre-filter: only
# when this is true do we pay for surface enumeration.
touches_mcp=0
touches_cli=0
for path in "${STAGED_FILES[@]}"; do
  [[ "$path" == "$MCP_REGISTRY" ]] && touches_mcp=1
  [[ "$path" == "$CLI_PREFIX"*.py ]] && touches_cli=1
done

VIOLATIONS=0
BLOCK_DETAIL=""
emit_block() {
  echo "BLOCK: $1" >&2
  BLOCK_DETAIL="$BLOCK_DETAIL$1"$'\n'
  VIOLATIONS=$((VIOLATIONS + 1))
}

# --- Triggers 1 + 2: surface-set comparison ------------------------------
if (( touches_mcp || touches_cli )); then
  if PY="$(find_python)"; then
    # One process for both surfaces and both revisions.
    # shellcheck disable=SC2086
    SURFACE_DIFF="$($PY "$SURFACE_TOOL" compare --base HEAD --head INDEX 2>/dev/null)"
    if [[ -n "$SURFACE_DIFF" ]]; then
      MCP_CHANGES="$(printf '%s\n' "$SURFACE_DIFF" | grep '^mcp ' || true)"
      CLI_CHANGES="$(printf '%s\n' "$SURFACE_DIFF" | grep '^cli ' || true)"

      if [[ -n "$MCP_CHANGES" ]] && ! is_staged "$CODEMAP_MCP"; then
        emit_block "the MCP tool surface changed but $CODEMAP_MCP is not staged:
$(printf '%s\n' "$MCP_CHANGES" | sed 's/^mcp /    /')"
      fi
      if [[ -n "$CLI_CHANGES" ]] && ! is_staged "$CODEMAP_CLI"; then
        emit_block "the CLI flag surface changed but $CODEMAP_CLI is not staged:
$(printf '%s\n' "$CLI_CHANGES" | sed 's/^cli /    /')"
      fi
    fi
  else
    # No interpreter: we cannot compare sets. Degrade to a conservative
    # path-based block rather than a silent pass.
    echo "[codemap-sync] WARNING: no Python interpreter; falling back to a conservative path-based trigger." >&2
    if (( touches_mcp )) && ! is_staged "$CODEMAP_MCP"; then
      emit_block "$MCP_REGISTRY is staged and $CODEMAP_MCP is not (no interpreter available for exact surface comparison)."
    fi
    if (( touches_cli )) && ! is_staged "$CODEMAP_CLI"; then
      emit_block "a ${CLI_PREFIX}*.py file is staged and $CODEMAP_CLI is not (no interpreter available for exact surface comparison)."
    fi
  fi
fi

# --- Trigger 3: New language plugin --------------------------------------
NEW_FILES=()
while IFS= read -r -d '' path; do
  NEW_FILES+=("$path")
done < <(git diff --cached --name-only -z --diff-filter=A 2>/dev/null)

for path in ${NEW_FILES[@]+"${NEW_FILES[@]}"}; do
  case "$path" in
    tree_sitter_analyzer/languages/*.py)
      is_staged "$CODEMAP_LANGS" || emit_block "$path is a new language plugin but $CODEMAP_LANGS is not staged."
      ;;
    tree_sitter_analyzer/formatters/*.py)
      is_staged "$CODEMAP_FMT" || emit_block "$path is a new formatter but $CODEMAP_FMT is not staged."
      ;;
  esac
done

# --- verdict + escape hatch ----------------------------------------------
if (( VIOLATIONS == 0 )); then
  exit 0
fi

case "${SKIP_CODEMAP_SYNC:-0}" in
  force)
    GIT_DIR_PATH="$(git rev-parse --git-dir 2>/dev/null || echo .git)"
    {
      echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') bypassed $VIOLATIONS violation(s) on $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
      printf '%s' "$BLOCK_DETAIL" | sed 's/^/    /'
    } >> "$GIT_DIR_PATH/codemap-sync-bypass.log" 2>/dev/null
    echo "[codemap-sync] SKIP_CODEMAP_SYNC=force — bypassing $VIOLATIONS violation(s); logged to \$GIT_DIR/codemap-sync-bypass.log." >&2
    echo "[codemap-sync] The CI codemap parity tests still run. Bypass is local-only." >&2
    exit 0
    ;;
  1)
    echo "" >&2
    echo "[codemap-sync] SKIP_CODEMAP_SYNC=1 would have silenced $VIOLATIONS real violation(s)." >&2
    echo "[codemap-sync] Refusing: pre-commit only shows output from FAILING hooks, so a" >&2
    echo "[codemap-sync] silently-bypassed gate is indistinguishable from a passing one — an" >&2
    echo "[codemap-sync] 'export SKIP_CODEMAP_SYNC=1' would disable this gate for a whole" >&2
    echo "[codemap-sync] session with zero signal. Either stage the codemap, or re-run with" >&2
    echo "[codemap-sync] SKIP_CODEMAP_SYNC=force to bypass on the record." >&2
    exit 1
    ;;
esac

echo "" >&2
echo "[codemap-sync] $VIOLATIONS violation(s). Run /update-codemaps, or stage the codemap row manually." >&2
echo "[codemap-sync] To bypass on the record: SKIP_CODEMAP_SYNC=force git commit ..." >&2
exit 1
