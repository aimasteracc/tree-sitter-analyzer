"""
Tests for mcp/tools/generator.py module.

TDD: Testing code generation tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.generator import (
    TestGeneratorTool,
    MockGeneratorTool,
    ClassGeneratorTool,
)


class TestTestGeneratorTool:
    """Test TestGeneratorTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = TestGeneratorTool()
        assert tool.get_name() == "generate_tests"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = TestGeneratorTool()
        assert "test" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = TestGeneratorTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "source_file" in schema["properties"]
        assert "source_file" in schema["required"]

    def test_source_file_not_found(self) -> None:
        """Should return error for non-existent file."""
        tool = TestGeneratorTool()
        result = tool.execute({"source_file": "/nonexistent/file.py"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_generate_tests_for_functions(self) -> None:
        """Should generate tests for functions."""
        tool = TestGeneratorTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "module.py"
            source.write_text('''
def get_data():
    pass

def process_data():
    pass
''')
            output = Path(tmpdir) / "test_module.py"
            
            result = tool.execute({
                "source_file": str(source),
                "output_file": str(output)
            })
            
            assert result["success"] is True
            assert result["tests_generated"] >= 2
            
            # Verify output file content
            content = output.read_text()
            assert "test_get_data" in content
            assert "test_process_data" in content

    def test_generate_tests_for_classes(self) -> None:
        """Should generate tests for classes."""
        tool = TestGeneratorTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "module.py"
            source.write_text('''
class UserService:
    pass

class OrderService:
    pass
''')
            output = Path(tmpdir) / "test_module.py"
            
            result = tool.execute({
                "source_file": str(source),
                "output_file": str(output)
            })
            
            assert result["success"] is True
            assert result["tests_generated"] >= 2
            
            content = output.read_text()
            assert "TestUserService" in content
            assert "TestOrderService" in content

    def test_skip_private_functions(self) -> None:
        """Should skip functions starting with underscore."""
        tool = TestGeneratorTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "module.py"
            source.write_text('''
def public_func():
    pass

def _private_func():
    pass
''')
            output = Path(tmpdir) / "test_module.py"
            
            result = tool.execute({
                "source_file": str(source),
                "output_file": str(output)
            })
            
            content = output.read_text()
            assert "test_public_func" in content
            assert "test__private_func" not in content

    def test_auto_generate_output_path(self) -> None:
        """Should auto-generate output path if not provided."""
        tool = TestGeneratorTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            source = src_dir / "module.py"
            source.write_text("def test(): pass")
            
            result = tool.execute({"source_file": str(source)})
            
            assert result["success"] is True
            assert "output_file" in result


class TestMockGeneratorTool:
    """Test MockGeneratorTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = MockGeneratorTool()
        assert tool.get_name() == "generate_mocks"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = MockGeneratorTool()
        assert "mock" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = MockGeneratorTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "class_name" in schema["properties"]
        assert "class_name" in schema["required"]

    def test_generate_basic_mock(self) -> None:
        """Should generate basic mock class."""
        tool = MockGeneratorTool()
        
        result = tool.execute({"class_name": "UserService"})
        
        assert result["success"] is True
        assert result["class_name"] == "MockUserService"
        assert "MockUserService" in result["mock_code"]
        assert "Mock" in result["mock_code"]

    def test_generate_mock_with_methods(self) -> None:
        """Should generate mock with specified methods."""
        tool = MockGeneratorTool()
        
        result = tool.execute({
            "class_name": "DataService",
            "methods": ["get_data", "save_data", "delete_data"]
        })
        
        assert result["success"] is True
        assert "self.get_data = Mock" in result["mock_code"]
        assert "self.save_data = Mock" in result["mock_code"]
        assert "self.delete_data = Mock" in result["mock_code"]

    def test_generate_mock_no_methods(self) -> None:
        """Should generate mock without methods."""
        tool = MockGeneratorTool()
        
        result = tool.execute({"class_name": "EmptyService"})
        
        assert result["success"] is True
        assert "MockEmptyService" in result["mock_code"]


class TestClassGeneratorTool:
    """Test ClassGeneratorTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = ClassGeneratorTool()
        assert tool.get_name() == "generate_class"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = ClassGeneratorTool()
        assert "class" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = ClassGeneratorTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "class_name" in schema["properties"]
        assert "pattern" in schema["properties"]

    def test_generate_dataclass(self) -> None:
        """Should generate dataclass."""
        tool = ClassGeneratorTool()
        
        result = tool.execute({
            "class_name": "User",
            "pattern": "dataclass"
        })
        
        assert result["success"] is True
        assert result["class_name"] == "User"
        assert "@dataclass" in result["code"]
        assert "class User" in result["code"]

    def test_generate_singleton(self) -> None:
        """Should generate singleton class."""
        tool = ClassGeneratorTool()
        
        result = tool.execute({
            "class_name": "Config",
            "pattern": "singleton"
        })
        
        assert result["success"] is True
        assert "_instance" in result["code"]
        assert "__new__" in result["code"]

    def test_generate_default_pattern(self) -> None:
        """Should default to dataclass pattern."""
        tool = ClassGeneratorTool()
        
        result = tool.execute({"class_name": "MyClass"})
        
        assert result["success"] is True
        assert "@dataclass" in result["code"]

    def test_generate_unknown_pattern(self) -> None:
        """Should generate basic class for unknown pattern."""
        tool = ClassGeneratorTool()
        
        result = tool.execute({
            "class_name": "Service",
            "pattern": "unknown_pattern"
        })
        
        assert result["success"] is True
        assert "class Service" in result["code"]
        assert "__init__" in result["code"]

    def test_write_to_output_file(self) -> None:
        """Should write to output file."""
        tool = ClassGeneratorTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "generated.py"
            
            result = tool.execute({
                "class_name": "TestClass",
                "output_file": str(output)
            })
            
            assert result["success"] is True
            assert output.exists()
            content = output.read_text()
            assert "TestClass" in content
