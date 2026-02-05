"""协作工具"""

import ast
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class CodeReviewTool(BaseTool):
    """代码审查工具"""

    def get_name(self) -> str:
        return "code_reviewer"

    def get_description(self) -> str:
        return "自动代码审查，检查常见问题"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要审查的文件路径",
                },
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要执行的检查类型",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            issues = []

            # 检查命名规范
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.islower():
                        issues.append(
                            {
                                "severity": "warning",
                                "type": "naming",
                                "message": f"函数名 {node.name} 应使用小写和下划线",
                            }
                        )

                if isinstance(node, ast.ClassDef):
                    if not node.name[0].isupper():
                        issues.append(
                            {
                                "severity": "warning",
                                "type": "naming",
                                "message": f"类名 {node.name} 应使用 PascalCase",
                            }
                        )

            # 检查复杂度
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 50:
                        issues.append(
                            {
                                "severity": "error",
                                "type": "complexity",
                                "message": f"函数 {node.name} 过于复杂（{len(node.body)} 行）",
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
    """注释管理工具"""

    def get_name(self) -> str:
        return "comment_manager"

    def get_description(self) -> str:
        return "管理代码注释（提取、分析、生成）"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要处理的文件路径",
                },
                "operation": {
                    "type": "string",
                    "enum": ["extract", "analyze", "suggest"],
                    "description": "操作类型",
                },
            },
            "required": ["file_path", "operation"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(arguments["file_path"])
        operation = arguments["operation"]

        if not file_path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            content = file_path.read_text(encoding="utf-8")

            if operation == "extract":
                return self._extract_comments(content)
            elif operation == "analyze":
                return self._analyze_comments(content)
            elif operation == "suggest":
                return self._suggest_comments(content, file_path)

            return {"success": False, "error": f"未知操作: {operation}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_comments(self, content: str) -> dict[str, Any]:
        """提取注释"""
        comments = []
        for i, line in enumerate(content.splitlines(), 1):
            if "#" in line:
                comment = line[line.index("#") :].strip()
                comments.append({"line": i, "comment": comment})

        return {"success": True, "comments": comments, "count": len(comments)}

    def _analyze_comments(self, content: str) -> dict[str, Any]:
        """分析注释质量"""
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
        """建议添加注释的位置"""
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
                            "suggestion": f"为函数 {node.name} 添加文档字符串",
                        }
                    )

            if isinstance(node, ast.ClassDef):
                if not ast.get_docstring(node):
                    suggestions.append(
                        {
                            "line": node.lineno,
                            "type": "class",
                            "name": node.name,
                            "suggestion": f"为类 {node.name} 添加文档字符串",
                        }
                    )

        return {
            "success": True,
            "file": str(file_path),
            "suggestions": suggestions,
        }


class TaskManagerTool(BaseTool):
    """任务管理工具"""

    def get_name(self) -> str:
        return "task_manager"

    def get_description(self) -> str:
        return "管理代码中的 TODO/FIXME/HACK 标记"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "要扫描的目录路径",
                },
                "task_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要查找的任务类型（TODO, FIXME, HACK, NOTE）",
                },
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = Path(arguments["directory"])
        task_types = arguments.get("task_types", ["TODO", "FIXME", "HACK"])

        if not directory.exists():
            return {"success": False, "error": f"目录不存在: {directory}"}

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

        # 按类型分组
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
    """Notebook 编辑工具"""

    def get_name(self) -> str:
        return "notebook_editor"

    def get_description(self) -> str:
        return "编辑 Jupyter Notebook 文件"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Notebook 文件路径",
                },
                "operation": {
                    "type": "string",
                    "enum": ["read", "add_cell", "delete_cell", "execute"],
                    "description": "操作类型",
                },
                "cell_index": {
                    "type": "integer",
                    "description": "单元格索引（用于 delete_cell）",
                },
                "cell_content": {
                    "type": "string",
                    "description": "单元格内容（用于 add_cell）",
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "单元格类型（用于 add_cell）",
                },
            },
            "required": ["notebook_path", "operation"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        notebook_path = Path(arguments["notebook_path"])
        operation = arguments["operation"]

        if operation != "read" and not notebook_path.exists():
            return {"success": False, "error": f"Notebook 不存在: {notebook_path}"}

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
                return {"success": False, "error": "文件不存在"}

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

                return {"success": True, "message": "单元格已添加"}

            elif operation == "delete_cell":
                content = json.loads(notebook_path.read_text(encoding="utf-8"))
                cell_index = arguments.get("cell_index", 0)

                if 0 <= cell_index < len(content["cells"]):
                    del content["cells"][cell_index]
                    notebook_path.write_text(
                        json.dumps(content, indent=2), encoding="utf-8"
                    )
                    return {"success": True, "message": "单元格已删除"}
                return {"success": False, "error": "单元格索引无效"}

            return {"success": False, "error": f"未知操作: {operation}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ShellExecutorTool(BaseTool):
    """安全 Shell 执行工具"""

    def get_name(self) -> str:
        return "shell_executor"

    def get_description(self) -> str:
        return "在安全沙箱中执行 Shell 命令"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令",
                },
                "working_directory": {
                    "type": "string",
                    "description": "工作目录",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒）",
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

        # 安全检查：禁止危险命令
        dangerous_commands = ["rm -rf", "del /f", "format", "mkfs"]
        if any(cmd in command.lower() for cmd in dangerous_commands):
            return {"success": False, "error": "检测到危险命令，已拒绝执行"}

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
            return {"success": False, "error": "命令执行超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}
