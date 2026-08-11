"""Stable facade for AST cache extraction.

Symbol rules, language helpers, and traversal live in focused modules. The
worker remains here so multiprocessing pickles and runtime monkeypatches keep
resolving the historical module-level entry points.
"""

# ruff: noqa: F401

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from typing import Any

from ..constants import EXCLUDE_DIRS
from ..core.parser import Parser
from ..indexing_snapshot import (
    IndexFileFingerprint,
    decode_index_source,
    index_source_content_hash,
)
from ..source_oracle import SourceOracleError, safe_workspace_path
from ._symbol_declarations import (
    _DOCSTRING_MAX_CHARS,
    _go_package_constants,
    _php_constants,
    _python_docstring,
    _python_module_constant,
)
from ._symbol_metrics import (
    _annotate_canonical_complexity,
    _count_decision_points,
    _count_nodes,
)
from ._symbol_rules import (
    _CLASS_LIKE,
    _COMPLEXITY_NODE_TYPES,
    _CONST_STYLE_NAME,
    _CSHARP_SCOPE_BODY_NODES,
    _ENUM_LIKE,
    _FUNCTION_LIKE,
    _GO_CONST_LIKE,
    _GO_SCOPE_BODY_NODES,
    _IMPORT_LIKE,
    _JAVA_SCOPE_BODY_NODES,
    _JSTS_SCOPE_BODY_NODES,
    _PHP_SCOPE_BODY_NODES,
    _PY_CONST_STYLE_NAME,
    _PY_DUNDER_NAME,
    _PY_SCOPE_BODY_NODES,
    _RUST_CONST_LIKE,
    _RUST_SCOPE_BODY_NODES,
    _SCALA_CLASS_LIKE,
    _SCALA_SCOPE_BODY_NODES,
    _SCOPE_BODY_NODES,
    _VAR_DECL_LIKE,
    _WALK_MAX_DEPTH,
)
from ._symbol_syntax import (
    _C_DECLARATOR_WRAPPERS,
    _bash_subscript_base,
    _c_declarator_name,
    _c_function_def_name,
    _extract_parent_classes,
    _find_parent_class,
    _node_text,
    _scala_given_type_text,
    _scala_symbol_from_node,
    _scala_symbol_name,
)
from ._symbol_walker import (
    _extract_imports,
    _extract_structure,
    _extract_symbols,
    _walk_for_symbols,
)

_EXCLUDE_DIRS = EXCLUDE_DIRS
_worker_parser: Parser | None = None


def _has_fts5(conn: sqlite3.Connection) -> bool:
    """Return whether the SQLite connection supports FTS5."""
    try:
        conn.execute(
            "SELECT fts5 FROM pragma_compile_options WHERE fts5 = 'ENABLE_FTS5'"
        )
        return True
    except sqlite3.OperationalError:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE IF EXISTS _fts5_probe")
            return True
        except sqlite3.OperationalError:
            return False


def _init_worker_parser() -> None:
    """Initialize the process-local parser used by index workers."""
    global _worker_parser
    _worker_parser = Parser()


def _worker_index_file(
    args: tuple[str, str, str] | tuple[str, str, str, IndexFileFingerprint | None],
) -> dict[str, Any]:
    """Parse one immutable descriptor-backed source on POSIX."""
    global _worker_parser
    abs_path, project_root, language = args[:3]
    expected = args[3] if len(args) == 4 else None
    rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
    try:
        if os.name == "posix":
            captured = safe_workspace_path(
                os.path.realpath(project_root),
                rel_path,
                deadline=time.monotonic() + 5.0,
                limit=64 * 1024 * 1024,
                expected_chain=expected.descriptor_chain if expected else None,
            )
            if captured.kind != "file" or captured.data is None:
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            source_code = decode_index_source(captured.data)
            leaf = tuple(int(value) for value in captured.metadata[-1].split(b","))
            opened = IndexFileFingerprint(
                mtime_ns=leaf[4],
                ctime_ns=leaf[5],
                file_size=leaf[3],
                device=leaf[0],
                inode=leaf[1],
                mode=leaf[2],
                content_hash=index_source_content_hash(source_code),
                descriptor_chain=expected.descriptor_chain if expected else (),
            )
            if expected is not None and (
                opened != expected or opened.content_hash != expected.content_hash
            ):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        else:
            # Windows retains legacy indexing, but cannot produce a P0.1
            # authoritative source certification.
            stat_result = os.stat(abs_path)
            with open(abs_path, encoding="utf-8", errors="replace") as source_file:
                source_code = source_file.read()
            opened = IndexFileFingerprint.from_stat(stat_result)
    except (OSError, SourceOracleError) as exc:
        return {
            "status": "source_changed" if expected is not None else "io_error",
            "rel_path": rel_path,
            "abs_path": abs_path,
            "reason": "file changed after candidate snapshot"
            if expected is not None
            else str(exc),
        }
    if _worker_parser is None:
        _worker_parser = Parser()
    result = _worker_parser.parse_code(source_code, language, filename=abs_path)
    if not result.success:
        return {
            "status": "parse_failed",
            "rel_path": rel_path,
            "abs_path": abs_path,
            "reason": result.error_message or "parse failed",
        }
    symbols = _extract_symbols(result.tree, source_code, language)
    imports = _extract_imports(symbols)
    structure = _extract_structure(symbols)
    call_edges = _extract_call_edges(result.tree, source_code, language, symbols)
    return _worker_payload(
        rel_path,
        abs_path,
        language,
        opened,
        source_code,
        symbols,
        imports,
        structure,
        call_edges,
    )


def _worker_payload(
    rel_path: str,
    abs_path: str,
    language: str,
    fingerprint: IndexFileFingerprint,
    source_code: str,
    symbols: dict[str, Any],
    imports: list[str],
    structure: dict[str, Any],
    call_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Serialize one successful extraction into a process-safe payload."""
    return {
        "status": "ok",
        "rel_path": rel_path,
        "abs_path": abs_path,
        "language": language,
        "content_hash": _content_hash(source_code),
        "mtime_ns": fingerprint.mtime_ns,
        "file_size": fingerprint.file_size,
        "symbols_count": len(symbols.get("symbols", [])),
        "symbols_json": json.dumps(symbols, ensure_ascii=False),
        "imports_json": json.dumps(imports, ensure_ascii=False),
        "structure_json": json.dumps(structure, ensure_ascii=False),
        "call_edges_json": json.dumps(call_edges, ensure_ascii=False),
        "symbol_rows": [
            (
                symbol.get("name", symbol.get("text", "")),
                symbol.get("kind", "unknown"),
                symbol.get("line", 0),
                symbol.get("end_line", 0),
            )
            for symbol in symbols.get("symbols", [])
        ],
    }


def _content_hash(source: str | bytes) -> str:
    """Return the stable SHA-256 hash used by cache invalidation."""
    if isinstance(source, str):
        source = source.encode("utf-8", errors="replace")
    return hashlib.sha256(source).hexdigest()


def _extract_call_edges(
    tree: Any, source_code: str, language: str, symbols: dict[str, Any]
) -> list[dict[str, Any]]:
    """Preserve the historical cache-extraction entry point."""
    from .call_edges import extract_call_edges

    return extract_call_edges(tree, source_code, language)
