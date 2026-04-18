"""Integration tests for Inheritance Quality MCP Tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.inheritance_quality_tool import (
    InheritanceQualityTool,
)


@pytest.fixture
def tool() -> InheritanceQualityTool:
    return InheritanceQualityTool()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestInheritanceQualityToolDefinition:
    def test_tool_name(self, tool: InheritanceQualityTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "inheritance_quality"

    def test_tool_has_description(self, tool: InheritanceQualityTool) -> None:
        defn = tool.get_tool_definition()
        assert len(defn["description"]) > 50

    def test_tool_has_input_schema(self, tool: InheritanceQualityTool) -> None:
        defn = tool.get_tool_definition()
        assert "inputSchema" in defn
        props = defn["inputSchema"]["properties"]
        assert "file_path" in props
        assert "format" in props
        assert "depth_threshold" in props


class TestInheritanceQualityToolValidation:
    def test_valid_arguments(self, tool: InheritanceQualityTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"}) is True

    def test_missing_file_path(self, tool: InheritanceQualityTool) -> None:
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_invalid_format(self, tool: InheritanceQualityTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


class TestInheritanceQualityToolExecution:
    @pytest.mark.asyncio
    async def test_execute_json_format(self, tool: InheritanceQualityTool) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n\n"
            "class C(B):\n    pass\n\n"
            "class D(C):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "json",
            })
            assert "total_classes" in result
            assert result["total_classes"] == 4
            assert "issues" in result
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_toon_format(self, tool: InheritanceQualityTool) -> None:
        code = "class Foo:\n    pass\n"
        path = _write_tmp(code)
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "toon",
            })
            assert "content" in result
            assert result["total_classes"] == 1
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self, tool: InheritanceQualityTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, tool: InheritanceQualityTool) -> None:
        result = await tool.execute({
            "file_path": "/nonexistent/file.py",
            "format": "json",
        })
        assert result["total_classes"] == 0

    @pytest.mark.asyncio
    async def test_execute_custom_threshold(self, tool: InheritanceQualityTool) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n\n"
            "class C(B):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "json",
                "depth_threshold": 2,
            })
            deep = [
                i for i in result.get("issues", [])
                if i["type"] == "deep_inheritance"
            ]
            assert len(deep) >= 1
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_js_file(self, tool: InheritanceQualityTool) -> None:
        code = (
            "class Base {}\n\n"
            "class Child extends Base {\n"
            "    constructor() {\n"
            "        super();\n"
            "    }\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".js")
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "json",
            })
            assert result["total_classes"] == 2
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_execute_toon_shows_classes(self, tool: InheritanceQualityTool) -> None:
        code = (
            "class A:\n    pass\n\n"
            "class B(A):\n    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = await tool.execute({
                "file_path": path,
                "format": "toon",
            })
            assert result["total_classes"] == 2
            assert result["total_issues"] == 0
        finally:
            Path(path).unlink()
