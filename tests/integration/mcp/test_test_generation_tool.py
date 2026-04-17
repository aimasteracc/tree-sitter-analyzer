"""
Integration tests for test generation MCP tool.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.test_generation_tool import TestGenerationTool


@pytest.fixture
async def async_tool() -> TestGenerationTool:
    """Create async test generation tool instance."""
    return TestGenerationTool()


@pytest.fixture
def sample_python_file(temp_dir: tempfile.TemporaryDirectory) -> str:
    """Create a sample Python file for testing."""
    file_path = f"{temp_dir.name}/sample.py"
    with open(file_path, "w") as f:
        f.write("""
def add(x: int, y: int) -> int:
    '''Add two numbers together.'''
    return x + y

def greet(name: str) -> str:
    '''Greet the user by name.'''
    if not name:
        return "Hello, Anonymous!"
    return f"Hello, {name}!"

def divide(a: float, b: float) -> float:
    '''Divide two numbers.'''
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

async def async_function(x: int) -> int:
    '''Async function (should be skipped).'''
    return x * 2
""")
    return file_path


class TestTestGenerationTool:
    """Integration tests for TestGenerationTool."""

    @pytest.fixture
    def tool(self) -> TestGenerationTool:
        """Create test generation tool instance."""
        return TestGenerationTool()

    def test_tool_definition(self, tool: TestGenerationTool) -> None:
        """Should have correct tool definition."""
        definition = tool.get_tool_definition()

        assert definition["name"] == "generate_tests"
        assert "file_path" in definition["inputSchema"]["properties"]
        assert "output_path" in definition["inputSchema"]["properties"]
        assert "module_path" in definition["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_generate_tests_success(self, tool: TestGenerationTool, sample_python_file: str) -> None:
        """Should generate tests successfully."""
        result = await tool.execute({"file_path": sample_python_file})

        assert result["success"] is True
        assert "output_file" in result
        assert result["functions_analyzed"] == 3  # async function skipped
        assert result["total_tests_generated"] > 0

    @pytest.mark.asyncio
    async def test_generate_tests_with_custom_output(self, tool: TestGenerationTool, sample_python_file: str, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should generate tests to custom output path."""
        output_path = f"{temp_dir.name}/custom_test.py"

        result = await tool.execute({
            "file_path": sample_python_file,
            "output_path": output_path,
        })

        assert result["success"] is True
        assert result["output_file"] == output_path
        assert Path(output_path).exists()

    @pytest.mark.asyncio
    async def test_generate_tests_with_module_path(self, tool: TestGenerationTool, sample_python_file: str, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should use custom module path for imports."""
        output_path = f"{temp_dir.name}/test_module.py"

        result = await tool.execute({
            "file_path": sample_python_file,
            "module_path": "mymodule.calculator",
            "output_path": output_path,
        })

        assert result["success"] is True
        assert result["module_path"] == "mymodule.calculator"

    @pytest.mark.asyncio
    async def test_generate_tests_file_not_found(self, tool: TestGenerationTool) -> None:
        """Should handle file not found error."""
        result = await tool.execute({"file_path": "nonexistent.py"})

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_generate_tests_no_functions(self, tool: TestGenerationTool, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should handle files with no functions."""
        file_path = f"{temp_dir.name}/empty.py"
        with open(file_path, "w") as f:
            f.write("# Just a comment\n")

        result = await tool.execute({"file_path": file_path})

        assert result["success"] is False
        assert "No functions found" in result["error"]

    @pytest.mark.asyncio
    async def test_function_summaries(self, tool: TestGenerationTool, sample_python_file: str) -> None:
        """Should include function summaries in result."""
        result = await tool.execute({"file_path": sample_python_file})

        assert result["success"] is True
        assert "function_summaries" in result

        summaries = result["function_summaries"]
        assert len(summaries) == 3

        # Check first function summary
        add_summary = next((s for s in summaries if s["name"] == "add"), None)
        assert add_summary is not None
        assert add_summary["parameters"] == 2
        assert add_summary["complexity"] == 1
        assert add_summary["has_exceptions"] is False

    @pytest.mark.asyncio
    async def test_skips_async_functions(self, tool: TestGenerationTool, sample_python_file: str) -> None:
        """Should skip async functions."""
        result = await tool.execute({"file_path": sample_python_file})

        assert result["success"] is True
        assert result["functions_analyzed"] == 3  # Only 3 functions, async skipped

        # Check that async_function is not in summaries
        summaries = result["function_summaries"]
        async_summary = next((s for s in summaries if s["name"] == "async_function"), None)
        assert async_summary is None

    @pytest.mark.asyncio
    async def test_includes_exception_tests(self, tool: TestGenerationTool, sample_python_file: str) -> None:
        """Should generate exception tests for functions that raise."""
        result = await tool.execute({"file_path": sample_python_file})

        assert result["success"] is True

        # Find divide function summary
        divide_summary = next((s for s in result["function_summaries"] if s["name"] == "divide"), None)
        assert divide_summary is not None
        assert divide_summary["has_exceptions"] is True

    def test_get_test_examples(self, tool: TestGenerationTool) -> None:
        """Should return test examples."""
        examples = tool.get_test_examples()

        assert len(examples) > 0
        assert "description" in examples[0]
        assert "input" in examples[0]
        assert "output" in examples[0]

    @pytest.mark.asyncio
    async def test_invalid_file_extension(self, tool: TestGenerationTool, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should reject non-Python files."""
        file_path = f"{temp_dir.name}/test.txt"
        with open(file_path, "w") as f:
            f.write("Not a Python file")

        result = await tool.execute({"file_path": file_path})

        assert result["success"] is False
        assert "not a python file" in result["error"]


@pytest.fixture
def temp_dir() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary directory for testing."""
    return tempfile.TemporaryDirectory()
