#!/usr/bin/env python3
"""Project-local agent skills inventory MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...services import build_agent_skills_inventory  # ARCH-A1: was ...cli.agent_skills
from .base_tool import BaseMCPTool

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "skills_root": {
            "type": "string",
            "description": (
                "Optional project-relative skills directory (default: .agents/skills)"
            ),
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


class AgentSkillsTool(BaseMCPTool):
    """MCP tool that lists project-local agent skills and usability gaps."""

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "list_agent_skills",
            "description": (
                "List project-local .agents/skills metadata, trigger text, read order, "
                "support files, scripts, context needs, side effects, and gaps. "
                "Use before selecting a project-local skill."
            ),
            "inputSchema": TOOL_SCHEMA,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate output format and optional skills root."""
        output_format = arguments.get("output_format", "toon")
        if output_format not in {"json", "toon"}:
            raise ValueError("output_format must be 'json' or 'toon'")

        skills_root = arguments.get("skills_root")
        if skills_root is not None and not isinstance(skills_root, str):
            raise ValueError("skills_root must be a string")
        if isinstance(skills_root, str) and not skills_root.strip():
            raise ValueError("skills_root must be a non-empty string")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Build a project-local agent skill inventory."""
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        skills_root = arguments.get("skills_root")
        self._validate_skills_root(skills_root)
        result = build_agent_skills_inventory(
            project_root=str(self.project_root),
            skills_root=skills_root,
        )
        if arguments.get("output_format", "toon") == "toon":
            return _build_toon_response(result)
        # Strip ``toon_content`` from the JSON path — it duplicates the
        # structured fields (~1.8 KB per call) and confuses agents that
        # expect a clean JSON envelope.
        result.pop("toon_content", None)
        return result

    def _validate_skills_root(self, skills_root: str | None) -> None:
        """Keep custom skills roots inside the configured project boundary."""
        if not skills_root:
            return
        project_root = Path(str(self.project_root)).resolve()
        candidate = Path(skills_root).expanduser()
        resolved = candidate if candidate.is_absolute() else project_root / candidate
        is_valid, error = self.security_validator.validate_directory_path(
            str(resolved),
            must_exist=False,
        )
        if not is_valid:
            raise ValueError(f"Invalid skills_root: {error}")


def _build_toon_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact MCP response when callers request TOON output."""
    return {
        "success": result["success"],
        "format": "toon",
        "inventory": result["inventory"],
        "skills_root": result["skills_root"],
        "skills_root_exists": result["skills_root_exists"],
        "skill_count": result["skill_count"],
        "agent_summary": result["agent_summary"],
        "gaps": result["gaps"],
        "validation": result["validation"],
        "toon_content": result["toon_content"],
    }
