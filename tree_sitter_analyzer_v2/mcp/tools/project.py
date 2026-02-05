"""MCP Tools for project management."""
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class ProjectInitTool(BaseTool):
    """Initialize a new project."""

    def get_name(self) -> str:
        return "init_project"

    def get_description(self) -> str:
        return "Initialize a new Python project with standard structure."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Project directory"},
                "name": {"type": "string", "description": "Project name"},
                "template": {"type": "string", "enum": ["basic", "library", "cli", "web"], "default": "basic"},
            },
            "required": ["directory", "name"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            name = arguments["name"]
            template = arguments.get("template", "basic")

            directory.mkdir(parents=True, exist_ok=True)

            # Create basic structure
            (directory / name).mkdir(exist_ok=True)
            (directory / name / "__init__.py").write_text("")
            (directory / "tests").mkdir(exist_ok=True)
            (directory / "tests" / "__init__.py").write_text("")

            # Create pyproject.toml
            pyproject = f"""[project]
name = "{name}"
version = "0.1.0"
description = "A new Python project"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
            (directory / "pyproject.toml").write_text(pyproject)

            # Create README
            readme = f"""# {name}

A new Python project.

## Installation

```bash
pip install -e .
```

## Usage

```python
import {name}
```
"""
            (directory / "README.md").write_text(readme)

            return {
                "success": True,
                "directory": str(directory.absolute()),
                "files_created": 5,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ProjectAnalyzerTool(BaseTool):
    """Analyze project structure."""

    def get_name(self) -> str:
        return "analyze_project"

    def get_description(self) -> str:
        return "Analyze project structure and provide insights."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Project directory"},
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            directory = Path(arguments["directory"])
            if not directory.exists():
                return {"success": False, "error": "Directory not found"}

            # Count files by type
            py_files = list(directory.rglob("*.py"))
            test_files = [f for f in py_files if "test" in f.name]
            src_files = [f for f in py_files if "test" not in f.name]

            # Calculate total lines
            total_lines = 0
            for file in py_files:
                try:
                    total_lines += len(file.read_text(encoding="utf-8").splitlines())
                except Exception:
                    continue

            return {
                "success": True,
                "total_files": len(py_files),
                "source_files": len(src_files),
                "test_files": len(test_files),
                "total_lines": total_lines,
                "test_ratio": round(len(test_files) / len(src_files), 2) if src_files else 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
