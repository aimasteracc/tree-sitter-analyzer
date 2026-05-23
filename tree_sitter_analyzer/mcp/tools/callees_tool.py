#!/usr/bin/env python3
"""
CodeGraph Callees MCP Tool

Dedicated tool for finding all functions called by a given function.
CodeGraph parity: equivalent to codegraph_callees.

Simpler and more discoverable than the monolithic codegraph_call_graph tool.
"""

import os
import re
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

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


def classify_callee_resolution(
    callee_name: str,
    callee_resolved_file: str,
    caller_file: str,
) -> tuple[str, str]:
    """Classify callee resolution type and determine resolved file.

    Returns (callee_resolution, callee_resolved_file):
    - callee_resolution: one of 'local', 'project', 'stdlib', 'third_party', 'dynamic', 'unknown'
    - callee_resolved_file: the file where the callee is defined (may be empty)
    """
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


class CodeGraphCalleesTool(BaseMCPTool):
    """MCP Tool for finding callees of a function (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        self._data_source: str = "unknown"
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None
        self._data_source = "unknown"

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

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_callees",
            "description": (
                "Find all functions called by the given function (CodeGraph parity). "
                "Returns callee function name, file, line, and language. "
                "No other built-in tool provides forward call lookup."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "function_name": {
                    "type": "string",
                    "description": "Source function name to find callees for",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
                "include_activation": {
                    "type": "boolean",
                    "description": (
                        "When true, embed per-callee git modification "
                        "frequency under the 'activation' key. Off by "
                        "default to preserve token budget."
                    ),
                    "default": False,
                },
            },
            "required": ["function_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "function_name" not in arguments:
            raise ValueError("function_name is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        func_name = arguments["function_name"]
        file_path = arguments.get("file_path")
        output_format = arguments.get("output_format", "toon")
        include_activation = bool(arguments.get("include_activation", False))

        cache = self._try_get_cache()
        if cache is not None and cache.has_call_edges():
            callees = self._sql_native_callees(
                cache, func_name, file_path, include_activation
            )
            data_source = "sql"
        else:
            graph = self._get_call_graph()
            callees = graph.callees_of(func_name, file_path)
            data_source = self._data_source
            if include_activation:
                self._enrich_graph_callees_with_activation(callees)
            self._enrich_callees_with_resolution(callees)

        result: dict[str, Any] = {
            "success": True,
            "verdict": "INFO" if callees else "NOT_FOUND",
            "data_source": data_source,
            "function": func_name,
            "callee_count": len(callees),
            "callees": callees,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _sql_native_callees(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        include_activation: bool = False,
    ) -> list[dict[str, Any]]:
        """Use SQL-native callees query — O(k) instead of full graph build.

        When ``include_activation`` is True, each entry gets an
        ``activation`` sub-dict carrying ``mod_count_30d`` and
        ``last_modified_at`` read from ``ast_symbol_activation``. The
        lookup is keyed by ``(callee_file, callee_line)`` and falls back
        to zero counts when no row is found.
        """
        raw = cache.query_callees(func_name, caller_file=file_path)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        activation_map: dict[tuple[str, int], dict[str, Any]] = {}
        if include_activation:
            activation_map = self._fetch_activation_map(cache)
        for edge in raw:
            key = f"{edge['callee_name']}:{edge.get('callee_file', '')}"
            if key in seen:
                continue
            seen.add(key)
            callee_resolved = edge.get("callee_resolved_file", "")
            callee_file_val = edge.get("callee_file", callee_resolved)
            caller_file_val = edge.get("caller_file", "")
            resolution, resolved_file = classify_callee_resolution(
                edge["callee_name"], callee_resolved, caller_file_val
            )
            entry: dict[str, Any] = {
                "name": edge["callee_name"],
                "file": resolved_file or callee_file_val,
                "line": edge["callee_line"],
                "language": "",
                "callee_resolution": resolution,
                "callee_resolved_file": resolved_file,
            }
            row_data = cache.lookup(
                os.path.join(cache.project_root, resolved_file or callee_file_val)
            )
            if row_data:
                entry["language"] = row_data.get("language", "")
            if include_activation:
                entry["activation"] = self._activation_for(
                    activation_map,
                    resolved_file or callee_file_val,
                    edge["callee_line"],
                )
            results.append(entry)
        if not raw:
            results = self._resolve_via_enhanced(
                cache,
                func_name,
                file_path,
                activation_map if include_activation else {},
            )
        return results

    @staticmethod
    def _fetch_activation_map(
        cache: Any,
    ) -> dict[tuple[str, int], dict[str, Any]]:
        """Build a (file_path, line) -> {mod_count_30d, last_modified_at} map.

        We JOIN with ``ast_symbol_rows`` to recover the source line for
        each activation row — the activation table itself only carries
        ``symbol_id`` and ``file_path``. Returns an empty map when the
        cache is legacy / missing the table.
        """
        try:
            conn = cache._get_conn()
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
        """Return the activation entry for a callee, or zero-row defaults."""
        return activation_map.get(
            (file_path, line),
            {"mod_count_30d": 0, "last_modified_at": None},
        )

    def _enrich_callees_with_resolution(self, callees: list[dict[str, Any]]) -> None:
        """Add callee_resolution and callee_resolved_file to graph-fallback results."""
        for entry in callees:
            callee_file = entry.get("file", "")
            callee_name = entry.get("name", "")
            if "callee_resolution" not in entry or "callee_resolved_file" not in entry:
                resolution, resolved_file = classify_callee_resolution(
                    callee_name, callee_file, callee_file
                )
                entry.setdefault("callee_resolution", resolution)
                entry.setdefault("callee_resolved_file", resolved_file)

    def _resolve_via_enhanced(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        activation_map: dict[tuple[str, int], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fallback to query_callees_enhanced for cross-file resolution."""
        try:
            enhanced = cache.query_callees_enhanced(func_name, caller_file=file_path)
        except Exception:
            return []
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for edge in enhanced:
            callee_resolved = edge.get("callee_resolved_file", "")
            key = f"{edge['callee_name']}:{callee_resolved}"
            if key in seen:
                continue
            seen.add(key)
            caller_file_val = edge.get("caller_file", "")
            resolution, resolved_file = classify_callee_resolution(
                edge["callee_name"], callee_resolved, caller_file_val
            )
            entry: dict[str, Any] = {
                "name": edge["callee_name"],
                "file": resolved_file or edge.get("callee_file", ""),
                "line": edge["callee_line"],
                "language": "",
                "callee_resolution": resolution,
                "callee_resolved_file": resolved_file,
            }
            if activation_map:
                entry["activation"] = self._activation_for(
                    activation_map,
                    resolved_file or edge.get("callee_file", ""),
                    edge["callee_line"],
                )
            results.append(entry)
        return results

    def _enrich_graph_callees_with_activation(
        self, callees: list[dict[str, Any]]
    ) -> None:
        """Decorate graph-walk results with activation when SQL path missed.

        Used when the cache is unavailable / has no call edges so the tool
        falls back to a fresh CallGraph parse. We still try to attach
        activation if the cache table happens to exist.
        """
        try:
            from ...ast_cache import ASTCache
        except Exception:
            return
        if not self.project_root:
            return
        try:
            cache = ASTCache(self.project_root)
        except Exception:
            return
        try:
            activation_map = self._fetch_activation_map(cache)
            for entry in callees:
                entry.setdefault(
                    "activation",
                    self._activation_for(
                        activation_map,
                        entry.get("file", ""),
                        int(entry.get("line", 0) or 0),
                    ),
                )
        finally:
            try:
                cache.close()
            except Exception:
                pass
