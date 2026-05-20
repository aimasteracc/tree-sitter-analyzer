#!/usr/bin/env python3
"""Parser-readiness advisor MCP tool."""

from __future__ import annotations

from typing import Any

from ...services import (
    build_parser_readiness_advice,  # ARCH-A1: was ...cli.parser_readiness
)
from .base_tool import BaseMCPTool

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "language": {
            "type": "string",
            "description": "Optional language to inspect, such as swift or python",
        },
        "include_supported": {
            "type": "boolean",
            "description": "Include implemented languages, not only roadmap candidates",
            "default": False,
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "description": "Output format: 'toon' (default, token-efficient) or 'json'",
            "default": "toon",
        },
    },
    "additionalProperties": False,
}


class ParserReadinessTool(BaseMCPTool):
    """MCP tool that ranks language parser/plugin readiness."""

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "advise_parser_readiness",
            "description": (
                "Advise which language parser/plugin work is ready next. Uses local "
                "pyproject parser dependencies, plugin entry points, loader mappings, "
                "tests, and wiki-inspired parser signals such as ABI, grammar.json, "
                "external scanner, and maintenance checks."
            ),
            "inputSchema": TOOL_SCHEMA,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate optional language, include flag, and output format."""
        output_format = arguments.get("output_format", "toon")
        if output_format not in {"json", "toon"}:
            raise ValueError("output_format must be 'json' or 'toon'")

        language = arguments.get("language")
        if language is not None and not isinstance(language, str):
            raise ValueError("language must be a string")
        if isinstance(language, str) and not language.strip():
            raise ValueError("language must be a non-empty string")

        include_supported = arguments.get("include_supported", False)
        if not isinstance(include_supported, bool):
            raise ValueError("include_supported must be a boolean")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Build parser readiness advice from local project metadata."""
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        result = build_parser_readiness_advice(
            project_root=str(self.project_root),
            language=arguments.get("language"),
            include_supported=arguments.get("include_supported", False),
        )
        if arguments.get("output_format", "toon") == "toon":
            return _build_toon_response(result)
        return result


def _build_toon_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact MCP response when callers request TOON output."""
    return {
        "success": result["success"],
        "format": "toon",
        "advisor": result["advisor"],
        "project_root": result["project_root"],
        "requested_language": result["requested_language"],
        "agent_summary": result["agent_summary"],
        "recommendations": result["recommendations"],
        "toon_content": result["toon_content"],
    }
