"""Tests for Speculative Generality MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.speculative_generality_tool import (
    SpeculativeGeneralityTool,
)


@pytest.fixture
def tool() -> SpeculativeGeneralityTool:
    return SpeculativeGeneralityTool()


@pytest.fixture
def abstract_python_file() -> str:
    code = '''\
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

    @abstractmethod
    def perimeter(self) -> float:
        pass
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        return f.name


@pytest.fixture
def clean_python_file() -> str:
    code = '''\
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

class Circle(Shape):
    def area(self) -> float:
        return 3.14

class Square(Shape):
    def area(self) -> float:
        return 4.0
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        return f.name


class TestSpeculativeGeneralityToolDefinition:
    def test_get_tool_definition(self, tool: SpeculativeGeneralityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "speculative_generality"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_arguments_valid(self, tool: SpeculativeGeneralityTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_validate_arguments_missing_path(self, tool: SpeculativeGeneralityTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_validate_arguments_invalid_format(self, tool: SpeculativeGeneralityTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


class TestSpeculativeGeneralityToolExecute:
    @pytest.mark.asyncio
    async def test_execute_finds_issues(
        self,
        tool: SpeculativeGeneralityTool,
        abstract_python_file: str,
    ) -> None:
        result = await tool.execute(
            {"file_path": abstract_python_file, "format": "json"}
        )
        assert result["issue_count"] > 0
        assert any(
            i["issue_type"] == "speculative_abstract_class"
            for i in result["issues"]
        )

    @pytest.mark.asyncio
    async def test_execute_clean_file(
        self,
        tool: SpeculativeGeneralityTool,
        clean_python_file: str,
    ) -> None:
        result = await tool.execute({"file_path": clean_python_file})
        assert result["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_json_format(
        self,
        tool: SpeculativeGeneralityTool,
        abstract_python_file: str,
    ) -> None:
        result = await tool.execute(
            {"file_path": abstract_python_file, "format": "json"}
        )
        assert "file" in result
        assert "issues" in result
        assert isinstance(result["issues"], list)

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self,
        tool: SpeculativeGeneralityTool,
        abstract_python_file: str,
    ) -> None:
        result = await tool.execute(
            {"file_path": abstract_python_file, "format": "toon"}
        )
        assert "content" in result
        assert "total_types" in result

    @pytest.mark.asyncio
    async def test_execute_missing_path(self, tool: SpeculativeGeneralityTool) -> None:
        result = await tool.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_custom_threshold(
        self,
        tool: SpeculativeGeneralityTool,
        abstract_python_file: str,
    ) -> None:
        result = await tool.execute(
            {"file_path": abstract_python_file, "broad_threshold": 1}
        )
        # With threshold 1, 2 abstract methods triggers overly_broad
        assert result["issue_count"] > 0
