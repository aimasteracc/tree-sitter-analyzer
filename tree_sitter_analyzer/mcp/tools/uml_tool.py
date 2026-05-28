#!/usr/bin/env python3
"""UML Export MCP Tool — Mermaid diagrams from project intelligence."""

from __future__ import annotations

from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from .base_tool import BaseMCPTool
from .codegraph_visualization_hub import CodeGraphVisualizationHub

logger = setup_logger(__name__)

_DEFAULT_MAX_EDGES = 200


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
                "max_edges": {
                    "type": "integer",
                    "default": _DEFAULT_MAX_EDGES,
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
        for key in ("max_edges", "max_depth", "max_paths", "package_depth"):
            value = arguments.get(key)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ValueError(f"{key} must be a positive integer")
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
                max_edges=arguments.get("max_edges", _DEFAULT_MAX_EDGES),
                include_external_bases=arguments.get("include_external_bases", True),
            )
        elif diagram_type == "package":
            diagram = exporter.package_diagram(
                max_edges=arguments.get("max_edges", _DEFAULT_MAX_EDGES),
                package_depth=arguments.get("package_depth", 2),
            )
        elif diagram_type == "component":
            diagram = exporter.component_diagram(
                max_edges=arguments.get("max_edges", _DEFAULT_MAX_EDGES),
            )
        else:
            diagram = exporter.sequence_diagram(
                source=arguments["source"],
                target=arguments["target"],
                max_depth=arguments.get("max_depth", 8),
                max_paths=arguments.get("max_paths", 3),
            )

        verdict = "INFO" if diagram.edges else "NOT_FOUND"
        response = build_response(verdict=verdict, **diagram.to_dict())
        return apply_toon_format_to_response(response, output_format)
