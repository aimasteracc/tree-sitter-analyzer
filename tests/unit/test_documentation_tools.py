"""
Tests for mcp/tools/documentation.py module.

TDD: Testing documentation generation tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.documentation import (
    DocGeneratorTool,
    APIDocTool,
)


class TestDocGeneratorTool:
    """Test DocGeneratorTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = DocGeneratorTool()
        assert tool.get_name() == "generate_docs"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = DocGeneratorTool()
        assert "documentation" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = DocGeneratorTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "format" in schema["properties"]
        assert "file_path" in schema["required"]

    def test_file_not_found(self) -> None:
        """Should return error for non-existent file."""
        tool = DocGeneratorTool()
        result = tool.execute({"file_path": "/nonexistent/file.py"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_generate_docs_simple(self) -> None:
        """Should generate documentation for simple file."""
        tool = DocGeneratorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''"""Module docstring."""

def hello():
    """Say hello."""
    pass
''')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert "Module docstring" in result["documentation"]
            assert "hello" in result["documentation"]
            assert "Say hello" in result["documentation"]
        finally:
            Path(file_path).unlink()

    def test_generate_docs_with_class(self) -> None:
        """Should include class documentation."""
        tool = DocGeneratorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''
class MyClass:
    """A sample class."""
    
    def method(self):
        """A method."""
        pass
''')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert "MyClass" in result["documentation"]
            assert "sample class" in result["documentation"]
            assert "method" in result["documentation"]
        finally:
            Path(file_path).unlink()

    def test_default_format_markdown(self) -> None:
        """Should default to markdown format."""
        tool = DocGeneratorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('def test(): pass')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert result["format"] == "markdown"
        finally:
            Path(file_path).unlink()

    def test_file_name_in_header(self) -> None:
        """Should include file name in documentation header."""
        tool = DocGeneratorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('def test(): pass')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            # Header should include file stem
            assert "#" in result["documentation"]
        finally:
            Path(file_path).unlink()

    def test_handle_no_docstrings(self) -> None:
        """Should handle files without docstrings."""
        tool = DocGeneratorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''
def no_doc():
    pass

class NoDoc:
    pass
''')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            # Should still list functions/classes even without docs
            assert "no_doc" in result["documentation"]
            assert "NoDoc" in result["documentation"]
        finally:
            Path(file_path).unlink()

    def test_handle_syntax_error(self) -> None:
        """Should return error for syntax errors."""
        tool = DocGeneratorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("{{{ invalid python")
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is False
            assert "error" in result
        finally:
            Path(file_path).unlink()


class TestAPIDocTool:
    """Test APIDocTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = APIDocTool()
        assert tool.get_name() == "generate_api_docs"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = APIDocTool()
        assert "api" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = APIDocTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "directory" in schema["properties"]
        assert "output_file" in schema["properties"]
        assert "directory" in schema["required"]

    def test_directory_not_found(self) -> None:
        """Should return error for non-existent directory."""
        tool = APIDocTool()
        result = tool.execute({"directory": "/nonexistent/path"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_generate_api_docs_simple(self) -> None:
        """Should generate API docs for directory."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "api.py"
            py_file.write_text('''"""API module."""

class APIHandler:
    """Handles API requests."""
    pass

def get_data():
    """Get data from API."""
    pass
''')
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_processed"] == 1
            assert "API Documentation" in result["documentation"]
            assert "APIHandler" in result["documentation"]
            assert "get_data" in result["documentation"]

    def test_generate_api_docs_multiple_files(self) -> None:
        """Should process multiple files."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "users.py"
            file1.write_text('''
class UserService:
    """User service."""
    pass
''')
            
            file2 = Path(tmpdir) / "orders.py"
            file2.write_text('''
class OrderService:
    """Order service."""
    pass
''')
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_processed"] == 2
            assert "UserService" in result["documentation"]
            assert "OrderService" in result["documentation"]

    def test_skip_private_functions(self) -> None:
        """Should skip private functions (starting with _)."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "module.py"
            py_file.write_text('''
def public_func():
    """Public function."""
    pass

def _private_func():
    """Private function."""
    pass
''')
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert "public_func" in result["documentation"]
            assert "_private_func" not in result["documentation"]

    def test_write_to_output_file(self) -> None:
        """Should write documentation to output file."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "module.py"
            py_file.write_text('def test(): pass')
            
            output_file = Path(tmpdir) / "docs.md"
            
            result = tool.execute({
                "directory": tmpdir,
                "output_file": str(output_file)
            })
            
            assert result["success"] is True
            assert output_file.exists()
            content = output_file.read_text()
            assert "API Documentation" in content

    def test_handle_empty_directory(self) -> None:
        """Should handle empty directory."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_processed"] == 0
            assert "API Documentation" in result["documentation"]

    def test_handle_nested_directories(self) -> None:
        """Should process files in nested directories."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "sub" / "module"
            nested_dir.mkdir(parents=True)
            
            py_file = nested_dir / "core.py"
            py_file.write_text('''
class CoreClass:
    """Core class."""
    pass
''')
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_processed"] >= 1
            assert "CoreClass" in result["documentation"]

    def test_handle_syntax_errors_in_files(self) -> None:
        """Should skip files with syntax errors."""
        tool = APIDocTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "good.py"
            good_file.write_text('class Good: pass')
            
            bad_file = Path(tmpdir) / "bad.py"
            bad_file.write_text('{{{ invalid')
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert "Good" in result["documentation"]
