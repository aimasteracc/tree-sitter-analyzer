"""Cached dependency graph helpers for change-impact.

The normal :class:`DependencyGraph` reparses every source file in a fresh
process. For agent feedback loops, the AST cache already stores file imports,
so change-impact can reconstruct the file-level graph with SQL + small import
string parsers and fall back to the parser-backed graph when no cache exists.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from ....ast_cache import _AST_CACHE_EXTRACTOR_VERSION
from ....cache.schema import CURRENT_SCHEMA_VERSION, already_applied_versions
from ....index_source_snapshot import (
    capture_current_source_snapshot,
    recorded_source_rows,
)
from ....project_graph import _IMPORT_RESOLVERS
from ....synapse_resolver import parse_imports

logger = logging.getLogger(__name__)

_JS_FROM_RE = re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]")
_JS_IMPORT_RE = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
_JS_REQUIRE_RE = re.compile(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)")
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([^;]+);?", re.MULTILINE)
_QUOTED_PATH_RE = re.compile(r"['\"]([^'\"]+)['\"]")
_RUST_USE_RE = re.compile(r"^\s*use\s+([^;]+);?", re.MULTILINE)


class CachedDependencyGraph:
    """Small DependencyGraph-compatible wrapper backed by ASTCache rows."""

    def __init__(self, project_root: str, nodes: set[str]) -> None:
        self.project_root = Path(project_root).resolve()
        self._nodes = nodes
        self._edges: set[tuple[str, str]] = set()
        self._deps: dict[str, set[str]] = defaultdict(set)
        self._dependents: dict[str, set[str]] = defaultdict(set)

    def add_edge(self, source: str, target: str) -> None:
        if source == target or target not in self._nodes:
            return
        self._edges.add((source, target))
        self._deps[source].add(target)
        self._dependents[target].add(source)

    def nodes(self) -> list[str]:
        return sorted(self._nodes)

    def all_nodes(self) -> frozenset[str]:
        """Return all nodes as frozenset — mirrors DependencyGraph.all_nodes()."""
        return frozenset(self._nodes)

    def edges(self) -> list[tuple[str, str]]:
        return sorted(self._edges)

    def has_node(self, file_rel: str) -> bool:
        """Return True if *file_rel* is a node in the graph (O(1) set lookup)."""
        return file_rel in self._nodes

    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._nodes)

    def edge_count(self) -> int:
        """Return the number of directed edges in the graph."""
        return len(self._edges)

    def dependencies_of(self, file_rel: str) -> list[str]:
        return sorted(self._deps.get(file_rel, set()))

    def dependents_of(self, file_rel: str) -> list[str]:
        return sorted(self._dependents.get(file_rel, set()))


def load_cached_dependency_graph(
    project_root: str | None,
) -> CachedDependencyGraph | None:
    """Return a dependency graph reconstructed from ``.ast-cache/index.db``.

    Returns ``None`` when the cache is absent, empty, or incompatible so callers
    can fall back to the parser-backed DependencyGraph.
    """
    if not project_root:
        return None
    db_path = Path(project_root) / ".ast-cache" / "index.db"
    if not db_path.is_file():
        return None

    conn: sqlite3.Connection | None = None
    try:
        # 查询不负责建库或迁移；旧索引交给现有源码分析路径处理。
        conn = sqlite3.connect(db_path.absolute().as_uri() + "?mode=rw", uri=True)
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        versions = already_applied_versions(conn)
        if CURRENT_SCHEMA_VERSION not in versions or any(
            version < 1 or version > CURRENT_SCHEMA_VERSION for version in versions
        ):
            return None
        recorded = recorded_source_rows(conn)
        rows = _cached_index_rows(conn)
        if not rows:
            return None
        nodes = {row["file_path"] for row in rows}
        graph = CachedDependencyGraph(project_root, nodes)
        for row in rows:
            _add_cached_import_edges(graph, row, nodes)
        # 用同一数据库读取事务的库存核对完整源码，拒绝陈旧或不可认证输入。
        current = capture_current_source_snapshot(str(graph.project_root))
        if current.state != "exact" or current.rows != recorded:
            return None
        return graph
    except Exception:
        logger.debug("cached dependency graph load failed", exc_info=True)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _cached_index_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT file_path, language, imports_json, symbols_json, extractor_version "
            "FROM ast_index"
        ).fetchall()
    except Exception:
        return []
    result = []
    for row in rows:
        item = dict(row)
        payload = json.loads(item["symbols_json"])
        imports = json.loads(item["imports_json"])
        if (
            item["extractor_version"] != _AST_CACHE_EXTRACTOR_VERSION
            or not isinstance(payload, dict)
            or payload.get("truncated_depth") is not False
            or payload.get("import_projection_complete") is not True
            or payload.get("syntax_error") is not False
            or not isinstance(imports, list)
        ):
            return []
        result.append(item)
    return result


def _add_cached_import_edges(
    graph: CachedDependencyGraph,
    row: dict[str, Any],
    nodes: set[str],
) -> None:
    source = row["file_path"]
    language = row["language"]
    resolver = _IMPORT_RESOLVERS.get(language)
    if resolver is None:
        return
    for module, is_relative in _iter_cached_import_modules(row):
        resolved = resolver(module, source, nodes, is_relative)
        if resolved:
            graph.add_edge(source, resolved.replace("\\", "/"))


def _iter_cached_import_modules(row: dict[str, Any]) -> list[tuple[str, bool]]:
    try:
        raw_imports = json.loads(row.get("imports_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    language = row.get("language", "")
    source = row.get("file_path", "")
    modules: list[tuple[str, bool]] = []
    for raw in raw_imports:
        text = raw.get("text", "") if isinstance(raw, dict) else str(raw)
        if not text:
            continue
        modules.extend(_modules_from_import_text(text, language, source))
    return modules


def _modules_from_import_text(
    text: str,
    language: str,
    source: str,
) -> list[tuple[str, bool]]:
    if language == "python":
        return _python_import_modules(text, language, source)
    if language in {"javascript", "typescript"}:
        return _js_ts_import_modules(text)
    if language == "java":
        return _java_import_modules(text)
    if language == "go":
        return [(path, path.startswith(".")) for path in _QUOTED_PATH_RE.findall(text)]
    if language == "rust":
        return _rust_import_modules(text)
    if language in {"c", "cpp"}:
        return [(path, True) for path in _QUOTED_PATH_RE.findall(text)]
    return []


def _python_import_modules(
    text: str,
    language: str,
    source: str,
) -> list[tuple[str, bool]]:
    modules: list[tuple[str, bool]] = []
    for entry in parse_imports(text, language, source):
        module = entry.module_path
        if entry.is_relative and module and set(module) == {"."} and entry.local_name:
            module = f"{module}{entry.alias_of or entry.local_name}"
        modules.append((module, entry.is_relative))
    return modules


def _js_ts_import_modules(text: str) -> list[tuple[str, bool]]:
    modules = [
        *_JS_FROM_RE.findall(text),
        *_JS_IMPORT_RE.findall(text),
        *_JS_REQUIRE_RE.findall(text),
    ]
    return [(module, module.startswith(".")) for module in modules]


def _java_import_modules(text: str) -> list[tuple[str, bool]]:
    modules: list[tuple[str, bool]] = []
    for raw in _JAVA_IMPORT_RE.findall(text):
        module = raw.strip()
        if module.startswith("java.") or module.endswith(".*"):
            continue
        modules.append((module, False))
    return modules


def _rust_import_modules(text: str) -> list[tuple[str, bool]]:
    modules: list[tuple[str, bool]] = []
    for raw in _RUST_USE_RE.findall(text):
        module = raw.strip()
        is_relative = module.startswith(("crate::", "super::", "self::"))
        modules.append((module, is_relative))
    return modules
