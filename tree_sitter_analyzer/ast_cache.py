#!/usr/bin/env python3
"""
Pre-indexed AST Cache — SQLite-backed persistent parse result storage.

Stores serialized AST metadata (symbols, imports, structure) keyed by
content SHA-256 hash so re-analysis is instant without re-parsing.

CodeGraph parity: equivalent to CodeGraph's pre-indexed code intelligence.
Like CodeGraph, a one-time index step makes subsequent queries O(1).
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from .core.parser import Parser, ParseResult
from .project_graph import _language_from_ext
from .utils.tree_sitter_compat import get_node_text_safe

logger = logging.getLogger(__name__)

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS ast_index (
    file_path    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    language     TEXT NOT NULL,
    mtime_ns     INTEGER NOT NULL,
    file_size    INTEGER NOT NULL,
    symbols_json TEXT NOT NULL DEFAULT '{}',
    imports_json TEXT NOT NULL DEFAULT '[]',
    structure_json TEXT NOT NULL DEFAULT '{}',
    indexed_at   TEXT NOT NULL,
    PRIMARY KEY (file_path)
);

CREATE INDEX IF NOT EXISTS idx_ast_content_hash
    ON ast_index(content_hash);

CREATE INDEX IF NOT EXISTS idx_ast_language
    ON ast_index(language);
"""

_SCHEMA_V2_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS ast_symbols_fts
    USING fts5(
        name,
        kind,
        file_path,
        language,
        content=''
    );

CREATE TABLE IF NOT EXISTS ast_symbol_rows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        kind      TEXT NOT NULL,
        file_path TEXT NOT NULL,
        language  TEXT NOT NULL,
        line      INTEGER NOT NULL DEFAULT 0,
        end_line  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sym_rows_file_path
    ON ast_symbol_rows(file_path);
