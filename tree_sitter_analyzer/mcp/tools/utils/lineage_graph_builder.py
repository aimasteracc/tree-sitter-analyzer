"""Lineage graph builder helpers — Phase 3 REQ-CLEAN-001.

Contains grep-based definition discovery, caller enrichment, and the
grep-fallback integration used by SymbolLineageTool.

Functions:
    _find_definitions_via_grep
    _normalize_bare_symbol
    _build_grep_definition_regexes
    _iter_grep_candidate_files
    _scan_file_for_definitions
    _enrich_references_with_callers
    _apply_grep_fallback_defs
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.cache.fingerprint import is_ast_index_stale

# K3 fallback: project-wide text scan for definition sites.
_K3_FALLBACK_EXTS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".java",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".kt",
        ".cs",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
    }
)
_K3_FALLBACK_EXCLUDE: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "htmlcov",
        ".cache",
        ".eggs",
        ".claude",
        ".ast-cache",
        ".tree-sitter-cache",
    }
)


def _apply_grep_fallback_defs(
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    project_root: str,
    symbol: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """K3 fix: text-grep the project for definitions when the AST scan missed them.

    Promotes any matching reference to a definition (file + start_line key)
    and removes it from ``references`` to avoid double-counting. Pure
    helper — no side effects on the caller's lists.
    """
    fallback_defs = _find_definitions_via_grep(project_root, symbol)
    if not fallback_defs:
        return definitions, references

    out_defs = list(definitions)
    seen_def_keys = {(d.get("file", ""), d.get("start_line", 0)) for d in out_defs}
    ref_keys_to_drop: set[tuple[str, int]] = set()
    for fd in fallback_defs:
        key = (fd["file"], fd["start_line"])
        if key in seen_def_keys:
            continue
        seen_def_keys.add(key)
        ref_keys_to_drop.add(key)
        out_defs.append(fd)
    if not ref_keys_to_drop:
        return out_defs, references
    out_refs = [
        r
        for r in references
        if (r.get("file", ""), r.get("start_line", 0)) not in ref_keys_to_drop
    ]
    return out_defs, out_refs


def _find_definitions_via_grep(
    project_root: str,
    symbol: str,
) -> list[dict[str, Any]]:
    """Project-wide text scan for definition sites of ``symbol``.

    r37be (dogfood): tool flagged this at 108 lines. Split into
    bare-name normalisation + regex build + file walk + per-line scan.
    Behaviour preserved: 2-layer substring/word filter, no tree-sitter.
    """
    bare_name = _normalize_bare_symbol(symbol)
    if not bare_name:
        return []
    root = Path(project_root).resolve()
    if not root.is_dir():
        return []

    word_re, line_re = _build_grep_definition_regexes(bare_name)
    hits: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()
    for file_path in _iter_grep_candidate_files(root):
        _scan_file_for_definitions(
            file_path, root, bare_name, word_re, line_re, hits, seen_keys
        )
    return hits


def _normalize_bare_symbol(symbol: str) -> str:
    """Return the trailing component of ``a.b.c`` style symbols."""
    if not symbol:
        return ""
    return symbol.split(".")[-1]


def _build_grep_definition_regexes(
    bare_name: str,
) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Return (whole-word file-pre-check, full-line definition match) regexes."""
    word_re = re.compile(r"\b" + re.escape(bare_name) + r"\b")
    keyword_alternation = (
        r"(?:def|async\s+def|class|function|function\*|async\s+function|"
        r"func|fn|struct|interface|trait|enum|type|impl|namespace|module)"
    )
    line_re = re.compile(
        r"^\s*"
        r"(?:(?:public|private|protected|static|abstract|final|virtual|"
        r"override|sealed|unsafe|async|export|default)\s+)*"
        + keyword_alternation
        + r"\s+"
        + re.escape(bare_name)
        + r"(?:\b|[\s\(:<])"
    )
    return word_re, line_re


def _iter_grep_candidate_files(root: Path) -> Iterator[Path]:
    """Yield source files under ``root`` (manual scandir walk, excludes pruned)."""
    import os as _os

    stack: list[str] = [str(root)]
    while stack:
        current = stack.pop()
        try:
            it = _os.scandir(current)
        except OSError:
            continue
        with it:
            for entry in it:
                name = entry.name
                if name in _K3_FALLBACK_EXCLUDE:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                dot = name.rfind(".")
                if dot == -1:
                    continue
                if name[dot:].lower() not in _K3_FALLBACK_EXTS:
                    continue
                yield Path(entry.path)


def _scan_file_for_definitions(
    file_path: Path,
    root: Path,
    bare_name: str,
    word_re: re.Pattern[str],
    line_re: re.Pattern[str],
    hits: list[dict[str, Any]],
    seen_keys: set[tuple[str, int]],
) -> None:
    """Read ``file_path`` and append every matching definition line to ``hits``."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if not word_re.search(text):
        return
    rel = str(file_path.relative_to(root))
    for i, line in enumerate(text.splitlines(), start=1):
        if not line_re.match(line):
            continue
        key = (rel, i)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        hits.append(
            {
                "name": bare_name,
                "type": "definition",
                "file": rel,
                "start_line": i,
                "end_line": i,
                "role": "definition",
            }
        )


def _enrich_references_with_callers(
    references: list[dict[str, Any]],
    project_root: str,
    symbol: str,
) -> list[dict[str, Any]]:
    """#757: augment AST-element references with real call-site callers.

    ``execute_find_references`` walks AST *elements* (imports, definitions)
    but not call-edge rows, so its references[] contains only import
    statements — never actual call sites.  The call graph (populated by
    ``index_project``) stores every call edge as a row with
    ``caller_name / caller_file / caller_line``.  Querying it yields the
    real callers that the AST-element walk misses.

    Deduplication is by ``(file, start_line)`` so an AST import hit at
    the same position as a call-graph edge is not double-counted.

    Returns a new list (immutable input) with call-site rows appended.
    """
    try:
        from tree_sitter_analyzer.ast_cache import ASTCache

        if is_ast_index_stale(project_root):
            return references
        cache = ASTCache(project_root)
        if not cache.has_call_edges():
            cache.close()
            return references
        raw_callers = cache.query_callers(symbol)
        cache.close()
    except Exception:  # nosec BLE001 — degrade gracefully; no callers added
        return references

    if not raw_callers:
        return references

    # Build a seen-key set from existing references to avoid duplicates.
    seen: set[tuple[str, int]] = {
        (r.get("file", ""), int(r.get("start_line", 0))) for r in references
    }

    new_refs = list(references)
    for edge in raw_callers:
        caller_name = edge.get("caller_name", "")
        caller_file = edge.get("caller_file", "")
        call_site_line = int(edge.get("callee_line") or edge.get("caller_line") or 0)
        # Skip unattributed call sites (module-level callers with no
        # enclosing function — same rule as callers_tool #638 fix).
        if not caller_name or not caller_file:
            continue
        key = (caller_file, call_site_line)
        if key in seen:
            continue
        seen.add(key)
        new_refs.append(
            {
                "name": caller_name,
                "type": "call_site",
                "file": caller_file,
                "start_line": call_site_line,
                "end_line": call_site_line,
                "role": "caller",
            }
        )
    return new_refs
