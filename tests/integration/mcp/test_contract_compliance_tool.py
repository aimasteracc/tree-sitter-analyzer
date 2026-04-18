"""Tests for Contract Compliance MCP Tool."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.contract_compliance_tool import (
    ContractComplianceTool,
)


@pytest.fixture
def tool() -> ContractComplianceTool:
    return ContractComplianceTool()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


@pytest.mark.asyncio
async def test_tool_definition(tool: ContractComplianceTool) -> None:
    defn = tool.get_tool_definition()
    assert defn["name"] == "contract_compliance"
    assert "file_path" in defn["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_json_format(tool: ContractComplianceTool) -> None:
    path = _write_tmp('def get_name() -> str:\n    return None\n', ".py")
    result = await tool.execute({"file_path": path, "format": "json"})
    assert "issues" in result
    assert result["language"] == "python"
    assert result["total_issues"] >= 1


@pytest.mark.asyncio
async def test_text_format(tool: ContractComplianceTool) -> None:
    path = _write_tmp('def get_name() -> str:\n    return None\n', ".py")
    result = await tool.execute({"file_path": path, "format": "text"})
    assert "content" in result
    assert "return_type_violation" in result["content"] or "None" in result["content"]


@pytest.mark.asyncio
async def test_toon_format(tool: ContractComplianceTool) -> None:
    path = _write_tmp('def get_name() -> str:\n    return None\n', ".py")
    result = await tool.execute({"file_path": path, "format": "toon"})
    assert "content" in result


@pytest.mark.asyncio
async def test_severity_filter(tool: ContractComplianceTool) -> None:
    path = _write_tmp(
        'def get_name() -> str:\n'
        '    return None\n'
        'def greet(name: str) -> str:\n'
        '    return name * 3\n',
        ".py",
    )
    result = await tool.execute({"file_path": path, "format": "json", "severity": "high"})
    for issue in result["issues"]:
        assert issue["severity"] == "high"


@pytest.mark.asyncio
async def test_no_file_path(tool: ContractComplianceTool) -> None:
    result = await tool.execute({"format": "json"})
    assert "error" in result


@pytest.mark.asyncio
async def test_validate_arguments_ok(tool: ContractComplianceTool) -> None:
    assert tool.validate_arguments({"file_path": "/tmp/test.py", "format": "json"}) is True


@pytest.mark.asyncio
async def test_validate_arguments_bad_format(tool: ContractComplianceTool) -> None:
    with pytest.raises(ValueError):
        tool.validate_arguments({"file_path": "/tmp/test.py", "format": "xml"})


@pytest.mark.asyncio
async def test_validate_arguments_bad_severity(tool: ContractComplianceTool) -> None:
    with pytest.raises(ValueError):
        tool.validate_arguments({"file_path": "/tmp/test.py", "format": "json", "severity": "critical"})


@pytest.mark.asyncio
async def test_validate_arguments_no_file(tool: ContractComplianceTool) -> None:
    with pytest.raises(ValueError):
        tool.validate_arguments({"format": "json"})
