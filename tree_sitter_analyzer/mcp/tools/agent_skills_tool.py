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
            "enum": ["json"],
            "description": "Output format: JSON",
            "default": "json",
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
                "Enumerate project-local skills stored under ``.agents/skills/`` "
                "(or wherever ``skills_root`` points). Each entry includes the "
                "skill's trigger text, recommended read order, supporting "
                "files / scripts / context-pack requirements, any declared "
                "side effects, and gap flags (missing scripts, unresolved "
                "references). Use this BEFORE invoking a project skill so "
                "the agent knows what state the skill expects.\n\n"
                "WHEN TO USE:\n"
                "- Before invoking any project skill — preload context + "
                "side-effect awareness\n"
                "- To discover which skills are available in a new repo\n"
                "- To detect skills with missing dependencies (gap flags)\n"
                "- To pick the skill whose trigger text matches the user "
                "intent\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- To inspect MCP tools themselves — they self-describe via "
                "their own ``description`` fields\n"
                "- To run a skill — this tool only enumerates, it does not "
                "execute anything\n"
                "- For built-in Claude Code skills — those are surfaced by "
                "the Skill tool, not via this MCP endpoint"
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
        """Validate output format and optional skills root."""
        output_format = arguments.get("output_format", "json")
        if output_format != "json":
            raise ValueError("output_format must be 'json'")

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
        return _build_json_response(result)

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


def _build_json_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return the structured JSON MCP response."""
    response: dict[str, Any] = {
        "success": result["success"],
        "format": "json",
        "inventory": result["inventory"],
        "skills_root": result["skills_root"],
        "skills_root_exists": result["skills_root_exists"],
        "skill_count": result["skill_count"],
        "skills": result["skills"],
        "agent_summary": result["agent_summary"],
        "gaps": result["gaps"],
        "validation": result["validation"],
    }
    summary_line = result.get("summary_line")
    if isinstance(summary_line, str) and summary_line:
        response["summary_line"] = summary_line
    verdict = result.get("verdict")
    if isinstance(verdict, str) and verdict:
        response["verdict"] = verdict
    return response
