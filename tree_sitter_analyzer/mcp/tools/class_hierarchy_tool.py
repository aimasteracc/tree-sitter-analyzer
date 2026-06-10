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
                    "description": (
                        "Query mode. Optional: when omitted, defaults to 'tree' "
                        "if class_name is given, else the global 'summary'."
                    ),
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
            # Wave 1b (audit structure-01, review nit): ``mode`` is resolved at
            # runtime (``_resolve_mode``) — defaulting to a class-scoped view
            # when ``class_name`` is supplied — so it is NOT required. Declaring
            # it required made strict MCP clients reject a valid
            # ``{class_name: X}`` call before dispatch.
            "required": [],
            "additionalProperties": False,
        }

    @staticmethod
    def _resolve_mode(arguments: dict[str, Any]) -> str:
        """Effective query mode.

        When the caller did not specify a mode, default to a CLASS-SCOPED view
        (``tree``) if a ``class_name`` was supplied, else the global
        ``summary``. Wave 1b (audit structure-01): a bare ``class_tree`` carrying
        a class identifier must NOT fall through to the global ``summary`` — that
        mode ignores ``class_name`` and returns a confident project-wide result
        for a class that may not even exist. ``tree`` instead returns
        ``NOT_FOUND`` for an unknown class.
        """
        mode = arguments.get("mode")
        if mode:
            return str(mode)
        return "tree" if arguments.get("class_name") else "summary"

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = self._resolve_mode(arguments)
        if mode in ("subclasses", "superclasses", "tree", "impact"):
            if not arguments.get("class_name"):
                raise ValueError(f"class_name is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = self._resolve_mode(arguments)
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
                # Wave 1b (audit structure-01): NOT_FOUND means the class is
                # unknown — an existing class with zero subclasses is a valid
                # INFO result, not a missing one.
                "verdict": (
                    "INFO" if result or hierarchy.has_class(class_name) else "NOT_FOUND"
                ),
            }
        elif mode == "superclasses":
            result = hierarchy.superclasses_of(class_name)
            response = {
                "success": True,
                "mode": "superclasses",
                "class_name": class_name,
                "superclass_count": len(result),
                "superclasses": result,
                # Wave 1b: same existence-vs-emptiness distinction — a root
                # class with no parents exists and is INFO, not NOT_FOUND.
                "verdict": (
                    "INFO" if result or hierarchy.has_class(class_name) else "NOT_FOUND"
                ),
            }
        elif mode == "tree":
            result = hierarchy.hierarchy_tree(class_name)
            all_subs = hierarchy.subclasses_of(class_name, max_depth=max_depth)
            response = {
                "success": True,
                "mode": "tree",
                "class_name": class_name,
                "subclass_count": len(all_subs),
                "tree": result,
                # Wave 1b (audit structure-01): verdict reflects whether the
                # class EXISTS, not whether it has subclasses — a real leaf
                # class (e.g. a concrete final class) must not read as
                # NOT_FOUND just because nothing inherits from it. ``tree`` is
                # the default mode for a named class, so this is the common path.
                "verdict": "INFO" if hierarchy.has_class(class_name) else "NOT_FOUND",
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
