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

_EXCLUDE_DIRS = frozenset({
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
})

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
        symbols.append({
            "kind": "function",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "params": params,
            "language": language,
        })
    elif node_type in _CLASS_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        symbols.append({
            "kind": "class",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "language": language,
        })
    elif node_type in _IMPORT_LIKE:
        symbols.append({
            "kind": "import",
            "text": _node_text(node, source),
            "line": node.start_point[0] + 1,
            "language": language,
        })
    elif node_type in _VAR_DECL_LIKE and name_node is not None:
        name = _node_text(name_node, source)
        if not name.startswith("_") or depth < 3:
            symbols.append({
                "kind": "variable",
                "name": name,
                "line": node.start_point[0] + 1,
                "language": language,
            })
    for child in node.children:
        _walk_for_symbols(child, source, symbols, language, depth + 1)


_FUNCTION_LIKE = frozenset({
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
})

_CLASS_LIKE = frozenset({
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
})

_IMPORT_LIKE = frozenset({
    "import_statement",
    "import_from_statement",
    "import_declaration",
    "require_statement",
    "use_declaration",
    "extern_crate_item",
    "package_declaration",
    "include_directive",
})

_VAR_DECL_LIKE = frozenset({
    "variable_declarator",
    "assignment_expression",
    "lexical_declaration",
    "variable_declaration",
    "const_declaration",
    "let_declaration",
})


def _node_text(node: Any, source: str) -> str:
    if node is None:
        return ""
    try:
        return source[node.start_byte:node.end_byte]
    except (IndexError, TypeError):
        return ""


def _count_nodes(node: Any) -> int:
    count = 1
    for child in node.children:
        count += _count_nodes(child)
    return count


def _extract_imports(symbols: dict[str, Any]) -> list[str]:
    return [
        s["text"]
        for s in symbols.get("symbols", [])
        if s.get("kind") == "import"
    ]


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
        conn.commit()

    def index_file(self, file_path: str, language: str | None = None) -> dict[str, Any]:
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.project_root)
        if language is None:
            language = _language_from_ext(abs_path)
        if language is None:
            return {"file": rel_path, "status": "skipped", "reason": "unsupported language"}

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
            if row["mtime_ns"] == int(stat.st_mtime_ns) and row["file_size"] == stat.st_size:
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
            return {"file": rel_path, "status": "error", "reason": result.error_message or "parse failed"}

        symbols = _extract_symbols(result.tree, source_code, language)
        imports = _extract_imports(symbols)
        structure = _extract_structure(symbols)
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
        conn.commit()
        return {
            "file": rel_path,
            "status": "indexed",
            "symbols": len(symbols.get("symbols", [])),
            "content_hash": content_hash[:16],
        }

    def index_project(
        self,
        max_files: int = 5000,
        force: bool = False,
    ) -> dict[str, Any]:
        if force:
            conn = self._get_conn()
            conn.execute("DELETE FROM ast_index")
            conn.commit()

        stats = {"indexed": 0, "cached": 0, "errors": 0, "skipped": 0, "files": []}
        count = 0
        for abs_path in _walk_source_files(self.project_root):
            if count >= max_files:
                break
            lang = _language_from_ext(abs_path)
            if lang is None:
                stats["skipped"] += 1
                continue
            result = self.index_file(abs_path, lang)
            if result["status"] == "indexed":
                stats["indexed"] += 1
            elif result["status"] == "cached":
                stats["cached"] += 1
            elif result["status"] == "error":
                stats["errors"] += 1
            else:
                stats["skipped"] += 1
            stats["files"].append(result)
            count += 1
        stats["total_files"] = count
        return stats

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

    def search_symbols(self, query: str, language: str | None = None) -> list[dict[str, Any]]:
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
                    results.append({
                        "file": row["file_path"],
                        "language": row["language"],
                        **sym,
                    })
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
        return {
            "total_files": total,
            "total_symbols": total_symbols,
            "by_language": {r["language"]: r["c"] for r in by_lang},
            "db_path": self.db_path,
        }

    def invalidate(self, file_path: str) -> bool:
        rel = os.path.relpath(os.path.abspath(file_path), self.project_root)
        conn = self._get_conn()
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
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_TO_LANG:
                yield os.path.join(dirpath, fname)
