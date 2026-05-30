#!/usr/bin/env python3
"""Shared execution helpers for CodeGraph caller/callee relation tools."""

from __future__ import annotations

import re
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph

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
    "stale_cache: most edges have callee_resolution='unknown'. "
    "Run `uv run tree-sitter-analyzer --ast-cache --ast-cache-mode force` "
    "or rebuild with `--mode resolve` to populate Synapse resolution columns."
)


def _is_stale_resolution(entries: list[dict[str, Any]]) -> bool:
    """Return True when a relation response mostly has unknown callee resolution."""
    if not entries:
        return False
    unknown = sum(1 for e in entries if e.get("callee_resolution") == "unknown")
    threshold = max(1, int(_STALE_CACHE_UNKNOWN_RATIO * len(entries)))
    return unknown >= threshold


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

    def _init_relation_state(self) -> None:
        self._call_graph = None
        self._data_source = "unknown"

    def _reset_relation_state(self) -> None:
        self._call_graph = None
        self._data_source = "unknown"

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

    def _get_call_graph(self) -> CallGraph:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
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
