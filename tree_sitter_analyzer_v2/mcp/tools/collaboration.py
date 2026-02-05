"""Collaboration Tools"""

import ast
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class CodeReviewTool(BaseTool):
    """Code review tool"""

    def get_name(self) -> str:
        return "code_reviewer"

    def get_description(self) -> str:
        return "Automatic code review, check common issues"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to review",
                },
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Check types to perform",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            issues = []

            # Check naming conventions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.islower():
                        issues.append(
                            {
                                "severity": "warning",
                                "type": "naming",
                                "message": f"Function name {node.name} should use lowercase and underscores",
                            }
                        )

                if isinstance(node, ast.ClassDef):
                    if not node.name[0].isupper():
                        issues.append(
                            {
                                "severity": "warning",
                                "type": "naming",
                                "message": f"Class name {node.name} should use PascalCase",
                            }
                        )

            # Check complexity
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 50:
                        issues.append(
                            {
                                "severity": "error",
                                "type": "complexity",
                                "message": f"Function {node.name} is too complex ({len(node.body)} lines)",
                            }
                        )

            return {
                "success": True,
                "file": str(file_path),
                "issues": issues,
                "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class CommentManagerTool(BaseTool):
    """Comment management tool"""

    def get_name(self) -> str:
        return "comment_manager"

    def get_description(self) -> str:
        return "Manage code comments (extract, analyze, generate)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to process",
                },
                "operation": {
                    "type": "string",
                    "enum": ["extract", "analyze", "suggest"],
                    "description": "Operation type",
                },
            },
            "required": ["file_path", "operation"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])
        operation = arguments["operation"]

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")

            if operation == "extract":
                return self._extract_comments(content)
            elif operation == "analyze":
                return self._analyze_comments(content)
            elif operation == "suggest":
                return self._suggest_comments(content, file_path)

            return {"success": False, "error": f"Unknown operation: {operation}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_comments(self, content: str) -> dict[str, Any]:
        """Extract comments"""
        comments = []
        for i, line in enumerate(content.splitlines(), 1):
            if "#" in line:
                comment = line[line.index("#") :].strip()
                comments.append({"line": i, "comment": comment})

        return {"success": True, "comments": comments, "count": len(comments)}

    def _analyze_comments(self, content: str) -> dict[str, Any]:
        """Analyze comment quality"""
        lines = content.splitlines()
        total_lines = len(lines)
        comment_lines = sum(1 for line in lines if "#" in line)
        code_lines = total_lines - comment_lines

        ratio = comment_lines / code_lines if code_lines > 0 else 0

        return {
            "success": True,
            "total_lines": total_lines,
            "comment_lines": comment_lines,
            "code_lines": code_lines,
            "comment_ratio": round(ratio, 2),
            "quality": "good" if 0.1 <= ratio <= 0.3 else "needs_improvement",
        }

    def _suggest_comments(self, content: str, file_path: Path) -> dict[str, Any]:
        """Suggest where to add comments"""
        tree = ast.parse(content)
        suggestions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not ast.get_docstring(node):
                    suggestions.append(
                        {
                            "line": node.lineno,
                            "type": "function",
                            "name": node.name,
                            "suggestion": f"Add docstring for function {node.name}",
                        }
                    )

            if isinstance(node, ast.ClassDef):
                if not ast.get_docstring(node):
                    suggestions.append(
                        {
                            "line": node.lineno,
                            "type": "class",
                            "name": node.name,
                            "suggestion": f"Add docstring for class {node.name}",
                        }
                    )

        return {
            "success": True,
            "file": str(file_path),
            "suggestions": suggestions,
        }


class TaskManagerTool(BaseTool):
    """Task management tool"""

    def get_name(self) -> str:
        return "task_manager"

    def get_description(self) -> str:
        return "Manage TODO/FIXME/HACK markers in code"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to scan",
                },
                "task_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task types to find (TODO, FIXME, HACK, NOTE)",
                },
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = Path(arguments["directory"])
        task_types = arguments.get("task_types", ["TODO", "FIXME", "HACK"])

        if not directory.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        tasks = []
        pattern = re.compile(r"#\s*(" + "|".join(task_types) + r"):\s*(.+)")

        for file_path in directory.rglob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                for i, line in enumerate(content.splitlines(), 1):
                    match = pattern.search(line)
                    if match:
                        tasks.append(
                            {
                                "file": str(file_path.relative_to(directory)),
                                "line": i,
                                "type": match.group(1),
                                "description": match.group(2).strip(),
                            }
                        )
            except Exception:
                continue

        # Group by type
        by_type = {}
        for task in tasks:
            task_type = task["type"]
            if task_type not in by_type:
                by_type[task_type] = []
            by_type[task_type].append(task)

        return {
            "success": True,
            "tasks": tasks,
            "total": len(tasks),
            "by_type": {k: len(v) for k, v in by_type.items()},
        }


