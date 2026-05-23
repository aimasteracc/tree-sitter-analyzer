#!/usr/bin/env python3
"""
Class Hierarchy MCP Tool — Cache-backed type inheritance analysis.

Modes:
  subclasses   — find all classes that inherit from a given class
  superclasses — find the full inheritance chain above a class
  tree         — full subtree rooted at a class
  impact       — risk analysis for modifying a base class
  all          — list all discovered class definitions
  summary      — hierarchy statistics

CodeGraph parity: equivalent to CodeGraph's type-hierarchy feature.
"""

from typing import Any

from ...ast_cache import ASTCache
from ...class_hierarchy import ClassHierarchy
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ClassHierarchyTool(BaseMCPTool):
    """MCP Tool for class inheritance hierarchy analysis (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._hierarchy: ClassHierarchy | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._hierarchy = None

    def _get_hierarchy(self) -> ClassHierarchy:
        if self._hierarchy is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            cache = ASTCache(self.project_root)
            self._hierarchy = ClassHierarchy(cache)
        return self._hierarchy

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_class_hierarchy",
            "description": (
                "Class inheritance hierarchy analysis (CodeGraph parity). "
                "Modes: subclasses (find descendants of a class), "
                "superclasses (find ancestors of a class), "
                "tree (full subtree rooted at a class), "
                "impact (risk analysis for modifying a base class), "
                "all (list all discovered classes), "
                "summary (hierarchy statistics). "
                "Requires ast_cache index to be built first. "
                "No other tool provides type hierarchy analysis."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "subclasses",
                        "superclasses",
                        "tree",
                        "impact",
                        "all",
                        "summary",
                    ],
                    "description": "Query mode",
                },
                "class_name": {
                    "type": "string",
                    "description": "Target class name (required for subclasses, superclasses, tree, impact)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max traversal depth for subclasses (default: 10)",
                    "default": 10,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "required": ["mode"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        if mode in ("subclasses", "superclasses", "tree", "impact"):
            if not arguments.get("class_name"):
                raise ValueError(f"class_name is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "summary")
        class_name = arguments.get("class_name", "")
        max_depth = arguments.get("max_depth", 10)
        output_format = arguments.get("output_format", "toon")

        hierarchy = self._get_hierarchy()
        hierarchy.build()

        result: Any
        if mode == "subclasses":
            result = hierarchy.subclasses_of(class_name, max_depth=max_depth)
            response: dict[str, Any] = {
                "success": True,
                "mode": "subclasses",
                "class_name": class_name,
                "subclass_count": len(result),
                "subclasses": result,
                "verdict": "INFO" if result else "NOT_FOUND",
            }
        elif mode == "superclasses":
            result = hierarchy.superclasses_of(class_name)
            response = {
                "success": True,
                "mode": "superclasses",
                "class_name": class_name,
                "superclass_count": len(result),
                "superclasses": result,
                "verdict": "INFO" if result else "NOT_FOUND",
            }
        elif mode == "tree":
            result = hierarchy.hierarchy_tree(class_name)
            response = {
                "success": True,
                "mode": "tree",
                "class_name": class_name,
                "tree": result,
                "verdict": "INFO",
            }
        elif mode == "impact":
            impact = hierarchy.hierarchy_impact(class_name)
            response = {
                "success": True,
                "mode": "impact",
                "verdict": (
                    "CAUTION"
                    if impact.risk_level in ("high", "critical")
                    else "REVIEW"
                    if impact.risk_level == "medium"
                    else "INFO"
                ),
                **impact.to_dict(),
            }
        elif mode == "all":
            classes = hierarchy.all_classes()
            response = {
                "success": True,
                "mode": "all",
                "class_count": len(classes),
                "classes": classes,
                "verdict": "INFO",
            }
        elif mode == "summary":
            response = {
                "success": True,
                "mode": "summary",
                "verdict": "INFO",
                **hierarchy.summary(),
            }
        else:
            response = {
                "success": False,
                "error": f"Unknown mode: {mode}",
                "verdict": "ERROR",
            }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)
