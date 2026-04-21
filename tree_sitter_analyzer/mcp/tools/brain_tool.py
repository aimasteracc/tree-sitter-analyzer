"""Brain Tool — one-call complete project awareness.

Exposes the ProjectBrain as an MCP tool. After warm-up, delivers
instant context for any file — no further tool calls needed.
"""
from __future__ import annotations

from typing import Any

from ...analysis.project_brain import ProjectBrain
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# Singleton brain — warmed once, reused across calls.
_brain: ProjectBrain | None = None


def _get_brain(project_root: str | None) -> ProjectBrain:
    global _brain
    if _brain is None or (
        project_root and _brain.project_root != project_root
    ):
        root = project_root or "."
        _brain = ProjectBrain(project_root=root)
        _brain.warm_up()
    return _brain


class BrainTool(BaseMCPTool):
    """One-call complete project context — no exploration needed."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "brain",
            "description": (
                "Complete project awareness in one call. Returns full "
                "context for a file: health, findings, hotspots, related "
                "files, and project overview. No further tool calls needed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "context",
                            "summary",
                            "hotspots",
                            "impact",
                            "warm_up",
                        ],
                        "description": (
                            "context: full file context. "
                            "summary: project overview. "
                            "hotspots: compound hotspots. "
                            "impact: what happens if I change this file. "
                            "warm_up: rebuild the brain model."
                        ),
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Target file (for context/impact)",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (for impact)",
                    },
                    "min_analyzers": {
                        "type": "integer",
                        "description": "Min analyzers for hotspot (default 2)",
                        "default": 2,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "default": "toon",
                    },
                },
                "required": ["action"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        fmt = arguments.get("format", "toon")
        action = arguments.get("action", "summary")

        brain = _get_brain(self.project_root)

        if action == "warm_up":
            brain.warm_up()
            data = brain.get_summary()
            data["status"] = "re-warmed"

        elif action == "summary":
            data = brain.get_summary()

        elif action == "hotspots":
            min_a = arguments.get("min_analyzers", 2)
            data = {
                "total": len(brain.get_hotspots(min_a)),
                "hotspots": brain.get_hotspots(min_a)[:50],
            }

        elif action == "context":
            fp = arguments.get("file_path")
            if not fp:
                raise ValueError("file_path required for context")
            resolved = self.resolve_and_validate_file_path(fp)
            data = brain.get_context_for_file(resolved)

        elif action == "impact":
            fp = arguments.get("file_path")
            if not fp:
                raise ValueError("file_path required for impact")
            resolved = self.resolve_and_validate_file_path(fp)
            line = arguments.get("line")
            data = brain.what_happens_if_i_change(resolved, line=line)

        else:
            raise ValueError(f"Unknown action: {action}")

        if fmt == "toon":
            return {"content": ToonEncoder().encode(data)}
        return data
