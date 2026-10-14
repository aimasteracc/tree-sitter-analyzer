#!/usr/bin/env python3
"""Shared execution helpers for CodeGraph caller/callee relation tools."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph
from ...graph.edge_store import _RESOLVED_CALLEE_RESOLUTIONS
from .parse_fallback_budget import index_missing_response
from .relation_freshness import index_identity

_STDLIB_TOP_LEVELS = frozenset(
    {
        "abc",
        "argparse",
        "ast",
        "asyncio",
        "base64",
        "bisect",
        "calendar",
        "collections",
        "configparser",
        "contextlib",
        "copy",
        "csv",
        "datetime",
        "decimal",
        "difflib",
        "email",
        "enum",
        "fileinput",
        "fnmatch",
        "fractions",
        "functools",
        "glob",
        "gzip",
        "hashlib",
        "heapq",
        "html",
        "http",
        "importlib",
        "inspect",
        "io",
        "itertools",
        "json",
        "logging",
        "math",
        "multiprocessing",
        "operator",
        "os",
        "pathlib",
        "pickle",
        "platform",
        "pprint",
        "queue",
        "re",
        "secrets",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "statistics",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tarfile",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "traceback",
        "typing",
        "unittest",
        "urllib",
        "uuid",
        "warnings",
        "weakref",
        "xml",
        "zipfile",
        "zlib",
    }
)

_STALE_CACHE_UNKNOWN_RATIO = 0.8

_STALE_CACHE_WARNING = (
    "stale_cache: this index holds call edges but none was ever resolved "
    "(callee_resolution='unknown' everywhere; built before Synapse resolution "
    "or the resolution pass never ran). "
    "Run `uv run tree-sitter-analyzer --ast-cache --ast-cache-mode index "
    "--ast-cache-force` to rebuild the index and populate Synapse "
    "resolution columns."
)

# 已解析标记集合与 EdgeStore 完整性计数共用同一来源，避免两处判定漂移。
_RESOLVED_MARKER_SQL = ", ".join(
    f"'{marker}'" for marker in sorted(_RESOLVED_CALLEE_RESOLUTIONS)
)
_RESOLVED_EDGE_PROBE = (
    "SELECT 1 FROM edges WHERE kind = 'calls' AND ("  # nosec B608
    f"callee_resolution IN ({_RESOLVED_MARKER_SQL}) "
    "OR callee_resolved_file <> '' "
    f"OR json_extract(metadata, '$.callee_resolution') IN ({_RESOLVED_MARKER_SQL})"
    ") LIMIT 1"
)


def index_never_resolved(cache: Any) -> bool:
    """#1580：索引有调用边，但没有任何一条边带已解析标记。

    这才是 ``stale_cache`` 警告要发现的情形——缓存建于解析列出现之前，或
    解析阶段从未运行。解析过的新索引里本就存在合理的未解析边（接收者未知的
    方法调用等），不能据此建议强制重建。读不到证据时返回 False：警告只在
    有正面证据时出现，单次答复的完整性由 RFC-0028 的 completeness 字段声明。
    """
    if cache is None:
        return False
    try:
        conn = cache.get_conn()
        if (
            conn.execute("SELECT 1 FROM edges WHERE kind = 'calls' LIMIT 1").fetchone()
            is None
        ):
            return False
        return conn.execute(_RESOLVED_EDGE_PROBE).fetchone() is None
    except (sqlite3.Error, AttributeError, TypeError):
        return False


def _is_stale_resolution(entries: list[dict[str, Any]], cache: Any) -> bool:
    """答复多数条目未解析，且其所依据的索引从未做过解析时返回 True（#1580）。

    旧实现只看单次答复的条目占比，分母是答复而非索引，新建索引上同样触发。
    """
    if not entries:
        return False
    unknown = sum(1 for e in entries if e.get("callee_resolution") == "unknown")
    threshold = max(1, int(_STALE_CACHE_UNKNOWN_RATIO * len(entries)))
    return unknown >= threshold and index_never_resolved(cache)


def classify_callee_resolution(
    callee_name: str,
    callee_resolved_file: str,
    caller_file: str,
) -> tuple[str, str]:
    """Classify callee resolution type and determine resolved file."""
    if not callee_name:
        return "unknown", callee_resolved_file

    dot_parts = callee_name.rsplit(".", 1)
    base_name = dot_parts[0] if len(dot_parts) == 2 else callee_name

    if callee_resolved_file:
        if callee_resolved_file == caller_file:
            return "local", callee_resolved_file
        return "project", callee_resolved_file

    if base_name in _STDLIB_TOP_LEVELS:
        return "stdlib", ""
    if callee_name.startswith("self.") or callee_name.startswith("cls."):
        return "local", caller_file

    if "." in callee_name:
        top = callee_name.split(".")[0]
        if top in _STDLIB_TOP_LEVELS:
            return "stdlib", ""
        if re.match(r"^[a-z_]+$", top) and top not in ("os", "sys"):
            pass

    return "unknown", callee_resolved_file


class CodeGraphRelationToolMixin:
    """Shared cache and graph bootstrap for caller/callee compatibility tools."""

    project_root: str | None
    _call_graph: CallGraph | None
    _data_source: str
    _graph_index_identity: tuple[Any, ...] | None

    def _init_relation_state(self) -> None:
        self._call_graph = None
        self._data_source = "unknown"
        self._graph_index_identity = None

    def _reset_relation_state(self) -> None:
        self._call_graph = None
        self._data_source = "unknown"
        self._graph_index_identity = None

    def _try_get_cache(self) -> Any:
        try:
            from ...ast_cache import ASTCache

            if self.project_root is None:
                return None
            cache = ASTCache(self.project_root)
            if cache.has_call_edges():
                return cache
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                return cache
            cache.close()
        except Exception:  # nosec B110
            pass
        return None

    @staticmethod
    def _cache_call_graph_built(cache: Any) -> bool:
        try:
            return bool(cache.call_graph_built())
        except Exception:
            return False

    def _parse_fallback_refusal(
        self, cache: Any, tool_label: str, **subject: Any
    ) -> dict[str, Any] | None:
        """#1562：无索引且仓库超出现场解析预算时返回 INDEX_MISSING 答复。

        有缓存（哪怕没有调用边）时走 ``CachedCallGraph``，不会现场解析，
        因此返回 ``None``；只有 ``cache is None`` 才会触发整仓解析。
        """
        if cache is not None:
            return None
        return index_missing_response(self.project_root, tool_label, **subject)

    def _get_call_graph(self) -> CallGraph:
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")
        # dogfood 2026-10-14：内存调用图绑定索引身份，重建索引或 generation
        # 切换后立即失效；身份检查只做几条聚合 SQL，不遍历源码树。
        # 身份在构建前记录：构建期间若有写入，下一次调用最多多重建一次。
        identity = index_identity(self.project_root)
        if self._call_graph is None or identity != self._graph_index_identity:
            self._graph_index_identity = identity
            cache = self._try_get_cache()
            if cache is not None:
                self._call_graph = CachedCallGraph(self.project_root, cache=cache)
                self._data_source = "cache"
            else:
                self._call_graph = CallGraph(self.project_root)
                self._data_source = "parse"
        return self._call_graph

    def get_call_graph(self) -> CallGraph:
        """Public alias for _get_call_graph() — use this instead of accessing _call_graph."""
        return self._get_call_graph()

    @property
    def call_graph_initialized(self) -> bool:
        """True if the call graph has been lazily initialized (i.e. cached)."""
        return self._call_graph is not None

    @staticmethod
    def _fetch_activation_map(
        cache: Any,
    ) -> dict[tuple[str, int], dict[str, Any]]:
        """Build a (file_path, line) -> activation map from AST cache rows."""
        try:
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT s.file_path, s.line, a.mod_count_30d, a.last_modified_at "
                "FROM ast_symbol_activation a "
                "JOIN ast_symbol_rows s ON s.id = a.symbol_id"
            ).fetchall()
        except Exception:
            return {}
        out: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            file_path = row["file_path"] or ""
            line = int(row["line"] or 0)
            out[(file_path, line)] = {
                "mod_count_30d": int(row["mod_count_30d"] or 0),
                "last_modified_at": (
                    int(row["last_modified_at"])
                    if row["last_modified_at"] is not None
                    else None
                ),
            }
        return out

    @staticmethod
    def _activation_for(
        activation_map: dict[tuple[str, int], dict[str, Any]],
        file_path: str,
        line: int,
    ) -> dict[str, Any]:
        """Return the activation entry for a relation target, or zero-row defaults."""
        return activation_map.get(
            (file_path, line),
            {"mod_count_30d": 0, "last_modified_at": None},
        )
