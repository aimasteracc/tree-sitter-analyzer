"""Tests for Parameter Coupling MCP Tool."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.parameter_coupling_tool import ParameterCouplingTool


def _write_temp(content: str, suffix: str = ".py") -> Path:
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / f"test_file{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def tool() -> ParameterCouplingTool:
    return ParameterCouplingTool()


class TestParameterCouplingToolDefinition:
    def test_tool_definition_has_name(self, tool: ParameterCouplingTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "parameter_coupling"

    def test_tool_definition_has_input_schema(self, tool: ParameterCouplingTool) -> None:
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "file_path" in properties
        assert "project_root" in properties
        assert "max_params" in properties
        assert "min_clump_size" in properties
        assert "format" in properties


class TestParameterCouplingToolExecution:
    @pytest.mark.asyncio
    async def test_analyze_file_json(self, tool: ParameterCouplingTool) -> None:
        path = _write_temp("def foo(a, b, c, d, e, f, g): pass\n")
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
        })
        assert result["total_functions"] == 1
        assert result["total_parameters"] == 7
        assert len(result["high_param_functions"]) == 1
        assert result["high_param_functions"][0]["param_count"] == 7

    @pytest.mark.asyncio
    async def test_analyze_file_toon(self, tool: ParameterCouplingTool) -> None:
        path = _write_temp("def foo(a, b): pass\n")
        result = await tool.execute({
            "file_path": str(path),
            "format": "toon",
        })
        assert result["total_functions"] == 1
        assert result["total_parameters"] == 2
        assert "content" in result

    @pytest.mark.asyncio
    async def test_analyze_directory(self, tool: ParameterCouplingTool) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "test.py").write_text("def hello(x, y): pass\n", encoding="utf-8")
        result = await tool.execute({
            "project_root": str(tmpdir),
            "format": "json",
        })
        assert result["total_functions"] >= 1

    @pytest.mark.asyncio
    async def test_no_path_returns_error(self, tool: ParameterCouplingTool) -> None:
        result = await tool.execute({"format": "json"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_custom_max_params(self, tool: ParameterCouplingTool) -> None:
        path = _write_temp("def foo(a, b, c): pass\n")
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
            "max_params": 2,
        })
        assert len(result["high_param_functions"]) == 1

    @pytest.mark.asyncio
    async def test_data_clump_json(self, tool: ParameterCouplingTool) -> None:
        code = (
            "def process(user, config, logger, data): pass\n"
            "def validate(user, config, logger, schema): pass\n"
        )
        path = _write_temp(code)
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
            "min_clump_size": 3,
        })
        assert len(result["data_clumps"]) >= 1
        clump = result["data_clumps"][0]
        assert "user" in clump["shared_params"]
        assert "config" in clump["shared_params"]
        assert "logger" in clump["shared_params"]

    @pytest.mark.asyncio
    async def test_warnings_in_json(self, tool: ParameterCouplingTool) -> None:
        params = ", ".join(f"p{i}" for i in range(8))
        path = _write_temp(f"def big({params}): pass\n")
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
        })
        assert len(result["warnings"]) >= 1

    @pytest.mark.asyncio
    async def test_toon_no_issues(self, tool: ParameterCouplingTool) -> None:
        path = _write_temp("def simple(x): pass\n")
        result = await tool.execute({
            "file_path": str(path),
            "format": "toon",
        })
        assert result["high_param_count"] == 0
        assert result["data_clump_count"] == 0

    @pytest.mark.asyncio
    async def test_js_file_analysis(self, tool: ParameterCouplingTool) -> None:
        code = "function process(user, config, logger, data, opts) { return 1; }\n"
        path = _write_temp(code, suffix=".js")
        result = await tool.execute({
            "file_path": str(path),
            "format": "json",
        })
        assert result["total_functions"] >= 1


class TestParameterCouplingToolValidation:
    def test_valid_arguments(self, tool: ParameterCouplingTool) -> None:
        assert tool.validate_arguments({"file_path": "/tmp/test.py"})

    def test_invalid_format(self, tool: ParameterCouplingTool) -> None:
        with pytest.raises(ValueError, match="format"):
            tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})

    def test_missing_path(self, tool: ParameterCouplingTool) -> None:
        with pytest.raises(ValueError, match="file_path or project_root"):
            tool.validate_arguments({"format": "toon"})
