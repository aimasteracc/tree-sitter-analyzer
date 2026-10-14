"""逐文件内容校验的索引依赖图：change-impact 复用持久化 AST 索引（Issue #1591）。

整图认证（``load_cached_dependency_graph``）要求全部源码与索引快照完全一致，并依赖
POSIX 的 ``dir_fd``/``O_NOFOLLOW`` 遍历；Windows 上它固定返回
``SOURCE_SCOPE_UNSUPPORTED``，而且只要有一个文件被编辑（change-impact 的常态）就
整体失效，于是每次都从源码重建并把每个文件完整解析两次。

这里改为逐文件决定导入证据来源，边的语义与 ``DependencyGraph._build`` 完全一致：

* 节点集合与 ``DependencyGraph`` 使用同一遍历函数 ``iter_graph_source_files``；
* 索引行可信（``row_is_admissible``）、语言一致且当前内容哈希与索引记录相同时，只重新
  解析索引里保存的导入语句文本，再走同一套 ``walk_imports`` + 解析器规则；
* 其余文件（已编辑、新增、索引缺失或证据不完整）按源码完整解析。

每个文件都会重新读取并哈希一次：等长、等 mtime 的改写不能靠时间戳证明内容未变
（见 ``incremental_sync_support.file_changed``），所以绝不在未校验内容时使用索引行。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ....cache.generation_routing import resolve_index_path
from ....cache.schema import CURRENT_SCHEMA_VERSION, already_applied_versions
from ....constants import EXCLUDE_DIRS, GRAPH_SOURCE_EXTS
from ....core.parser import Parser
from ....import_extractors import walk_imports
from ....incremental_sync_support import file_content_hash
from ....project_graph import (
    _IMPORT_RESOLVERS,
    DependencyGraph,
    _language_from_ext,
    extract_imports_from_file,
    iter_graph_source_files,
    python_submodule_import_targets,
)
from .change_impact_cached_graph import CachedDependencyGraph, row_is_admissible

logger = logging.getLogger(__name__)


class VerifiedIndexGraph(CachedDependencyGraph):
    """记录每个节点的导入证据来自索引还是源码，供响应如实说明。"""

    def __init__(self, project_root: str, nodes: set[str]) -> None:
        super().__init__(project_root, nodes)
        self.index_files = 0
        self.source_files = 0

    def add_edge(self, source: str, target: str) -> None:
        """与 ``DependencyGraph`` 一致：保留自导入边，只丢弃图外目标。"""
        if target not in self._nodes:
            return
        self._edges.add((source, target))
        self._deps[source].add(target)
        self._dependents[target].add(source)


def load_verified_index_graph(project_root: str | None) -> VerifiedIndexGraph | None:
    """索引可读时返回逐文件校验的依赖图；无索引或索引不兼容时返回 ``None``。"""
    if not project_root:
        return None
    rows = _read_index_rows(project_root)
    if not rows:
        return None
    root = Path(project_root).resolve()
    # os.walk 从 root 出发，路径必然位于 root 之下。
    sources = {
        str(path.relative_to(root)).replace("\\", "/"): str(path)
        for path in iter_graph_source_files(root, set(GRAPH_SOURCE_EXTS), EXCLUDE_DIRS)
    }
    nodes = set(sources)
    graph = VerifiedIndexGraph(str(root), nodes)
    parser = Parser()
    for rel, abs_path in sources.items():
        language = _language_from_ext(rel)
        row = rows.get(rel)
        if (
            row is not None
            and language is not None
            and row["language"] == language
            and _content_matches(abs_path, str(row["content_hash"]))
        ):
            imports = _imports_from_index_row(parser, row, language)
            graph.index_files += 1
        else:
            imports = extract_imports_from_file(abs_path, language)
            graph.source_files += 1
        _add_import_edges(graph, rel, imports, nodes)
    return graph


def dependency_graph_provenance(graph: Any | None) -> dict[str, Any]:
    """说明依赖图的证据来源；未使用索引时如实标注为源码重建。"""
    if graph is None:
        return {"source": "unavailable", "index_files": 0, "source_files": 0}
    if isinstance(graph, VerifiedIndexGraph):
        return {
            "source": "index" if graph.source_files == 0 else "index+source",
            "index_files": graph.index_files,
            "source_files": graph.source_files,
        }
    if isinstance(graph, CachedDependencyGraph):
        return {
            "source": "certified_index",
            "index_files": graph.node_count(),
            "source_files": 0,
        }
    if isinstance(graph, DependencyGraph):
        return {
            "source": "source",
            "index_files": 0,
            "source_files": graph.node_count(),
        }
    return {"source": "unknown", "index_files": 0, "source_files": 0}


def _read_index_rows(project_root: str) -> dict[str, dict[str, Any]]:
    """只读取可信行；查询不建库、不迁移，任何异常都退回源码重建。"""
    db_path = resolve_index_path(project_root)
    if not db_path.is_file():
        return {}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path.absolute().as_uri() + "?mode=rw", uri=True)
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        # 版本检查与行读取处于同一读事务，避免读到不同代的混合状态。
        conn.execute("BEGIN")
        versions = already_applied_versions(conn)
        if CURRENT_SCHEMA_VERSION not in versions or any(
            version < 1 or version > CURRENT_SCHEMA_VERSION for version in versions
        ):
            return {}
        rows = conn.execute(
            "SELECT file_path, language, imports_json, symbols_json, "
            "extractor_version, content_hash FROM ast_index"
        ).fetchall()
        return {
            item["file_path"]: item
            for item in (dict(row) for row in rows)
            if row_is_admissible(item)
        }
    except Exception:
        logger.debug("verified index graph rows unavailable", exc_info=True)
        return {}
    finally:
        if conn is not None:
            conn.close()


def _content_matches(abs_path: str, recorded_hash: str) -> bool:
    """用与索引写入端相同的解码与换行归一化比对内容；读失败视为已变化。"""
    try:
        return file_content_hash(abs_path) == recorded_hash
    except OSError:
        return False


def _imports_from_index_row(
    parser: Parser, row: dict[str, Any], language: str
) -> list[dict[str, Any]]:
    """只解析索引保存的导入语句文本，得到与整文件 ``walk_imports`` 相同的导入。"""
    imports: list[dict[str, Any]] = []
    for raw in json.loads(row["imports_json"]):
        text = raw.get("text", "") if isinstance(raw, dict) else raw
        if not text:
            continue
        result = parser.parse_code(text, language)
        if result.tree is not None:
            walk_imports(result.tree.root_node, result.source_code, language, imports)
    return imports


def _add_import_edges(
    graph: VerifiedIndexGraph,
    rel: str,
    imports: list[dict[str, Any]],
    nodes: set[str],
) -> None:
    """与 ``DependencyGraph._build`` 相同的建边规则（含 #1557 子模块边）。"""
    for imp in imports:
        module = imp.get("module_name", "")
        is_relative = bool(imp.get("is_relative", False))
        resolver = _IMPORT_RESOLVERS.get(imp.get("language", ""))
        resolved = resolver(module, rel, nodes, is_relative) if resolver else None
        if resolved:
            graph.add_edge(rel, resolved)
        if imp.get("language") != "python":
            continue
        for target in python_submodule_import_targets(
            module, imp.get("names", ()) or (), rel, nodes, is_relative
        ):
            graph.add_edge(rel, target)
