"""MCP Tools for documentation generation."""
import ast
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class DocGeneratorTool(BaseTool):
    """Generate documentation from code."""

    def get_name(self) -> str:
        return "generate_docs"

    def get_description(self) -> str:
        return "Generate documentation from Python code docstrings."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Python file to document"},
                "format": {"type": "string", "enum": ["markdown", "rst"], "default": "markdown"},
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            file_path = Path(arguments["file_path"])
            if not file_path.exists():
                return {"success": False, "error": "File not found"}

            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            docs = []
            docs.append(f"# {file_path.stem}\n")

            # Extract module docstring
            if ast.get_docstring(tree):
                docs.append(f"{ast.get_docstring(tree)}\n")

            # Extract classes and functions
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    docs.append(f"\n## Class: {node.name}\n")
                    if ast.get_docstring(node):
                        docs.append(f"{ast.get_docstring(node)}\n")

                elif isinstance(node, ast.FunctionDef):
                    docs.append(f"\n### Function: {node.name}\n")
                    if ast.get_docstring(node):
                        docs.append(f"{ast.get_docstring(node)}\n")

            return {
                "success": True,
                "documentation": "\n".join(docs),
                "format": arguments.get("format", "markdown"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class APIDocTool(BaseTool):
    """Generate API documentation."""

    def get_name(self) -> str:
        return "generate_api_docs"

    def get_description(self) -> str:
        return "Generate API documentation for a module or package."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Package directory"},
                "output_file": {"type": "string", "description": "Output file path"},
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            if not directory.exists():
                return {"success": False, "error": "Directory not found"}

            docs = ["# API Documentation\n\n"]
            py_files = sorted(directory.rglob("*.py"))

            for file_path in py_files:
                try:
                    relative_path = file_path.relative_to(directory)
                    docs.append(f"\n## {relative_path}\n")

                    content = file_path.read_text(encoding="utf-8")
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            docs.append(f"\n### `{node.name}`\n")
                            if ast.get_docstring(node):
                                docs.append(f"{ast.get_docstring(node)}\n")
                        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                            docs.append(f"\n#### `{node.name}()`\n")
                            if ast.get_docstring(node):
                                docs.append(f"{ast.get_docstring(node)}\n")
                except Exception:
                    continue

            documentation = "\n".join(docs)

            # Optionally write to file
            output_file = arguments.get("output_file")
            if output_file:
                Path(output_file).write_text(documentation, encoding="utf-8")

            return {
                "success": True,
                "documentation": documentation,
                "files_processed": len(py_files),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
