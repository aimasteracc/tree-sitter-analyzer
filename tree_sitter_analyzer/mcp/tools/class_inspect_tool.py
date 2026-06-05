#!/usr/bin/env python3
"""
Class Inspect MCP Tool — method inventory for a single class.

Reports all methods defined in a class (not inherited), and for each
method indicates whether it is an override of a parent-class method.
"""

from __future__ import annotations

import json
from typing import Any

from ...ast_cache import ASTCache
from ...class_hierarchy import ClassHierarchy
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ClassInspectTool(BaseMCPTool):
    """Inspect the methods defined in a single class, with override detection."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_class_inspect",
            "description": (
                "List all methods defined directly on a class (not inherited). "
                "For each method, reports whether it overrides a parent-class method "
                "and which parent introduced it. "
                "Requires ast_cache index to be built first."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "class_name": {
                    "type": "string",
                    "description": "Name of the class to inspect",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "required": ["class_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("class_name"):
            raise ValueError("class_name is required")
        return True

    def _get_cache(self) -> ASTCache:
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")
        return ASTCache(self.project_root)

    def _collect_methods(
        self, cache: ASTCache, class_name: str
    ) -> list[dict[str, Any]]:
        """Return all methods whose enclosing class matches class_name."""
        try:
            conn = cache.get_conn()
            rows = conn.execute(
                "SELECT file_path, symbols_json FROM ast_index"
            ).fetchall()
        except Exception:
            return []

        methods: list[dict[str, Any]] = []
        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                if sym.get("class") != class_name:
                    continue
                methods.append(
                    {
                        "name": sym.get("name", ""),
                        "line": sym.get("line", 0),
                        "end_line": sym.get("end_line", 0),
                        "file": row["file_path"],
                    }
                )
        methods.sort(key=lambda m: (m["file"], m["line"]))
        return methods

    def _parent_method_names(
        self, hierarchy: ClassHierarchy, class_name: str, cache: ASTCache
    ) -> set[str]:
        """Collect method names defined in any ancestor of class_name."""
        ancestors = hierarchy.superclasses_of(class_name)
        ancestor_names = {a["name"] for a in ancestors}
        if not ancestor_names:
            return set()

        try:
            conn = cache.get_conn()
            rows = conn.execute("SELECT symbols_json FROM ast_index").fetchall()
        except Exception:
            return set()

        parent_methods: set[str] = set()
        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                if sym.get("class") in ancestor_names:
                    parent_methods.add(sym["name"])
        return parent_methods

    def _find_override_source(
        self,
        hierarchy: ClassHierarchy,
        class_name: str,
        method_name: str,
        cache: ASTCache,
    ) -> str | None:
        """Return the name of the ancestor class that first defines method_name."""
        ancestors = hierarchy.superclasses_of(class_name)
        # superclasses_of returns nearest first (BFS)
        ancestor_names = [a["name"] for a in ancestors]
        if not ancestor_names:
            return None

        try:
            conn = cache.get_conn()
            rows = conn.execute("SELECT symbols_json FROM ast_index").fetchall()
        except Exception:
            return None

        # Build map: ancestor_class -> set of method names
        ancestor_methods: dict[str, set[str]] = {}
        for row in rows:
            try:
                symbols = json.loads(row["symbols_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for sym in symbols.get("symbols", []):
                if sym.get("kind") not in ("function", "method"):
                    continue
                cls = sym.get("class")
                if cls in ancestor_names:
                    ancestor_methods.setdefault(cls, set()).add(sym["name"])

        for ancestor in ancestor_names:
            if method_name in ancestor_methods.get(ancestor, set()):
                return str(ancestor)
        return None

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        class_name: str = arguments["class_name"]
        output_format: str = arguments.get("output_format", "toon")

        cache = self._get_cache()
        hierarchy = ClassHierarchy(cache)
        hierarchy.build()

        # Check the class is known
        if class_name not in hierarchy._classes:  # noqa: SLF001
            response: dict[str, Any] = {
                "success": True,
                "verdict": "NOT_FOUND",
                "class_name": class_name,
                "message": f"Class '{class_name}' not found in AST index.",
                "methods": [],
                "method_count": 0,
            }
            from ..utils.format_helper import apply_toon_format_to_response

            return apply_toon_format_to_response(response, output_format)

        parent_method_names = self._parent_method_names(hierarchy, class_name, cache)
        raw_methods = self._collect_methods(cache, class_name)

        methods: list[dict[str, Any]] = []
        for m in raw_methods:
            is_override = m["name"] in parent_method_names
            entry: dict[str, Any] = {
                "name": m["name"],
                "line": m["line"],
                "end_line": m["end_line"],
                "file": m["file"],
                "is_override": is_override,
            }
            if is_override:
                src = self._find_override_source(
                    hierarchy, class_name, m["name"], cache
                )
                if src:
                    entry["overrides_from"] = src
            methods.append(entry)

        response = {
            "success": True,
            "verdict": "INFO",
            "class": class_name,
            "method_count": len(methods),
            "methods": methods,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)
