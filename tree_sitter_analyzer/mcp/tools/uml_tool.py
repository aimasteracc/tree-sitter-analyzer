#!/usr/bin/env python3
"""UML Export MCP Tool — Mermaid diagrams from project intelligence."""

from __future__ import annotations

from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from ._validators import _validate_positive_int
from .base_tool import BaseMCPTool
from .codegraph_visualization_hub import CodeGraphVisualizationHub

logger = setup_logger(__name__)

# Per-diagram edge defaults (RFC-0015): narrowed from the old 200 monolith
# to reduce whole-project output flood while still covering typical projects.
_DEFAULT_CLASS_MAX_EDGES = 80
_DEFAULT_PACKAGE_MAX_EDGES = 60
_DEFAULT_COMPONENT_MAX_EDGES = 40

# Keep the old name as an alias so existing call-sites that reference it by
# name (e.g. FakeExporter tests) continue to resolve; remove after Phase 2.
_DEFAULT_MAX_EDGES = _DEFAULT_CLASS_MAX_EDGES


class CodeGraphUMLTool(BaseMCPTool):
    """Export UML-style Mermaid diagrams from the CodeGraph cache."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_uml",
            "description": (
                "Export UML-oriented Mermaid diagrams from indexed project "
                "facts. Diagrams: class, package, component, sequence. "
                "Class uses inheritance edges; package/component use import "
                "dependencies; sequence uses call paths."
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
                "diagram": {
                    "type": "string",
                    "enum": ["class", "package", "component", "sequence"],
                    "default": "class",
                    "description": "UML diagram to render",
                },
                "source": {
                    "type": "string",
                    "description": "Source function for sequence diagrams",
                },
                "target": {
                    "type": "string",
                    "description": "Target function for sequence diagrams",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Limit class diagram to classes defined in this file "
                        "and their direct bases/dependents from the full project."
                    ),
                },
                "class_name": {
                    "type": "string",
                    "description": (
                        "Show the named class plus its direct superclasses and "
                        "immediate subclasses (neighbourhood subgraph, up to max_edges)."
                    ),
                },
                "include_tests": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Include test-corpus classes (under tests/, testdata/, fixtures/) "
                        "in whole-project diagrams. Default False."
                    ),
                },
                "max_edges": {
                    "type": "integer",
                    "default": _DEFAULT_CLASS_MAX_EDGES,
                    "description": "Maximum relationships to render",
                },
                "max_depth": {
                    "type": "integer",
                    "default": 8,
                    "description": "Maximum call-path depth for sequence diagrams",
                },
                "max_paths": {
                    "type": "integer",
                    "default": 3,
                    "description": "Maximum call paths to inspect for sequence diagrams",
                },
                "package_depth": {
                    "type": "integer",
                    "default": 2,
                    "description": "Path depth used to group files for package diagrams",
                },
                "include_external_bases": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include common external bases in class diagrams",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format: toon (default) or json",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        diagram = arguments.get("diagram", "class")
        if diagram not in {"class", "package", "component", "sequence"}:
            raise ValueError(f"Unsupported UML diagram: {diagram}")
        if diagram == "sequence" and (
            not arguments.get("source") or not arguments.get("target")
        ):
            raise ValueError("source and target are required for sequence diagrams")
        # P1-B: use shared validator that also handles float coercion and bool rejection
        for key in ("max_edges", "max_depth", "max_paths", "package_depth"):
            _validate_positive_int(arguments, key)
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if not self.project_root:
            return apply_toon_format_to_response(
                build_error(error="Project root not set."),
                arguments.get("output_format", "toon"),
            )

        output_format = arguments.get("output_format", "toon")
        diagram_type = arguments.get("diagram", "class")
        exporter = CodeGraphVisualizationHub(self.project_root).uml_exporter()
        if exporter is None:
            return apply_toon_format_to_response(
                build_error(error="Project root not set."),
                output_format,
            )

        if diagram_type == "class":
            diagram = exporter.class_diagram(
                max_edges=arguments.get("max_edges", _DEFAULT_CLASS_MAX_EDGES),
                include_external_bases=arguments.get("include_external_bases", True),
                file_path=arguments.get("file_path"),
                class_name=arguments.get("class_name"),
                include_tests=arguments.get("include_tests", False),
            )
        elif diagram_type == "package":
            diagram = exporter.package_diagram(
                max_edges=arguments.get("max_edges", _DEFAULT_PACKAGE_MAX_EDGES),
                package_depth=arguments.get("package_depth", 2),
            )
        elif diagram_type == "component":
            diagram = exporter.component_diagram(
                max_edges=arguments.get("max_edges", _DEFAULT_COMPONENT_MAX_EDGES),
            )
        else:
            diagram = exporter.sequence_diagram(
                source=arguments["source"],
                target=arguments["target"],
                max_depth=arguments.get("max_depth", 8),
                max_paths=arguments.get("max_paths", 3),
            )

        # P2-1: check if class_name is unknown (not in project)
        not_found = diagram.metadata.get("not_found", False)
        verdict = (
            "NOT_FOUND" if not_found else ("INFO" if diagram.edges else "NOT_FOUND")
        )
        response = build_response(verdict=verdict, **diagram.to_dict())
        return apply_toon_format_to_response(response, output_format)
