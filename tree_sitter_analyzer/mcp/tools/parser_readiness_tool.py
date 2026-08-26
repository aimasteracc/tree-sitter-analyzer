#!/usr/bin/env python3
"""Parser-readiness advisor MCP tool."""

from __future__ import annotations

import re
from typing import Any

from ...services import (
    build_parser_readiness_advice,  # ARCH-A1: was ...cli.parser_readiness
)
from .base_tool import BaseMCPTool

# Strict allowlist pattern: lowercase letter start, then alphanumeric/underscore/hyphen,
# max 32 chars total.  Rejects path traversal, shell metacharacters, and invented names.
_LANG_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

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
            "enum": ["json"],
            "description": "Output format: JSON",
            "default": "json",
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
                "external scanner, and maintenance checks. "
                "Each language record exposes parser_package_version (installed "
                "distribution version, always empty-string when not installed) and "
                "parser_required_spec (raw pyproject requirement string, always "
                "populated when the dependency is declared)."
            ),
            "inputSchema": TOOL_SCHEMA,
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate optional language, include flag, and output format."""
        output_format = arguments.get("output_format", "json")
        if output_format != "json":
            raise ValueError("output_format must be 'json'")

        language = arguments.get("language")
        if language is not None and not isinstance(language, str):
            raise ValueError("language must be a string")
        if isinstance(language, str) and not language.strip():
            raise ValueError("language must be a non-empty string")
        if (
            isinstance(language, str)
            and language.strip()
            and not _LANG_NAME_RE.match(language)
        ):
            raise ValueError(
                f"unknown language {language!r}; "
                "language names must match ^[a-z][a-z0-9_-]{{0,31}}$ — "
                "see implemented_languages list"
            )

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
        return _build_json_response(result)


def _build_json_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return the structured JSON MCP response."""
    response = {
        "success": result.get("success", False),
        "verdict": result.get("verdict", "INFO"),
        "format": "json",
        "advisor": result.get("advisor", "parser readiness"),
        "project_root": result.get("project_root", ""),
        "requested_language": result.get("requested_language"),
        "readiness": result.get("readiness", []),
        "status_distribution": result.get("status_distribution", {}),
        "high_priority_languages": result.get("high_priority_languages", []),
        "implemented_languages": result.get("implemented_languages", []),
        "agent_summary": result.get("agent_summary", {}),
        "recommendations": result.get("recommendations", []),
    }
    # Mirror error fields for failure envelopes so callers can inspect
    # error type and message without parsing agent_summary.
    error_type = result.get("error_type")
    if error_type:
        response["error_type"] = error_type
    error = result.get("error")
    if error:
        response["error"] = error
    # G7: mirror summary_line so the JSON envelope also carries the
    # top-level one-liner (JSON path passes the full ``result`` dict
    # which already has it).
    summary_line = result.get("summary_line")
    if isinstance(summary_line, str) and summary_line:
        response["summary_line"] = summary_line
    # N4: mirror ``verdict`` to the top-level envelope so direct callers
    # see the same shape on JSON output as on JSON output. Source of
    # truth is the agent_summary surface, populated in
    # :func:`_build_agent_summary`.
    verdict = result.get("verdict")
    if isinstance(verdict, str) and verdict:
        response["verdict"] = verdict
    return response
