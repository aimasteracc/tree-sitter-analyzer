#!/usr/bin/env python3
"""
FTS5 Fast Path — Use pre-indexed AST cache instead of ripgrep for symbol queries.

When the AST cache has been indexed with FTS5, simple symbol queries (alphanumeric
identifiers, no regex metacharacters) can be answered from the SQLite FTS5 index
in microseconds instead of spawning a ripgrep subprocess.

Integration point: search_content_tool.py calls try_fts5_fast_path() before
falling back to ripgrep. Only eligible queries are served from FTS5; everything
else goes through the normal ripgrep path.
"""

from __future__ import annotations

import os
import re
from typing import Any

_SIMPLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_EXTS_TO_LANG_SUFFIX: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "java": "java",
    "go": "go",
    "c": "c",
    "cpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "h": "c",
    "hpp": "cpp",
    "rs": "rust",
    "rb": "ruby",
    "php": "php",
    "swift": "swift",
    "kt": "kotlin",
    "cs": "c_sharp",
}


def _is_fts_eligible(arguments: dict[str, Any]) -> bool:
    """Return True if the query can be served from the FTS5 index.

    A query is FTS-eligible when:
    - It's a simple alphanumeric identifier (no regex metacharacters)
    - No regex-specific flags are set (fixed_strings, word, multiline)
    - No context lines are requested (context_before, context_after)
    - No file-type filtering that FTS5 doesn't understand
    """
    query = arguments.get("query", "")
    if not query or not _SIMPLE_IDENTIFIER_RE.match(query):
        return False
    if arguments.get("fixed_strings", False):
        return False
    if arguments.get("word", False):
        return False
    if arguments.get("multiline", False):
        return False
    if arguments.get("context_before") is not None:
        return False
    if arguments.get("context_after") is not None:
        return False
    if arguments.get("include_globs"):
        return False
    if arguments.get("exclude_globs"):
        return False
    return True


def _extensions_to_language(arguments: dict[str, Any]) -> str | None:
    """Map extensions argument to a language filter for FTS5 search."""
    exts = arguments.get("extensions")
    if not exts or not isinstance(exts, list) or len(exts) != 1:
        return None
    return _EXTS_TO_LANG_SUFFIX.get(exts[0])


def _aggregate_by_file(fts_results: list) -> dict[str, int]:
    """Count FTS results per file path."""
    by_file: dict[str, int] = {}
    for r in fts_results:
        fp = r["file"]
        by_file[fp] = by_file.get(fp, 0) + 1
    return by_file


def _build_symbol_groups(fts_results: list) -> list[dict]:
    """Group FTS results into per-file symbol lists, preserving sorted order."""
    symbols: dict[str, list] = {}
    for r in fts_results:
        fp = r["file"]
        if fp not in symbols:
            symbols[fp] = []
        symbols[fp].append(
            {
                "name": r.get("name", ""),
                "kind": r.get("kind", ""),
                "line": r.get("line", 0),
            }
        )
    return [
        {"file": fp, "count": len(syms), "symbols": syms}
        for fp, syms in sorted(symbols.items())
    ]


def _match_line_from_fts(file_path: str, line: int, source_root: str) -> str:
    """Best-effort extraction of the matching line text from the source file."""
    abs_path = os.path.join(source_root, file_path)
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        idx = line - 1
        if 0 <= idx < len(lines):
            return lines[idx].rstrip("\n\r")
    except OSError:
        pass
    return ""


def try_fts5_fast_path(
    arguments: dict[str, Any],
    project_root: str | None,
    requested_format: str,
) -> dict[str, Any] | None:
    """Try to answer the search query from the FTS5 AST index.

    Returns a complete search response dict if the query was answered from
    FTS5, or None if the query must fall through to ripgrep.

    The response shape matches what search_content normally returns so the
    caller can return it directly without further transformation.
    """
    if not project_root or not _is_fts_eligible(arguments):
        return None

    from ...ast_cache import ASTCache

    db_path = os.path.join(project_root, ".ast-cache", "index.db")
    if not os.path.isfile(db_path):
        return None

    try:
        cache = ASTCache(project_root, db_path=db_path)
    except Exception:
        return None

    if not cache._fts5_available:
        cache.close()
        return None

    stats = cache.get_stats()
    if stats.get("total_files", 0) == 0:
        cache.close()
        return None

    query = arguments["query"]
    language = _extensions_to_language(arguments)
    fts_results = cache.fts_search(query, language=language, limit=200)
    cache.close()

    if not fts_results:
        return None

    if requested_format == "total_only":
        return {
            "success": True,
            "total_matches": len(fts_results),
            "data_source": "fts5",
        }

    if requested_format == "count_only":
        by_file = _aggregate_by_file(fts_results)
        file_counts = [{"file": fp, "count": c} for fp, c in sorted(by_file.items())]
        return {
            "success": True,
            "total_matches": len(fts_results),
            "file_count": len(by_file),
            "files": file_counts[:50],
            "data_source": "fts5",
        }

    formatted: list[dict[str, Any]] = [
        {
            "file": r["file"],
            "line": r.get("line", 0),
            "kind": r.get("kind", ""),
            "name": r.get("name", ""),
            "language": r.get("language", ""),
            "match": _match_line_from_fts(r["file"], r.get("line", 0), project_root),
        }
        for r in fts_results
    ]

    response: dict[str, Any] = {
        "success": True,
        "query": query,
        "total_matches": len(fts_results),
        "count": len(fts_results),
        "results": formatted[:100],
        "data_source": "fts5",
    }
    if language:
        response["language_filter"] = language

    if requested_format == "summary":
        response["files"] = _build_symbol_groups(fts_results)[:50]

    return response
