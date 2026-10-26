"""#1810: input that is not analyzed gets a canonical verdict plus a reason.

``check_file_health`` and ``code_patterns`` used to answer ``verdict: 'N/A'``
for empty and non-code files, which is outside ``CANONICAL_VERDICTS``. They
now answer ``INFO`` with a ``verdict_reason`` code, and keep ``grade: 'N/A'``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.code_patterns_tool import CodePatternsTool
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
from tree_sitter_analyzer.mcp.tools.tool_response import envelope_violations


def _health(tmp_path: Path, name: str, content: str) -> dict:
    target = tmp_path / name
    target.write_text(content, encoding="utf-8")
    tool = FileHealthTool(project_root=str(tmp_path))
    return asyncio.run(
        tool.execute({"file_path": str(target), "output_format": "json"})
    )


@pytest.mark.parametrize("content", ["", "   \n\t\n"])
def test_empty_file_health_is_info_with_reason(tmp_path: Path, content: str) -> None:
    result = _health(tmp_path, "empty.py", content)

    assert result["grade"] == "N/A"
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["verdict"] == "INFO"
    assert result["verdict_reason"] == "EMPTY_FILE"
    assert envelope_violations(result) == []


def test_non_code_file_health_is_info_with_reason(tmp_path: Path) -> None:
    result = _health(tmp_path, "README.md", "# Title\n\nSome prose.\n")

    assert result["grade"] == "N/A"
    assert result["signal"] == "non_code_file"
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["verdict"] == "INFO"
    assert result["verdict_reason"] == "NON_CODE_FILE"
    assert envelope_violations(result) == []


def test_empty_file_code_patterns_is_info_with_reason(tmp_path: Path) -> None:
    target = tmp_path / "empty.py"
    target.write_text("", encoding="utf-8")
    tool = CodePatternsTool(project_root=str(tmp_path))

    result = asyncio.run(
        tool.execute({"file_path": str(target), "output_format": "json"})
    )

    assert result["signal"] == "empty_file"
    assert result["verdict"] == "INFO"
    assert result["agent_summary"]["verdict"] == "INFO"
    assert result["verdict_reason"] == "EMPTY_FILE"
    assert envelope_violations(result) == []
