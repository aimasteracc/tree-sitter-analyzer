"""MCP Tools for code metrics."""
import ast
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class CodeMetricsTool(BaseTool):
    """Calculate code metrics."""

    def get_name(self) -> str:
        return "calculate_metrics"

    def get_description(self) -> str:
        return "Calculate comprehensive code metrics (LOC, complexity, maintainability)."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory to analyze"},
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            path = Path(arguments["path"])
            if not path.exists():
                return {"success": False, "error": "Path not found"}

            if path.is_file():
                return self._analyze_file(path)
            else:
                return self._analyze_directory(path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _analyze_file(self, file_path: Path) -> dict[str, Any]:
        """Analyze single file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            # Count lines
            total_lines = len(lines)
            code_lines = len([line for line in lines if line.strip() and not line.strip().startswith("#")])
            comment_lines = len([line for line in lines if line.strip().startswith("#")])
            blank_lines = len([line for line in lines if not line.strip()])

            # Parse AST
            tree = ast.parse(content)
            functions = len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
            classes = len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])

            return {
                "success": True,
                "file": str(file_path.absolute()),
                "lines": {
                    "total": total_lines,
                    "code": code_lines,
                    "comments": comment_lines,
                    "blank": blank_lines,
                },
                "elements": {
                    "functions": functions,
                    "classes": classes,
                },
                "maintainability_index": round(171 - 5.2 * (total_lines / 1000) - 0.23 * functions, 2),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _analyze_directory(self, directory: Path) -> dict[str, Any]:
        """Analyze directory."""
        try:
            py_files = list(directory.rglob("*.py"))

            total_lines = 0
            total_functions = 0
            total_classes = 0

            for file_path in py_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    total_lines += len(content.splitlines())

                    tree = ast.parse(content)
                    total_functions += len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
                    total_classes += len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])
                except Exception:
                    continue

            return {
                "success": True,
                "directory": str(directory.absolute()),
                "files": len(py_files),
                "total_lines": total_lines,
                "total_functions": total_functions,
                "total_classes": total_classes,
                "avg_lines_per_file": round(total_lines / len(py_files), 2) if py_files else 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
