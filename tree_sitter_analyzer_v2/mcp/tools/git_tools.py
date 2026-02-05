"""MCP Tools for Git operations."""
import subprocess
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class GitStatusTool(BaseTool):
    """Get git status."""

    def get_name(self) -> str:
        return "git_status"

    def get_description(self) -> str:
        return "Get git repository status."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Repository directory"},
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {"success": True, "status": result.stdout, "clean": len(result.stdout.strip()) == 0}
        except Exception as e:
            return {"success": False, "error": str(e)}


class GitDiffTool(BaseTool):
    """Get git diff."""

    def get_name(self) -> str:
        return "git_diff"

    def get_description(self) -> str:
        return "Get git diff for changes."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Repository directory"},
                "file_path": {"type": "string", "description": "Specific file to diff"},
                "staged": {"type": "boolean", "description": "Show staged changes", "default": False},
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            cmd = ["git", "diff"]
            
            if arguments.get("staged"):
                cmd.append("--staged")
            
            if arguments.get("file_path"):
                cmd.append(arguments["file_path"])

            result = subprocess.run(cmd, cwd=directory, capture_output=True, text=True, timeout=10)
            return {"success": True, "diff": result.stdout}
        except Exception as e:
            return {"success": False, "error": str(e)}


class GitCommitTool(BaseTool):
    """Create git commit."""

    def get_name(self) -> str:
        return "git_commit"

    def get_description(self) -> str:
        return "Create a git commit with staged changes."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Repository directory"},
                "message": {"type": "string", "description": "Commit message"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Files to add"},
            },
            "required": ["directory", "message"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            message = arguments["message"]
            files = arguments.get("files", [])

            # Add files if specified
            if files:
                for file in files:
                    subprocess.run(["git", "add", file], cwd=directory, timeout=10)

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=10,
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "committed": result.returncode == 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
