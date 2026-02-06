"""
MCP Tool for code quality checking.

This module provides tools for checking code complexity, detecting duplicates,
and identifying code smells.
"""

import ast
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class CodeQualityTool(BaseTool):
    """
    MCP tool for code quality checking.

    Provides complexity analysis, duplicate detection, and code smell identification.
    """

    def get_name(self) -> str:
        """Get tool name."""
        return "check_code_quality"

    def get_description(self) -> str:
        """Get tool description."""
        return (
            "Check code quality including complexity, duplicates, and code smells. "
            "Helps maintain high code quality standards."
        )

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool arguments."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to check",
                },
                "check_type": {
                    "type": "string",
                    "enum": ["complexity", "duplicates", "smells", "all"],
                    "description": "Type of quality check to perform",
                    "default": "all",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute code quality check.

        Args:
            arguments: Dictionary with check parameters

        Returns:
            Dictionary with quality metrics
        """
        try:
            file_path = arguments["file_path"]
            check_type = arguments.get("check_type", "all")

            path = Path(file_path)
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            content = path.read_text(encoding="utf-8")

            result: dict[str, Any] = {"success": True, "file": str(path.absolute())}

            if check_type in ["complexity", "all"]:
                result["complexity"] = self._check_complexity(content)

            if check_type in ["duplicates", "all"]:
                result["duplicates"] = self._check_duplicates(content)

            if check_type in ["smells", "all"]:
                result["smells"] = self._check_smells(content)

            return result

        except Exception as e:
            return {"success": False, "error": f"Failed to check quality: {str(e)}"}

    def _check_complexity(self, content: str) -> dict[str, Any]:
        """Check code complexity."""
        try:
            tree = ast.parse(content)
            complexities = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    complexity = self._calculate_cyclomatic_complexity(node)
                    complexities.append({
                        "function": node.name,
                        "cyclomatic": complexity,
                        "line": node.lineno,
                    })

            avg_complexity = sum(c["cyclomatic"] for c in complexities) / len(complexities) if complexities else 0

            return {
                "functions": complexities,
                "average": round(avg_complexity, 2),
                "max": max((c["cyclomatic"] for c in complexities), default=0),
            }

        except Exception:
            return {"error": "Failed to parse Python code"}

    def _calculate_cyclomatic_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            # Count decision points
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        return complexity

    def _check_duplicates(self, content: str) -> dict[str, Any]:
        """Check for duplicate code blocks."""
        lines = content.splitlines()
        duplicates = []

        # Simple duplicate detection: find repeated 3+ line blocks
        min_lines = 3
        seen_blocks = {}

        for i in range(len(lines) - min_lines + 1):
            block = tuple(lines[i:i + min_lines])
            block_str = "\n".join(block)

            # Skip empty or comment-only blocks
            if not block_str.strip() or all(line.strip().startswith("#") for line in block):
                continue

            if block in seen_blocks:
                duplicates.append({
                    "lines": [seen_blocks[block], i + 1],
                    "size": min_lines,
                })
            else:
                seen_blocks[block] = i + 1

        return {
            "count": len(duplicates),
            "blocks": duplicates[:10],  # Limit to first 10
        }

    def _check_smells(self, content: str) -> dict[str, Any]:
        """Check for code smells."""
        smells = []

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                # Long parameter list
                if isinstance(node, ast.FunctionDef):
                    if len(node.args.args) > 5:
                        smells.append({
                            "type": "long_parameter_list",
                            "function": node.name,
                            "line": node.lineno,
                            "params": len(node.args.args),
                        })

                    # Long function
                    if hasattr(node, 'end_lineno') and node.end_lineno:
                        length = node.end_lineno - node.lineno
                        if length > 50:
                            smells.append({
                                "type": "long_function",
                                "function": node.name,
                                "line": node.lineno,
                                "length": length,
                            })

        except Exception:
            pass

        return {
            "count": len(smells),
            "issues": smells,
        }
