"""MCP Tool for running tests."""
import subprocess
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class TestRunnerTool(BaseTool):
    """Run pytest tests."""

    def get_name(self) -> str:
        return "run_tests"

    def get_description(self) -> str:
        return "Run pytest tests with coverage reporting."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Test file or directory"},
                "coverage": {"type": "boolean", "description": "Enable coverage", "default": True},
                "verbose": {"type": "boolean", "description": "Verbose output", "default": False},
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            path = Path(arguments["path"])
            if not path.exists():
                return {"success": False, "error": f"Path not found: {path}"}

            cmd = ["pytest", str(path)]
            if arguments.get("coverage", True):
                cmd.extend(["--cov", "--cov-report=term"])
            if arguments.get("verbose"):
                cmd.append("-v")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "passed": "passed" in result.stdout.lower(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