class NotebookEditorTool(BaseTool):
    """Notebook editor tool"""

    def get_name(self) -> str:
        return "notebook_editor"

    def get_description(self) -> str:
        return "Edit Jupyter Notebook files"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Notebook file path",
                },
                "operation": {
                    "type": "string",
                    "enum": ["read", "add_cell", "delete_cell", "execute"],
                    "description": "Operation type",
                },
                "cell_index": {
                    "type": "integer",
                    "description": "Cell index (for delete_cell)",
                },
                "cell_content": {
                    "type": "string",
                    "description": "Cell content (for add_cell)",
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "Cell type (for add_cell)",
                },
            },
            "required": ["notebook_path", "operation"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        notebook_path = Path(arguments["notebook_path"])
        operation = arguments["operation"]

        if operation != "read" and not notebook_path.exists():
            return {"success": False, "error": f"Notebook not found: {notebook_path}"}

        try:
            import json

            if operation == "read":
                if notebook_path.exists():
                    content = json.loads(notebook_path.read_text(encoding="utf-8"))
                    return {
                        "success": True,
                        "cells": len(content.get("cells", [])),
                        "metadata": content.get("metadata", {}),
                    }
                return {"success": False, "error": "File not found"}

            elif operation == "add_cell":
                content = json.loads(notebook_path.read_text(encoding="utf-8"))
                cell_content = arguments.get("cell_content", "")
                cell_type = arguments.get("cell_type", "code")

                new_cell = {
                    "cell_type": cell_type,
                    "metadata": {},
                    "source": [cell_content],
                }
                if cell_type == "code":
                    new_cell["outputs"] = []
                    new_cell["execution_count"] = None

                content["cells"].append(new_cell)
                notebook_path.write_text(
                    json.dumps(content, indent=2), encoding="utf-8"
                )

                return {"success": True, "message": "Cell added"}

            elif operation == "delete_cell":
                content = json.loads(notebook_path.read_text(encoding="utf-8"))
                cell_index = arguments.get("cell_index", 0)

                if 0 <= cell_index < len(content["cells"]):
                    del content["cells"][cell_index]
                    notebook_path.write_text(
                        json.dumps(content, indent=2), encoding="utf-8"
                    )
                    return {"success": True, "message": "Cell deleted"}
                return {"success": False, "error": "Invalid cell index"}

            return {"success": False, "error": f"Unknown operation: {operation}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ShellExecutorTool(BaseTool):
    """Safe shell executor tool"""

    def get_name(self) -> str:
        return "shell_executor"

    def get_description(self) -> str:
        return "Execute shell commands in a safe sandbox"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["command"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        import subprocess

        command = arguments["command"]
        working_directory = arguments.get("working_directory")
        timeout = arguments.get("timeout", 30)

        # Safety check: block dangerous commands
        dangerous_commands = ["rm -rf", "del /f", "format", "mkfs"]
        if any(cmd in command.lower() for cmd in dangerous_commands):
            return {"success": False, "error": "Dangerous command detected, execution blocked"}

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command execution timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
