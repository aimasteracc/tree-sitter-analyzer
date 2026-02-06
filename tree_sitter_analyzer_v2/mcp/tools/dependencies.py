"""MCP Tools for dependency analysis."""
import ast
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class DependencyAnalyzerTool(BaseTool):
    """Analyze project dependencies."""

    def get_name(self) -> str:
        return "analyze_dependencies"

    def get_description(self) -> str:
        return "Analyze project dependencies and imports."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Project directory"},
                "include_stdlib": {"type": "boolean", "description": "Include stdlib", "default": False},
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            if not directory.exists():
                return {"success": False, "error": "Directory not found"}

            imports = set()
            py_files = list(directory.rglob("*.py"))

            for file_path in py_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                imports.add(alias.name.split(".")[0])
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports.add(node.module.split(".")[0])
                except Exception:
                    continue

            return {
                "success": True,
                "dependencies": sorted(imports),
                "count": len(imports),
                "files_analyzed": len(py_files),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class DependencyGraphTool(BaseTool):
    """Generate dependency graph."""

    def get_name(self) -> str:
        return "dependency_graph"

    def get_description(self) -> str:
        return "Generate module dependency graph visualization."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Project directory"},
                "format": {"type": "string", "enum": ["mermaid", "dot"], "default": "mermaid"},
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            if not directory.exists():
                return {"success": False, "error": "Directory not found"}

            # Build dependency graph
            dependencies = {}
            py_files = list(directory.rglob("*.py"))

            for file_path in py_files:
                try:
                    module_name = file_path.stem
                    content = file_path.read_text(encoding="utf-8")
                    tree = ast.parse(content)

                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.Import, ast.ImportFrom)):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    imports.append(alias.name.split(".")[0])
                            elif node.module:
                                imports.append(node.module.split(".")[0])

                    dependencies[module_name] = list(set(imports))
                except Exception:
                    continue

            # Generate Mermaid diagram
            mermaid = "graph TD\n"
            for module, deps in dependencies.items():
                for dep in deps:
                    if dep in dependencies:  # Only internal dependencies
                        mermaid += f"    {module} --> {dep}\n"

            return {
                "success": True,
                "graph": mermaid,
                "modules": len(dependencies),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
