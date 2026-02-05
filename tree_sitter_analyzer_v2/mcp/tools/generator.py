"""MCP Tools for code generation."""
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class TestGeneratorTool(BaseTool):
    """Generate test templates."""

    def get_name(self) -> str:
        return "generate_tests"

    def get_description(self) -> str:
        return "Generate pytest test templates for Python modules."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_file": {"type": "string", "description": "Source file to generate tests for"},
                "output_file": {"type": "string", "description": "Output test file path"},
            },
            "required": ["source_file"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            source_file = Path(arguments["source_file"])
            if not source_file.exists():
                return {"success": False, "error": "Source file not found"}

            # Generate test file path
            output_file = arguments.get("output_file")
            if not output_file:
                output_file = source_file.parent.parent / "tests" / f"test_{source_file.name}"
            else:
                output_file = Path(output_file)

            # Read source to extract functions/classes
            content = source_file.read_text(encoding="utf-8")
            
            import ast
            tree = ast.parse(content)
            
            functions = []
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)

            # Generate test template
            test_content = f'''"""Tests for {source_file.name}."""
import pytest
from {source_file.stem} import *


'''
            
            for cls in classes:
                test_content += f'''class Test{cls}:
    """Test cases for {cls}."""
    
    def test_{cls.lower()}_creation(self):
        """Test {cls} creation."""
        # TODO: Implement test
        pass

'''

            for func in functions:
                test_content += f'''def test_{func}():
    """Test {func} function."""
    # TODO: Implement test
    pass

'''

            # Write test file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(test_content, encoding="utf-8")

            return {
                "success": True,
                "output_file": str(output_file.absolute()),
                "tests_generated": len(classes) + len(functions),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class MockGeneratorTool(BaseTool):
    """Generate mock objects."""

    def get_name(self) -> str:
        return "generate_mocks"

    def get_description(self) -> str:
        return "Generate mock objects for testing."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "class_name": {"type": "string", "description": "Class to mock"},
                "methods": {"type": "array", "items": {"type": "string"}, "description": "Methods to mock"},
            },
            "required": ["class_name"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            class_name = arguments["class_name"]
            methods = arguments.get("methods", [])

            mock_code = f'''"""Mock for {class_name}."""
from unittest.mock import Mock, MagicMock


class Mock{class_name}:
    """Mock implementation of {class_name}."""
    
    def __init__(self):
'''
            
            for method in methods:
                mock_code += f'''        self.{method} = Mock(return_value=None)
'''

            return {
                "success": True,
                "mock_code": mock_code,
                "class_name": f"Mock{class_name}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ClassGeneratorTool(BaseTool):
    """Generate class templates."""

    def get_name(self) -> str:
        return "generate_class"

    def get_description(self) -> str:
        return "Generate Python class templates with common patterns."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "class_name": {"type": "string", "description": "Class name"},
                "pattern": {"type": "string", "enum": ["dataclass", "singleton", "factory", "builder"], "default": "dataclass"},
                "output_file": {"type": "string", "description": "Output file path"},
            },
            "required": ["class_name"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            class_name = arguments["class_name"]
            pattern = arguments.get("pattern", "dataclass")

            if pattern == "dataclass":
                code = f'''"""Data class for {class_name}."""
from dataclasses import dataclass


@dataclass
class {class_name}:
    """Data class {class_name}."""
    
    # Add fields here
    pass
'''
            elif pattern == "singleton":
                code = f'''"""Singleton {class_name}."""


class {class_name}:
    """Singleton {class_name}."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
'''
            else:
                code = f'''"""Class {class_name}."""


class {class_name}:
    """Class {class_name}."""
    
    def __init__(self):
        pass
'''

            # Optionally write to file
            output_file = arguments.get("output_file")
            if output_file:
                Path(output_file).write_text(code, encoding="utf-8")

            return {
                "success": True,
                "code": code,
                "class_name": class_name,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
