"""MCP Tool for linting code."""
import subprocess
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class LinterTool(BaseTool):
    """Run ruff linter on code."""

    def get_name(self) -> str:
        return "run_linter"

    def get_description(self) -> str:
        return "Run ruff linter on Python code to check for issues."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory to lint"},
                "fix": {"type": "boolean", "description": "Auto-fix issues", "default": False},
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            path = Path(arguments["path"])
            if not path.exists():
                return {"success": False, "error": f"Path not found: {path}"}

            cmd = ["ruff", "check", str(path)]
            if arguments.get("fix"):
                cmd.append("--fix")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            return {
                "success": result.returncode == 0,
                "issues": result.stdout if result.stdout else "No issues found",
                "errors": result.stderr if result.stderr else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
