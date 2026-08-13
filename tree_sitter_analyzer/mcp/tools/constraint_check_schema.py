"""Input schema for the architectural constraint MCP tool."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path_filter": {
            "type": "string",
            "default": "",
            "description": (
                "Optional fnmatch-style glob applied to caller_file. "
                "Use to narrow results to a queue scope, e.g. 'mcp/**'."
            ),
        },
        "severity_min": {
            "type": "string",
            "enum": ["error", "warn", "info"],
            "default": "warn",
            "description": (
                "Minimum severity to include in the response. "
                "Default 'warn' suppresses info-level rules from agent output."
            ),
        },
        "persist": {
            "type": "boolean",
            "default": True,
            "description": (
                "Write evaluated violations through to the cache. Set false for "
                "RFC-0022 read-only evaluation; no database or file is created."
            ),
        },
        "diff_snapshot_id": {
            "type": "string",
            "description": "RFC-0022 frozen diff snapshot to evaluate against.",
        },
        "scope_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Primitive-issued assessed_scope_paths. With diff_snapshot_id the "
                "list must exactly match the frozen snapshot scope."
            ),
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "json",
            "description": "Response format.",
        },
    },
    "additionalProperties": False,
}
