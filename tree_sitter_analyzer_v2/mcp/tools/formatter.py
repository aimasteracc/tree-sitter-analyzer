"""MCP Tool for formatting code."""
import subprocess
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class FormatterTool(BaseTool):
    """Format code using ruff."""

    def get_name(self) -> str:
        return "format_code"

    def get_description(self) -> str:
        return "Format Python code using ruff formatter."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory to format"},
                "check_only": {"type": "boolean", "description": "Only check, don't modify", "default": False},
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            path = Path(arguments["path"])
            if not path.exists():
                return {"success": False, "error": f"Path not found: {path}"}

            cmd = ["ruff", "format", str(path)]
            if arguments.get("check_only"):
                cmd.append("--check")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "formatted": not arguments.get("check_only"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
