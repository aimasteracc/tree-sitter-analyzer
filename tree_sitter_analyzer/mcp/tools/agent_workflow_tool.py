#!/usr/bin/env python3
"""SMART agent workflow pack MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...services import build_agent_workflow_pack  # ARCH-A1: was ...cli.agent_workflow
from .base_tool import BaseMCPTool, _canonicalize_verdict

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target_path": {
            "type": "string",
            "description": (
                "Optional project-relative target path for focused workflow commands"
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


class AgentWorkflowTool(BaseMCPTool):
    """MCP tool that returns a SMART workflow command pack for agents."""

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "get_agent_workflow",
            "description": (
                "Return the SMART agent workflow pack for project setup, file mapping, "
                "edit-risk analysis, focused retrieval, dependency tracing, and queue "
                "boundary verification. Use before opening a new autonomous queue item."
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
        """Validate output format and optional target path."""
        if arguments.get("output_format", "json") != "json":
            raise ValueError("output_format must be 'json'")
        target_path = arguments.get("target_path")
        if target_path is not None and not isinstance(target_path, str):
            raise ValueError("target_path must be a string")
        if isinstance(target_path, str) and not target_path.strip():
            raise ValueError("target_path must be a non-empty string")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Build a SMART agent workflow pack."""
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        target_path = arguments.get("target_path")
        self._validate_target_path(target_path)
        result = build_agent_workflow_pack(
            project_root=str(self.project_root),
            target_path=target_path,
        )
        _canonicalize_workflow_verdict(result)
        if not result.get("success", True):
            return result
        return _build_json_response(result)

    def _validate_target_path(self, target_path: str | None) -> None:
        """Keep optional workflow targets inside the configured project boundary."""
        if not target_path:
            return
        project_root = Path(str(self.project_root)).resolve()
        candidate = Path(target_path).expanduser()
        resolved = candidate if candidate.is_absolute() else project_root / candidate
        is_valid, error = self.security_validator.validate_file_path(str(resolved))
        if not is_valid:
            raise ValueError(f"Invalid target_path: {error}")


def _canonicalize_workflow_verdict(result: dict[str, Any]) -> None:
    """Rewrite both verdict surfaces in-place to the canonical vocabulary."""
    agent_summary = result.get("agent_summary")
    if isinstance(agent_summary, dict):
        existing = agent_summary.get("verdict")
        if isinstance(existing, str) or existing is None:
            agent_summary["verdict"] = _canonicalize_verdict(existing)
    top_value = result.get("verdict")
    if isinstance(top_value, str) or top_value is None:
        result["verdict"] = _canonicalize_verdict(top_value)


def _build_json_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return the structured JSON workflow envelope."""
    response: dict[str, Any] = {
        "success": result["success"],
        "format": "json",
        "workflow": result["workflow"],
        "workflow_mode": result["workflow_mode"],
        "project_root": result["project_root"],
        "target_path": result["target_path"],
        "agent_summary": result["agent_summary"],
        "current_phase": result["current_phase"],
        "phase_order": result["phase_order"],
        "current_step": result["current_step"],
        "recommended_commands": result["recommended_commands"],
        "routing": result["routing"],
        "queue_boundary_commands": result["queue_boundary_commands"],
        "sprint_contract": result["sprint_contract"],
    }
    summary_line = result.get("summary_line")
    if isinstance(summary_line, str) and summary_line:
        response["summary_line"] = summary_line
    agent_summary = result.get("agent_summary")
    if isinstance(agent_summary, dict) and isinstance(
        agent_summary.get("verdict"), str
    ):
        response["verdict"] = agent_summary["verdict"]
    return response