"""


def _has_fts5(conn: sqlite3.Connection) -> bool:
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


_EXCLUDE_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
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
        ".idea",
        ".vscode",
        ".claude",
        ".swarm",
        ".claude-flow",
        ".opencode",
    }
)

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".cs": "c_sharp",
}


def _worker_index_file(args: tuple[str, str, str]) -> dict[str, Any]:
    """Worker function used by ``ASTCache.index_project`` when running with
    a process pool. Must be module-level so it is picklable across spawn.

    Returns a dict with:
      * ``status`` in {"ok", "parse_failed", "io_error"}
      * ``abs_path``, ``rel_path``, ``language``
      * pre-serialised ``symbols_json`` / ``imports_json`` / ``structure_json``
      * ``content_hash`` / ``mtime_ns`` / ``file_size``
      * ``symbol_rows``: list of (name, kind, line, end_line) for FTS5 insert
    Tree-sitter ``Tree`` objects are NEVER returned — they are C objects
    that cannot be pickled. The worker discards them after extraction.
    """
    abs_path, project_root, language = args
    rel_path = os.path.relpath(abs_path, project_root)
    try:
        stat = os.stat(abs_path)
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            source_code = f.read()
    except OSError as exc:
        return {
            "status": "io_error",
            "rel_path": rel_path,
            "abs_path": abs_path,
            "reason": str(exc),
        }
    parser = Parser()
    result = parser.parse_file(abs_path, language)
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
    return {
        "status": "ok",
        "rel_path": rel_path,
        "abs_path": abs_path,
        "language": language,
        "content_hash": _content_hash(source_code),
        "mtime_ns": int(stat.st_mtime_ns),
        "file_size": int(stat.st_size),
        "symbols_count": len(symbols.get("symbols", [])),
        "symbols_json": json.dumps(symbols, ensure_ascii=False),
        "imports_json": json.dumps(imports, ensure_ascii=False),
        "structure_json": json.dumps(structure, ensure_ascii=False),
        "symbol_rows": [
            (
                sym.get("name", sym.get("text", "")),
                sym.get("kind", "unknown"),
                sym.get("line", 0),
                sym.get("end_line", 0),
            )
            for sym in symbols.get("symbols", [])
        ],
    }


def _content_hash(source: str | bytes) -> str:
    if isinstance(source, str):
        source = source.encode("utf-8", errors="replace")
    return hashlib.sha256(source).hexdigest()


def _first_text_child(
    node: Any,
    source: str,
    accepted_types: tuple[str, ...],
    names: list[str],
    strip_chars: str = "",
) -> None:
    """Find the first child whose ``type`` is in ``accepted_types``; append text.

    Used by Go/Python ``package_declaration``, JS ``require_statement``,
    C/C++ ``include_directive`` etc. — all share the "scan children for
    first matching type, append non-empty text, break" pattern.
    Optional ``strip_chars`` removes wrapping quotes / brackets so e.g.
    ``"foo"`` becomes ``foo``.

    r37du (dogfood): extracted from ``_extract_import_bound_names`` to
    collapse 4 mirror branches (depth 6) into 4 helper calls (depth 3).
    """
    for child in node.children:
        if child.type not in accepted_types:
            continue
        text = _node_text(child, source)
        if strip_chars:
            text = text.strip(strip_chars)
        if text:
            names.append(text)
            return


def _collect_extern_crate_names(node: Any, source: str, names: list[str]) -> None:
    """Collect non-``extern`` identifier children of a ``extern_crate_item``.

    Rust's ``extern crate foo;`` exposes ``foo`` as one of the
    identifier children alongside the literal ``extern`` keyword node.
    """
    for child in node.children:
        if child.type != "identifier":
            continue
        text = _node_text(child, source)
        if text and text != "extern":
            names.append(text)


def _rust_use_as_clause_alias(node: Any, source: str) -> str:
    """Return the alias bound by a Rust ``use_as_clause`` (``X as y``).

    Walks children for the literal ``as`` keyword and the identifier
    that follows it. Empty string when the shape doesn't match.
    """
    seen_as = False
    for grand in node.children:
        if grand.type == "as":
            seen_as = True
            continue
        if seen_as and grand.type == "identifier":
            return _node_text(grand, source)
    return ""


def _match_symbols_in_row(row: Any, query_lower: str) -> list[dict[str, Any]]:
    """Return matching symbol dicts from one ``ast_index`` row.

    Loads ``symbols_json``, then yields a flattened symbol dict for every
    symbol whose ``name`` contains ``query_lower`` (case-insensitive).
    The flattened dict adds ``file`` + ``language`` columns.

    r37cz (dogfood): module-level helper so ``_search_symbols_linear``
    stays at ≤3 levels of nesting.
    """
    matches: list[dict[str, Any]] = []
    symbols = json.loads(row["symbols_json"])
    for sym in symbols.get("symbols", []):
        name = sym.get("name", sym.get("text", ""))
        if query_lower not in name.lower():
            continue
        matches.append(
            {
                "file": row["file_path"],
                "language": row["language"],
                **sym,
            }
        )
    return matches


def _extract_symbols(tree: Any, source_code: str, language: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    if tree is None:
        return {"symbols": symbols, "node_count": 0}
    root = tree.root_node
    _walk_for_symbols(root, source_code, symbols, language)
    return {"symbols": symbols, "node_count": _count_nodes(root)}


def _walk_for_symbols(
    node: Any,
    source: str,
    symbols: list[dict[str, Any]],
    language: str,
    depth: int = 0,
) -> None:
    if depth > 20:
        return
    node_type = node.type
    name_node = node.child_by_field_name("name")
    if node_type in _FUNCTION_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        params_node = node.child_by_field_name("parameters")
        params = _node_text(params_node, source) if params_node else ""
        symbols.append(
            {
                "kind": "function",
                "name": name,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "params": params,
                "language": language,
            }
        )
    elif node_type in _CLASS_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        symbols.append(
            {
                "kind": "class",
                "name": name,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "language": language,
            }
        )
    elif node_type in _IMPORT_LIKE:
        # K7: ``from X import (A, B, C)`` previously stored the entire
        # parenthesised block — newlines, alias keyword, trailing
        # comments and all — as a single ``text`` field. The FTS5
        # writer then derived ``name = sym.get("name", sym.get("text"))``,
        # so an FTS search for ``execute`` returned import rows with
        # 280-char ``name`` values. Emit one row per *bound* identifier
        # so each row's ``name`` is a single locally bound symbol.
        line_no = node.start_point[0] + 1
        end_line_no = node.end_point[0] + 1
        bound_names = _extract_import_bound_names(node, source)
        if bound_names:
            for bound in bound_names:
                symbols.append(
                    {
                        "kind": "import",
                        "name": bound,
                        "text": bound,
                        "line": line_no,
                        "end_line": end_line_no,
                        "language": language,
                    }
                )
        else:
            # Defensive fallback for syntactically unusual import nodes
            # (wildcard imports, syntax errors, languages we don't
            # specifically handle below). Cap ``name`` at 100 chars so
            # the FTS row stays scannable.
            raw_text = _node_text(node, source).replace("\n", " ").strip()
            short_name = raw_text[:100]
            symbols.append(
                {
                    "kind": "import",
                    "name": short_name,
                    "text": short_name,
                    "line": line_no,
                    "end_line": end_line_no,
                    "language": language,
                }
            )
    elif node_type in _VAR_DECL_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        if not name.startswith("_") or depth < 3:
            symbols.append(
                {
                    "kind": "variable",
                    "name": name,
                    "line": node.start_point[0] + 1,
                    "language": language,
                }
            )
    for child in node.children:
        _walk_for_symbols(child, source, symbols, language, depth + 1)


def _extract_import_bound_names(node: Any, source: str) -> list[str]:
    """Return the locally bound identifiers introduced by an import-like node.

    K7: walks tree-sitter import nodes for the common language shapes and
    returns one bound identifier per imported symbol — the name the import
    actually introduces into the local namespace. ``import X as Y`` yields
    ``Y``; ``from m import A, B as b`` yields ``A`` and ``b``; ``import * as ns``
    yields ``ns``. Wildcard ``*`` imports return ``["*"]`` so the row is
    still searchable. Returns ``[]`` when the node shape isn't one we
    recognise (callers should fall back to a truncated raw-text row).

    The helper is intentionally heuristic — it covers the languages we
    index (Python, JS/TS, Java, Go, Rust, C/C++) by walking direct
    children rather than running per-language tree-sitter queries. It
    never raises; on unfamiliar shapes it returns ``[]``.
    """
    names: list[str] = []
    try:
        node_type = node.type
        if node_type == "import_from_statement":
            _collect_python_from_import(node, source, names)
        elif node_type == "import_statement":
            # Python ``import a, b``; JS/TS ``import x, { y } from 'foo'``;
            # the children disambiguate.
            _collect_import_statement(node, source, names)
        elif node_type == "import_declaration":
            # Java / JS — single-symbol shape predominantly, but JS uses
            # ``import_clause`` children that we walk recursively.
            _collect_import_declaration(node, source, names)
        elif node_type == "use_declaration":
            # Rust ``use mod::{A, B};``
            _collect_rust_use(node, source, names)
        elif node_type == "package_declaration":
            # Go ``package x`` — emit the package name itself.
            # r37du (dogfood): flatten nesting 6 → 3 via _first_text_child.
            _first_text_child(node, source, ("identifier", "package_identifier"), names)
        elif node_type == "require_statement":
            # Some JS / Lua dialects expose ``require_statement`` directly.
            _first_text_child(
                node,
                source,
                ("string", "string_fragment", "identifier"),
                names,
                strip_chars="'\"",
            )
        elif node_type == "include_directive":
            # C/C++ — header name is the user-facing handle.
            _first_text_child(
                node,
                source,
                ("string_literal", "system_lib_string"),
                names,
                strip_chars='<>"',
            )
        elif node_type == "extern_crate_item":
            _collect_extern_crate_names(node, source, names)
    except Exception:  # noqa: BLE001 — never crash the indexer on a weird node
        return []

    # De-duplicate while preserving order; drop empties and obvious noise.
    seen: set[str] = set()
    result: list[str] = []
    for raw in names:
        cleaned = raw.strip().strip("(){};,")
        if not cleaned or cleaned in {"import", "from", "as", "use", "pub"}:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _bound_name_from_aliased(node: Any, source: str) -> str:
    """Return the bound name from an ``aliased_import`` node.

    For ``A as a`` returns ``a``; falls back to ``A`` when no alias is
    present (defensive — tree-sitter normally emits the alias).
    """
    seen_as = False
    for child in node.children:
        if child.type == "as":
            seen_as = True
            continue
        if seen_as and child.type == "identifier":
            text = _node_text(child, source)
            if text:
                return text
    for child in node.children:
        if child.type in ("dotted_name", "identifier"):
            return _node_text(child, source)
    return ""


def _collect_python_from_import(node: Any, source: str, names: list[str]) -> None:
    """Collect bound names from a Python ``from X import ...`` statement.

    r37du (dogfood): flatten nesting 6 → 3 by extracting the
    aliased / dotted / wildcard handling into ``_collect_one_python_import_target``.
    The ``import_list`` branch reuses the same handler via inner loop.
    """
    saw_import = False
    for child in node.children:
        if child.type == "import":
            saw_import = True
            continue
        if not saw_import:
            continue
        if child.type == "import_list":
            for sub in child.children:
                _collect_one_python_import_target(sub, source, names)
            continue
        _collect_one_python_import_target(child, source, names)


def _collect_one_python_import_target(
    child: Any, source: str, names: list[str]
) -> None:
    """Append the bound name from one Python import target child node.

    Handles ``aliased_import`` (extract bound alias), ``dotted_name`` /
    ``identifier`` (raw name), and ``wildcard_import`` (emit ``*``).
    No-op on any other shape.
    """
    if child.type == "aliased_import":
        bound = _bound_name_from_aliased(child, source)
        if bound:
            names.append(bound)
        return
    if child.type in ("dotted_name", "identifier"):
        text = _node_text(child, source)
        if text:
            names.append(text)
        return
    if child.type == "wildcard_import":
        names.append("*")


def _collect_import_statement(node: Any, source: str, names: list[str]) -> None:
    # Python: import a, b.c, d as e — children include dotted_name +
    # aliased_import.
    # JS/TS: import defaultExp, { a, b as bb } from 'foo' — children
    # include identifier (default), import_clause -> named_imports ->
    # import_specifier.
    for child in node.children:
        if child.type == "aliased_import":
            bound = _bound_name_from_aliased(child, source)
            if bound:
                names.append(bound)
        elif child.type in ("dotted_name", "identifier"):
            text = _node_text(child, source)
            if text:
                names.append(text)
        elif child.type == "import_clause":
            _collect_js_import_clause(child, source, names)


def _collect_js_import_clause(node: Any, source: str, names: list[str]) -> None:
    # r37cw (dogfood): flattened nesting 8 → 3 by extracting the
    # ``named_imports`` / ``namespace_import`` branches into helpers.
    for child in node.children:
        if child.type == "identifier":
            text = _node_text(child, source)
            if text:
                names.append(text)
        elif child.type == "named_imports":
            _collect_named_imports(child, source, names)
        elif child.type == "namespace_import":
            _collect_namespace_import(child, source, names)


def _collect_named_imports(node: Any, source: str, names: list[str]) -> None:
    """Harvest bound names from a JS ``named_imports`` node.

    Pattern: ``{ a, b as c }`` — for each ``import_specifier``, the bound
    name is the final identifier (after any ``as`` rename).
    """
    for sub in node.children:
        if sub.type != "import_specifier":
            continue
        bound = _last_identifier_text(sub, source)
        if bound:
            names.append(bound)


def _collect_namespace_import(node: Any, source: str, names: list[str]) -> None:
    """Harvest bound names from a JS ``namespace_import`` (``* as ns``)."""
    for sub in node.children:
        if sub.type != "identifier":
            continue
        text = _node_text(sub, source)
        if text:
            names.append(text)


def _last_identifier_text(node: Any, source: str) -> str:
    """Return the text of the last ``identifier`` child of ``node``.

    Empty string if no identifier is present. Used by JS import-specifier
    extraction where ``a as b`` exposes ``b`` as the bound name.
    """
    last = ""
    for grand in node.children:
        if grand.type != "identifier":
            continue
        text = _node_text(grand, source)
        if text:
            last = text
    return last


def _collect_import_declaration(node: Any, source: str, names: list[str]) -> None:
    # Java: import a.b.C; — last segment of the dotted scoped_identifier
    # is the bound name. We emit the full path so users can search either
    # the leaf or the qualified path.
    for child in node.children:
        if child.type in ("scoped_identifier", "identifier"):
            text = _node_text(child, source)
            if text:
                # Use the leaf as the searchable name to match
                # function/class kinds (which use bare identifiers).
                leaf = text.rsplit(".", 1)[-1]
                names.append(leaf)
        elif child.type == "import_clause":
            _collect_js_import_clause(child, source, names)


def _collect_rust_use(node: Any, source: str, names: list[str]) -> None:
    # Rust use trees can be deeply nested: ``use a::b::{C, D as d};``.
    # Walk descendants and harvest each terminal identifier.
    stack: list[Any] = [node]
    while stack:
        cur = stack.pop()
        for child in cur.children:
            if child.type == "scoped_use_list":
                stack.append(child)
            elif child.type == "use_list":
                stack.append(child)
            elif child.type == "use_as_clause":
                # r37du (dogfood): flatten nesting 6 → 3 via
                # _rust_use_as_clause_alias helper.
                bound = _rust_use_as_clause_alias(child, source)
                if bound:
                    names.append(bound)
            elif child.type == "scoped_identifier":
                text = _node_text(child, source)
                if text:
                    names.append(text.rsplit("::", 1)[-1])
            elif child.type == "identifier":
                text = _node_text(child, source)
                if text and text not in {"use", "pub", "self", "crate"}:
                    names.append(text)


_FUNCTION_LIKE = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "function_item",
        "method_declaration",
        "constructor_declaration",
        "lambda_expression",
        "anonymous_function",
        "class_method",
        "member_function",
        "function_declarator",
        "declaration",
        "init_declarator",
    }
)

_CLASS_LIKE = frozenset(
    {
        "class_definition",
        "class_declaration",
        "class",
        "interface_declaration",
        "struct_item",
        "enum_declaration",
        "enum",
        "trait_declaration",
        "impl_item",
        "struct_declaration",
        "type_declaration",
    }
)

_IMPORT_LIKE = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "require_statement",
        "use_declaration",
        "extern_crate_item",
        "package_declaration",
        "include_directive",
    }
)

_VAR_DECL_LIKE = frozenset(
    {
        "variable_declarator",
        "assignment_expression",
        "lexical_declaration",
        "variable_declaration",
        "const_declaration",
        "let_declaration",
    }
)


def _node_text(node: Any, source: str) -> str:
    # ``node.start_byte``/``end_byte`` are UTF-8 byte offsets, so we must
    # encode-then-slice — direct ``str`` slicing corrupts multibyte sources.
    if node is None:
        return ""
    try:
        return get_node_text_safe(node, source)
    except (IndexError, TypeError):
        return ""


def _count_nodes(node: Any) -> int:
    count = 1
    for child in node.children:
        count += _count_nodes(child)
    return count


def _extract_imports(symbols: dict[str, Any]) -> list[str]:
    return [s["text"] for s in symbols.get("symbols", []) if s.get("kind") == "import"]


def _extract_structure(symbols: dict[str, Any]) -> dict[str, Any]:
    functions = []
    classes = []
    for s in symbols.get("symbols", []):
        if s["kind"] == "function":
            functions.append({"name": s["name"], "line": s["line"]})
        elif s["kind"] == "class":
            classes.append({"name": s["name"], "line": s["line"]})
    return {"functions": functions, "classes": classes}


class ASTCache:
    """
    SQLite-backed persistent AST cache.

    Stores per-file parse metadata (symbols, imports, structure) keyed by
    content hash. Re-analysis of unchanged files is a simple DB lookup.
    """

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        self.project_root = os.path.abspath(project_root)
        if db_path is None:
            db_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        self.db_path = db_path
        self._local = threading.local()
        self._parser = Parser()
        self._index_lock = threading.Lock()
        self._fts5_available: bool | None = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA_V1)
        if self._fts5_available is None:
            self._fts5_available = _has_fts5(conn)
        if self._fts5_available:
            try:
                conn.executescript(_SCHEMA_V2_FTS)
                conn.commit()
            except sqlite3.OperationalError:
                self._fts5_available = False
        conn.commit()

    def index_file(self, file_path: str, language: str | None = None) -> dict[str, Any]:
        """Parse one file and persist its symbols / imports / structure.

        r37cx (dogfood): 110 lines → ~30 of phase dispatch.
        Sub-helpers: ``_resolve_language_for_path``, ``_check_existing_index``,
        ``_persist_indexed_file``, ``_reindex_fts_rows``.
        """
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.project_root)

        language = self._resolve_language_for_path(abs_path, language)
        if language is None:
            return {
                "file": rel_path,
                "status": "skipped",
                "reason": "unsupported language",
            }

        try:
            stat = os.stat(abs_path)
        except OSError as e:
            return {"file": rel_path, "status": "error", "reason": str(e)}

        conn = self._get_conn()
        row = conn.execute(
            "SELECT content_hash, mtime_ns, file_size FROM ast_index WHERE file_path = ?",
            (rel_path,),
        ).fetchone()

        cache_response = self._check_existing_index(row, stat, rel_path)
        if cache_response is not None:
            return cache_response

        try:
            with open(abs_path, encoding="utf-8", errors="replace") as f:
                source_code = f.read()
        except OSError as e:
            return {"file": rel_path, "status": "error", "reason": str(e)}

        content_hash = _content_hash(source_code)
        if row is not None and row["content_hash"] == content_hash:
            conn.execute(
                "UPDATE ast_index SET mtime_ns = ?, file_size = ? WHERE file_path = ?",
                (int(stat.st_mtime_ns), stat.st_size, rel_path),
            )
            conn.commit()
            return {"file": rel_path, "status": "cached", "reason": "content unchanged"}

        result: ParseResult = self._parser.parse_file(abs_path, language)
        if not result.success:
            return {
                "file": rel_path,
                "status": "error",
                "reason": result.error_message or "parse failed",
            }

        symbols = _extract_symbols(result.tree, source_code, language)
        imports = _extract_imports(symbols)
        structure = _extract_structure(symbols)
        self._persist_indexed_file(
            conn,
            rel_path=rel_path,
            content_hash=content_hash,
            language=language,
            stat=stat,
            symbols=symbols,
            imports=imports,
            structure=structure,
        )
        if self._fts5_available:
            self._reindex_fts_rows(conn, rel_path, language, symbols)
        conn.commit()
        return {
            "file": rel_path,
            "status": "indexed",
            "symbols": len(symbols.get("symbols", [])),
            "content_hash": content_hash[:16],
        }

    @staticmethod
    def _resolve_language_for_path(abs_path: str, language: str | None) -> str | None:
        """Pick the language to parse with, defaulting to file-extension lookup."""
        if language is not None:
            return language
        return _language_from_ext(abs_path)

    @staticmethod
    def _check_existing_index(
        row: Any, stat: os.stat_result, rel_path: str
    ) -> dict[str, Any] | None:
        """Return a "cached" response if stat-based fingerprint matches, else None.

        Fast path: if mtime_ns + file_size both match the stored row, skip the
        file read entirely. The caller then proceeds to read+hash on a miss.
        """
        if row is None:
            return None
        if row["mtime_ns"] != int(stat.st_mtime_ns):
            return None
        if row["file_size"] != stat.st_size:
            return None
        return {"file": rel_path, "status": "cached", "reason": "unchanged"}

    @staticmethod
    def _persist_indexed_file(
        conn: Any,
        *,
        rel_path: str,
        content_hash: str,
        language: str,
        stat: os.stat_result,
        symbols: dict[str, Any],
        imports: Any,
        structure: Any,
    ) -> None:
        """Upsert the ast_index row for ``rel_path``."""
        indexed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO ast_index
               (file_path, content_hash, language, mtime_ns, file_size,
                symbols_json, imports_json, structure_json, indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel_path,
                content_hash,
                language,
                int(stat.st_mtime_ns),
                stat.st_size,
                json.dumps(symbols, ensure_ascii=False),
                json.dumps(imports, ensure_ascii=False),
                json.dumps(structure, ensure_ascii=False),
                indexed_at,
            ),
        )

    @staticmethod
    def _reindex_fts_rows(
        conn: Any, rel_path: str, language: str, symbols: dict[str, Any]
    ) -> None:
        """Replace FTS5 symbol rows for ``rel_path`` (delete then re-insert)."""
        conn.execute(
            "DELETE FROM ast_symbol_rows WHERE file_path = ?",
            (rel_path,),
        )
        conn.execute(
            "DELETE FROM ast_symbols_fts WHERE file_path = ?",
            (rel_path,),
        )
        for sym in symbols.get("symbols", []):
            sym_name = sym.get("name", sym.get("text", ""))
            sym_kind = sym.get("kind", "unknown")
            sym_line = sym.get("line", 0)
            sym_end = sym.get("end_line", 0)
            row_id = conn.execute(
                """INSERT INTO ast_symbol_rows
                   (name, kind, file_path, language, line, end_line)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sym_name, sym_kind, rel_path, language, sym_line, sym_end),
            ).lastrowid
            conn.execute(
                """INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language)
                   VALUES (?, ?, ?, ?, ?)""",
                (row_id, sym_name, sym_kind, rel_path, language),
            )

    def index_project(
        self,
        max_files: int = 5000,
        force: bool = False,
        *,
        workers: int | None = None,
    ) -> dict[str, Any]:
        """Index every source file under ``self.project_root``.

        PERF-4: when there are enough files to amortise the spawn cost,
        we farm parse + extract out to a process pool. Workers return
        already-serialised JSON; this thread does the SQLite write.
        Workers never return tree-sitter ``Tree`` objects (C objects,
        not picklable).

        ``workers``:
          * ``None`` (default): pick a sensible value — 0 if files < 64
            (serial path, no spawn cost), otherwise
            ``max(2, (os.cpu_count() or 4) - 1)``.
          * ``0`` or ``1``: force serial path.
          * ``>=2``: use that many worker processes.
          Configurable per-call; overridden by ``TSA_INDEX_WORKERS`` env var.

        r37cy (dogfood): 143 lines → ~25 lines of phase dispatch.
        Sub-helpers: ``_clear_index_on_force``, ``_enumerate_index_candidates``,
        ``_resolve_worker_count``, ``_run_candidate_workers``,
        ``_apply_index_results``.
        """
        if force:
            self._clear_index_on_force()

        stats = self._empty_index_stats()
        candidates, count = self._enumerate_index_candidates(max_files, stats)
        workers = self._resolve_worker_count(workers, len(candidates))
        results = self._run_candidate_workers(candidates, workers)
        self._apply_index_results(results, stats)
        stats["total_files"] = count
        stats["workers"] = workers
        return stats

    @staticmethod
    def _empty_index_stats() -> dict[str, Any]:
        """Return the baseline ``index_project`` stats dict (mutated in place)."""
        return {
            "indexed": 0,
            "cached": 0,
            "errors": 0,
            "skipped": 0,
            "files": [],
        }

    def _clear_index_on_force(self) -> None:
        """Drop every row in ``ast_index`` (used when ``force=True``)."""
        conn = self._get_conn()
        conn.execute("DELETE FROM ast_index")
        conn.commit()

    def _enumerate_index_candidates(
        self, max_files: int, stats: dict[str, Any]
    ) -> tuple[list[tuple[str, str]], int]:
        """Walk source files; partition into (needs-parse, already-cached).

        Already-cached entries are appended to ``stats['files']`` (and
        ``stats['cached']`` is incremented) inline because the cache check
        is one SQL lookup with no parsing — cheaper than dispatching to
        workers. Returns ``(candidates, count)`` where ``candidates`` is
        the list of ``(abs_path, language)`` tuples for the parse phase.
        """
        conn = self._get_conn()
        candidates: list[tuple[str, str]] = []
        already_cached: list[dict[str, Any]] = []
        count = 0
        for abs_path in _walk_source_files(self.project_root):
            if count >= max_files:
                break
            count += 1
            lang = _language_from_ext(abs_path)
            if lang is None:
                stats["skipped"] += 1
                continue
            rel_path = os.path.relpath(abs_path, self.project_root)
            try:
                stat = os.stat(abs_path)
            except OSError as e:
                stats["errors"] += 1
                stats["files"].append(
                    {"file": rel_path, "status": "error", "reason": str(e)}
                )
                continue
            row = conn.execute(
                "SELECT mtime_ns, file_size FROM ast_index WHERE file_path = ?",
                (rel_path,),
            ).fetchone()
            if self._cache_matches_stat(row, stat):
                already_cached.append(
                    {"file": rel_path, "status": "cached", "reason": "unchanged"}
                )
                continue
            candidates.append((abs_path, lang))

        stats["cached"] += len(already_cached)
        stats["files"].extend(already_cached)
        return candidates, count

    @staticmethod
    def _cache_matches_stat(row: Any, stat: os.stat_result) -> bool:
        """Return True iff ``row`` exists and its mtime/size match ``stat``."""
        if row is None:
            return False
        if row["mtime_ns"] != int(stat.st_mtime_ns):
            return False
        return bool(row["file_size"] == stat.st_size)

    @staticmethod
    def _resolve_worker_count(workers: int | None, candidate_count: int) -> int:
        """Pick a worker count, honouring ``TSA_INDEX_WORKERS`` env override.

        Default rule: use a process pool when the candidate list is large
        enough (``>= 64``) to amortise spawn cost; otherwise stay serial.
        """
        env_workers = os.environ.get("TSA_INDEX_WORKERS")
        if env_workers is not None:
            try:
                workers = int(env_workers)
            except ValueError:
                pass
        if workers is None:
            if candidate_count < 64:
                workers = 0  # serial — spawn overhead not worth it on tiny sets
            else:
                workers = max(2, (os.cpu_count() or 4) - 1)
        return workers

    def _run_candidate_workers(
        self, candidates: list[tuple[str, str]], workers: int
    ) -> list[dict[str, Any]]:
        """Parse the candidate list either serially or via a process pool."""
        if workers and workers >= 2 and len(candidates) >= 2:
            return self._index_parallel(candidates, workers)
        return [
            _worker_index_file((p, self.project_root, lang)) for p, lang in candidates
        ]

    def _apply_index_results(
        self, results: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        """Apply parse results in a single SQLite transaction (single writer).

        Batching avoids the per-insert fsync/commit cost that dominated the
        post-parallel timing on medium projects (~1 ms per file).
        """
        # r37du (dogfood): flatten nesting 6 → 4 by extracting the
        # per-result handling into _apply_one_index_result.
        conn = self._get_conn()
        indexed_at = datetime.now(timezone.utc).isoformat()
        conn.execute("BEGIN")
        try:
            for r in results:
                self._apply_one_index_result(r, stats, indexed_at)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _apply_one_index_result(
        self,
        r: dict[str, Any],
        stats: dict[str, Any],
        indexed_at: str,
    ) -> None:
        """Apply one parse result to ``stats`` + insert into the index table.

        Error results (``io_error`` / ``parse_failed``) bump
        ``stats['errors']`` and record an ``error`` files-row. Success
        results call ``_insert_index_row``, bump ``stats['indexed']``,
        and record an ``indexed`` files-row with symbol count + short
        content hash.

        r37du (dogfood): lifted out of ``_apply_index_results`` to flatten
        nesting 6 → 4.
        """
        if r["status"] in ("io_error", "parse_failed"):
            stats["errors"] += 1
            stats["files"].append(
                {
                    "file": r["rel_path"],
                    "status": "error",
                    "reason": r["reason"],
                }
            )
            return
        self._insert_index_row(r, indexed_at)
        stats["indexed"] += 1
        stats["files"].append(
            {
                "file": r["rel_path"],
                "status": "indexed",
                "symbols": r["symbols_count"],
                "content_hash": r["content_hash"][:16],
            }
        )

    def _index_parallel(
        self, candidates: list[tuple[str, str]], workers: int
    ) -> list[dict[str, Any]]:
        """Dispatch parse+extract to a process pool. Spawn context so the
        behaviour is identical on macOS and Linux (fork inherits SQLite
        handles in a way SQLite does not like)."""
        from multiprocessing import get_context

        ctx = get_context("spawn")
        args_iter = [(p, self.project_root, lang) for p, lang in candidates]
        results: list[dict[str, Any]] = []
        with ctx.Pool(processes=workers) as pool:
            for r in pool.imap_unordered(_worker_index_file, args_iter, chunksize=8):
                results.append(r)
        return results

    def _insert_index_row(self, r: dict[str, Any], indexed_at: str) -> None:
        """Write one worker result to SQLite (main table + optional FTS5)."""
        conn = self._get_conn()
        rel_path = r["rel_path"]
        conn.execute(
            """INSERT OR REPLACE INTO ast_index
               (file_path, content_hash, language, mtime_ns, file_size,
                symbols_json, imports_json, structure_json, indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel_path,
                r["content_hash"],
                r["language"],
                r["mtime_ns"],
                r["file_size"],
                r["symbols_json"],
                r["imports_json"],
                r["structure_json"],
                indexed_at,
            ),
        )
        if not self._fts5_available:
            return
        conn.execute(
            "DELETE FROM ast_symbol_rows WHERE file_path = ?",
            (rel_path,),
        )
        conn.execute(
            "DELETE FROM ast_symbols_fts WHERE file_path = ?",
            (rel_path,),
        )
        for sym_name, sym_kind, sym_line, sym_end in r["symbol_rows"]:
            row_id = conn.execute(
                """INSERT INTO ast_symbol_rows
                   (name, kind, file_path, language, line, end_line)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sym_name, sym_kind, rel_path, r["language"], sym_line, sym_end),
            ).lastrowid
            conn.execute(
                """INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language)
                   VALUES (?, ?, ?, ?, ?)""",
                (row_id, sym_name, sym_kind, rel_path, r["language"]),
            )

    def lookup(self, file_path: str) -> dict[str, Any] | None:
        rel = os.path.relpath(os.path.abspath(file_path), self.project_root)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM ast_index WHERE file_path = ?",
            (rel,),
        ).fetchone()
        if row is None:
            return None
        return {
            "file": row["file_path"],
            "content_hash": row["content_hash"],
            "language": row["language"],
            "symbols": json.loads(row["symbols_json"]),
            "imports": json.loads(row["imports_json"]),
            "structure": json.loads(row["structure_json"]),
            "indexed_at": row["indexed_at"],
        }

    def search_symbols(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        if self._fts5_available:
            return self.fts_search(query, language=language)
        return self._search_symbols_linear(query, language)

    def fts_search(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._fts5_available:
            return self._search_symbols_linear(query, language)

        conn = self._get_conn()
        fts_query = " OR ".join(f'"{term}"' for term in query.split() if term)
        if not fts_query:
            fts_query = f'"{query}"'

        if language:
            sql = """
                SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line
                FROM ast_symbols_fts f
                JOIN ast_symbol_rows r ON f.rowid = r.id
                WHERE ast_symbols_fts MATCH ? AND r.language = ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_query, language, limit)).fetchall()
        else:
            sql = """
                SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line
                FROM ast_symbols_fts f
                JOIN ast_symbol_rows r ON f.rowid = r.id
                WHERE ast_symbols_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_query, limit)).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "file": row["file_path"],
                    "language": row["language"],
                    "line": row["line"],
                    "end_line": row["end_line"],
                }
            )
        return results

    def _search_symbols_linear(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        """Linear ``LIKE``-style symbol search (used when FTS5 is unavailable).

        r37cz (dogfood): flattened nesting 7 → 3 by extracting the
        per-row match loop into ``_match_symbols_in_row``.
        """
        rows = self._fetch_index_rows_for_search(language)
        results: list[dict[str, Any]] = []
        query_lower = query.lower()
        for row in rows:
            results.extend(_match_symbols_in_row(row, query_lower))
        return results

    def _fetch_index_rows_for_search(self, language: str | None) -> list[Any]:
        """Return ``ast_index`` rows, optionally filtered by ``language``."""
        conn = self._get_conn()
        if language:
            return list(
                conn.execute(
                    "SELECT file_path, symbols_json, language FROM ast_index WHERE language = ?",
                    (language,),
                ).fetchall()
            )
        return list(
            conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()
        )

    def get_stats(self) -> dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM ast_index").fetchone()["c"]
        by_lang = conn.execute(
            "SELECT language, COUNT(*) as c FROM ast_index GROUP BY language ORDER BY c DESC"
        ).fetchall()
        total_symbols = 0
        for row in conn.execute("SELECT symbols_json FROM ast_index").fetchall():
            syms = json.loads(row["symbols_json"])
            total_symbols += len(syms.get("symbols", []))
        stats: dict[str, Any] = {
            "total_files": total,
            "total_symbols": total_symbols,
            "by_language": {r["language"]: r["c"] for r in by_lang},
            "db_path": self.db_path,
            "fts5_available": bool(self._fts5_available),
        }
        if self._fts5_available:
            try:
                fts_count = conn.execute(
                    "SELECT COUNT(*) as c FROM ast_symbol_rows"
                ).fetchone()["c"]
                stats["fts_indexed_symbols"] = fts_count
            except sqlite3.OperationalError:
                pass
        return stats

    def invalidate(self, file_path: str) -> bool:
        rel = os.path.relpath(os.path.abspath(file_path), self.project_root)
        conn = self._get_conn()
        if self._fts5_available:
            conn.execute("DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel,))
            conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel,))
        cursor = conn.execute("DELETE FROM ast_index WHERE file_path = ?", (rel,))
        conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def _walk_source_files(project_root: str) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_TO_LANG:
                yield os.path.join(dirpath, fname)
