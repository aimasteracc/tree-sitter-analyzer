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

_SCHEMA_V3_CALL_EDGES = """
CREATE TABLE IF NOT EXISTS ast_call_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_name TEXT NOT NULL,
    caller_file TEXT NOT NULL,
    caller_line INTEGER NOT NULL,
    callee_name TEXT NOT NULL,
    callee_full TEXT NOT NULL DEFAULT '',
    callee_line INTEGER NOT NULL DEFAULT 0,
    file_path   TEXT NOT NULL,
    language    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ce_callee_name
    ON ast_call_edges(callee_name);

CREATE INDEX IF NOT EXISTS idx_ce_caller_name
    ON ast_call_edges(caller_name);

CREATE INDEX IF NOT EXISTS idx_ce_file_path
    ON ast_call_edges(file_path);
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
    call_edges = _extract_call_edges(result.tree, source_code, language, symbols)
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
        "call_edges_json": json.dumps(call_edges, ensure_ascii=False),
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
        symbols.append(
            {
                "kind": "import",
                "text": _node_text(node, source),
                "line": node.start_point[0] + 1,
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
    if node is None:
        return ""
    try:
        return source[node.start_byte : node.end_byte]
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


def _extract_call_edges(
    tree: Any, source_code: str, language: str, symbols: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract call edges from the AST using call_graph module helpers.

    Returns list of dicts with caller_name, caller_file (empty — filled later),
    caller_line, callee_name, callee_full, callee_line.
    """
    if tree is None:
        return []
    from . import call_graph as _cg

    definitions, calls = _cg._walk_tree(tree.root_node, source_code, language)

    file_funcs: dict[str, tuple[int, int]] = {}
    for d in definitions:
        file_funcs[d["name"]] = (d["start_line"], d.get("end_line", d["start_line"]))

    edges: list[dict[str, Any]] = []
    for call in calls:
        call_line = call["line"]
        caller_name = ""
        caller_line = 0
        for fname, (start, end) in file_funcs.items():
            if start <= call_line <= end:
                caller_name = fname
                caller_line = start
                break
        callee_name = call.get("name", "")
        callee_full = call.get("full_name", callee_name)
        callee_line = call_line
        receiver = call.get("receiver")
        if receiver:
            callee_name = f"{receiver}.{callee_name}"
        edges.append(
            {
                "caller_name": caller_name,
                "caller_line": caller_line,
                "callee_name": callee_name,
                "callee_full": callee_full,
                "callee_line": callee_line,
            }
        )
    return edges


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
        try:
            conn.executescript(_SCHEMA_V3_CALL_EDGES)
            conn.commit()
        except sqlite3.OperationalError:
            pass
        conn.commit()

    def index_file(self, file_path: str, language: str | None = None) -> dict[str, Any]:
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.project_root)
        if language is None:
            language = _language_from_ext(abs_path)
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

        source_code: str | None = None
        conn = self._get_conn()
        row = conn.execute(
            "SELECT content_hash, mtime_ns, file_size FROM ast_index WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
        if row is not None:
            if (
                row["mtime_ns"] == int(stat.st_mtime_ns)
                and row["file_size"] == stat.st_size
            ):
                return {"file": rel_path, "status": "cached", "reason": "unchanged"}

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
        call_edges = _extract_call_edges(result.tree, source_code, language, symbols)
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

        if self._fts5_available:
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

        conn.execute(
            "DELETE FROM ast_call_edges WHERE file_path = ?",
            (rel_path,),
        )
        for edge in call_edges:
            conn.execute(
                """INSERT INTO ast_call_edges
                   (caller_name, caller_file, caller_line,
                    callee_name, callee_full, callee_line,
                    file_path, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge["caller_name"],
                    rel_path,
                    edge["caller_line"],
                    edge["callee_name"],
                    edge["callee_full"],
                    edge["callee_line"],
                    rel_path,
                    language,
                ),
            )

        conn.commit()
        return {
            "file": rel_path,
            "status": "indexed",
            "symbols": len(symbols.get("symbols", [])),
            "call_edges": len(call_edges),
            "content_hash": content_hash[:16],
        }

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
        """
        if force:
            conn = self._get_conn()
            conn.execute("DELETE FROM ast_index")
            conn.commit()

        # Pass 1: enumerate candidate files and partition into
        # (already-cached, needs-parse). The "already-cached" partition
        # is handled inline because it is one SQL lookup per file with
        # no parsing — cheaper than dispatching to workers.
        candidates: list[tuple[str, str]] = []  # (abs_path, language)
        already_cached: list[dict[str, Any]] = []
        stats: dict[str, Any] = {
            "indexed": 0,
            "cached": 0,
            "errors": 0,
            "skipped": 0,
            "files": [],
        }
        count = 0
        conn = self._get_conn()
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
            if (
                row is not None
                and row["mtime_ns"] == int(stat.st_mtime_ns)
                and row["file_size"] == stat.st_size
            ):
                already_cached.append(
                    {"file": rel_path, "status": "cached", "reason": "unchanged"}
                )
                continue
            candidates.append((abs_path, lang))

        stats["cached"] += len(already_cached)
        stats["files"].extend(already_cached)

        # Pass 2: process the parse-needed list. Decide serial vs parallel.
        env_workers = os.environ.get("TSA_INDEX_WORKERS")
        if env_workers is not None:
            try:
                workers = int(env_workers)
            except ValueError:
                pass
        if workers is None:
            if len(candidates) < 64:
                workers = 0  # serial — spawn overhead not worth it on tiny sets
            else:
                workers = max(2, (os.cpu_count() or 4) - 1)

        if workers and workers >= 2 and len(candidates) >= 2:
            results = self._index_parallel(candidates, workers)
        else:
            results = [
                _worker_index_file((p, self.project_root, lang))
                for p, lang in candidates
            ]

        # Pass 3: single-writer SQLite insert wrapped in one transaction.
        # Batching avoids the per-insert fsync/commit cost that dominated
        # the post-parallel timing on medium projects (~1 ms per file).
        indexed_at = datetime.now(timezone.utc).isoformat()
        conn.execute("BEGIN")
        try:
            for r in results:
                if r["status"] == "io_error":
                    stats["errors"] += 1
                    stats["files"].append(
                        {
                            "file": r["rel_path"],
                            "status": "error",
                            "reason": r["reason"],
                        }
                    )
                    continue
                if r["status"] == "parse_failed":
                    stats["errors"] += 1
                    stats["files"].append(
                        {
                            "file": r["rel_path"],
                            "status": "error",
                            "reason": r["reason"],
                        }
                    )
                    continue
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
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        stats["total_files"] = count
        stats["workers"] = workers
        return stats

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

        conn.execute(
            "DELETE FROM ast_call_edges WHERE file_path = ?",
            (rel_path,),
        )
        call_edges = json.loads(r.get("call_edges_json", "[]"))
        for edge in call_edges:
            conn.execute(
                """INSERT INTO ast_call_edges
                   (caller_name, caller_file, caller_line,
                    callee_name, callee_full, callee_line,
                    file_path, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge["caller_name"],
                    rel_path,
                    edge["caller_line"],
                    edge["callee_name"],
                    edge["callee_full"],
                    edge["callee_line"],
                    rel_path,
                    r["language"],
                ),
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
        conn = self._get_conn()
        if language:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index WHERE language = ?",
                (language,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()

        results: list[dict[str, Any]] = []
        query_lower = query.lower()
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                name = sym.get("name", sym.get("text", ""))
                if query_lower in name.lower():
                    results.append(
                        {
                            "file": row["file_path"],
                            "language": row["language"],
                            **sym,
                        }
                    )
        return results

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
        conn.execute("DELETE FROM ast_call_edges WHERE file_path = ?", (rel,))
        cursor = conn.execute("DELETE FROM ast_index WHERE file_path = ?", (rel,))
        conn.commit()
        return cursor.rowcount > 0

    def get_call_edges(self) -> list[dict[str, Any]]:
        """Return all stored call edges from the cache."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT caller_name, caller_file, caller_line, "
                "callee_name, callee_full, callee_line, file_path, language "
                "FROM ast_call_edges"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def get_functions(self) -> list[dict[str, Any]]:
        """Return all indexed function definitions."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index"
        ).fetchall()
        functions: list[dict[str, Any]] = []
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                if sym.get("kind") == "function":
                    functions.append(
                        {
                            "name": sym["name"],
                            "file": row["file_path"],
                            "line": sym.get("line", 0),
                            "end_line": sym.get("end_line", 0),
                            "language": row["language"],
                            "params": sym.get("params", ""),
                        }
                    )
        return functions

    def get_functions_by_file(self, file_path: str) -> list[dict[str, Any]]:
        """Return indexed function definitions for a specific file."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT symbols_json, language FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return []
        symbols = json.loads(row["symbols_json"])
        return [
            {
                "name": sym["name"],
                "file": file_path,
                "line": sym.get("line", 0),
                "end_line": sym.get("end_line", 0),
                "language": row["language"],
                "params": sym.get("params", ""),
            }
            for sym in symbols.get("symbols", [])
            if sym.get("kind") == "function"
        ]

    def get_imports(self) -> dict[str, list[str]]:
        """Return per-file import lists from the cache.

        Returns dict mapping relative file path -> list of import text strings.
        Used by CachedCallGraph for import-aware cross-file call resolution.
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, imports_json FROM ast_index"
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result[row["file_path"]] = json.loads(row["imports_json"])
        return result

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
