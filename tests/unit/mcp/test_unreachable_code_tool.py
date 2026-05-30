"""Tests for UnreachableCodeTool MCP wrapper.

Covers validate_arguments, execute, file/project response builders,
format_block_line, and _resolve_path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.unreachable_code_tool import UnreachableCodeTool
from tree_sitter_analyzer.unreachable_code import (
    UnreachableBlock,
    UnreachableCodeResult,
)


def _make_block(
    start: int = 10,
    end: int = 12,
    fn: str = "my_func",
    reason: str = "after return",
    severity: str = "warning",
) -> UnreachableBlock:
    b = MagicMock(spec=UnreachableBlock)
    b.start_line = start
    b.end_line = end
    b.function_name = fn
    b.reason = reason
    b.severity = severity
    return b


def _make_result(
    file_path: str = "src/foo.py",
    language: str = "python",
    blocks: list[Any] | None = None,
    functions_analyzed: int = 5,
    errors: list[str] | None = None,
) -> UnreachableCodeResult:
    r = MagicMock(spec=UnreachableCodeResult)
    r.file_path = file_path
    r.language = language
    r.unreachable_blocks = blocks or []
    r.functions_analyzed = functions_analyzed
    r.errors = errors or []
    r.to_dict.return_value = {
        "file_path": file_path,
        "unreachable_blocks": [],
    }
    return r


@pytest.fixture
def tool() -> UnreachableCodeTool:
    return UnreachableCodeTool(project_root="/fake/root")


# ---------------------------------------------------------------------------
# get_tool_definition / get_tool_name / get_tool_schema
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_get_tool_name(self, tool: UnreachableCodeTool) -> None:
        assert tool.get_tool_name() == "unreachable_code"

    def test_get_tool_definition_has_name(self, tool: UnreachableCodeTool) -> None:
        d = tool.get_tool_definition()
        assert d["name"] == "unreachable_code"
        assert "description" in d

    def test_get_tool_schema_has_mode(self, tool: UnreachableCodeTool) -> None:
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "file_path" in schema["properties"]


# ---------------------------------------------------------------------------
# validate_arguments
# ---------------------------------------------------------------------------


class TestValidateArguments:
    def test_valid_file_mode_with_path(self, tool: UnreachableCodeTool) -> None:
        assert tool.validate_arguments({"mode": "file", "file_path": "src/x.py"})

    def test_valid_project_mode(self, tool: UnreachableCodeTool) -> None:
        assert tool.validate_arguments({"mode": "project"})

    def test_file_mode_missing_path_raises(self, tool: UnreachableCodeTool) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "file"})

    def test_invalid_mode_raises(self, tool: UnreachableCodeTool) -> None:
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "batch"})


# ---------------------------------------------------------------------------
# _format_block_line (static helper)
# ---------------------------------------------------------------------------


class TestFormatBlockLine:
    def test_formats_correctly(self, tool: UnreachableCodeTool) -> None:
        block = _make_block(
            start=10, end=12, fn="process", reason="after return", severity="warning"
        )
        line = tool._format_block_line(block)
        assert "L10-12" in line
        assert "process" in line
        assert "after return" in line
        assert "[warning]" in line


# ---------------------------------------------------------------------------
# _build_file_response
# ---------------------------------------------------------------------------


class TestBuildFileResponse:
    def test_toon_format_no_blocks(self, tool: UnreachableCodeTool) -> None:
        result = _make_result(blocks=[])
        resp = tool._build_file_response(result, "toon")
        assert "content" in resp or "toon_content" in resp

    def test_toon_format_with_blocks(self, tool: UnreachableCodeTool) -> None:
        block = _make_block()
        result = _make_result(blocks=[block])
        resp = tool._build_file_response(result, "toon")
        content = resp.get("content") or resp.get("toon_content", "")
        assert "L10-12" in content

    def test_toon_format_with_errors(self, tool: UnreachableCodeTool) -> None:
        result = _make_result(errors=["parse error at line 5"])
        resp = tool._build_file_response(result, "toon")
        content = resp.get("content") or resp.get("toon_content", "")
        assert "Parse errors" in content

    def test_json_format_returns_dict(self, tool: UnreachableCodeTool) -> None:
        result = _make_result()
        resp = tool._build_file_response(result, "json")
        assert isinstance(resp, dict)
        assert "file_path" in resp

    def test_toon_says_no_unreachable_when_empty(
        self, tool: UnreachableCodeTool
    ) -> None:
        result = _make_result(blocks=[])
        resp = tool._build_file_response(result, "toon")
        content = resp.get("content") or resp.get("toon_content", "")
        assert "No unreachable code detected" in content


# ---------------------------------------------------------------------------
# _format_file_blocks_toon
# ---------------------------------------------------------------------------


class TestFormatFileBlocksToon:
    def test_returns_empty_for_no_blocks(self, tool: UnreachableCodeTool) -> None:
        result = _make_result(blocks=[])
        assert tool._format_file_blocks_toon(result) == []

    def test_returns_header_and_block_lines(self, tool: UnreachableCodeTool) -> None:
        block = _make_block(start=5, end=7, fn="do_thing")
        result = _make_result(file_path="src/bar.py", language="python", blocks=[block])
        lines = tool._format_file_blocks_toon(result)
        assert any("src/bar.py" in line for line in lines)
        assert any("L5-7" in line for line in lines)


# ---------------------------------------------------------------------------
# _build_project_response
# ---------------------------------------------------------------------------


class TestBuildProjectResponse:
    def test_toon_format_empty_results(self, tool: UnreachableCodeTool) -> None:
        resp = tool._build_project_response([], "toon")
        content = resp.get("content") or resp.get("toon_content", "")
        assert "Project Scan" in content

    def test_toon_format_with_results(self, tool: UnreachableCodeTool) -> None:
        block = _make_block()
        r1 = _make_result(blocks=[block])
        r2 = _make_result(file_path="src/clean.py", blocks=[])
        resp = tool._build_project_response([r1, r2], "toon")
        content = resp.get("content") or resp.get("toon_content", "")
        assert "Files with issues: 1" in content

    def test_json_format_returns_counts(self, tool: UnreachableCodeTool) -> None:
        block = _make_block()
        r = _make_result(blocks=[block], functions_analyzed=3)
        resp = tool._build_project_response([r], "json")
        assert resp["files_with_issues"] == 1
        assert resp["total_functions_analyzed"] == 3
        assert resp["total_unreachable_blocks"] == 1


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_returns_absolute_path_when_file_exists(
        self, tmp_path, tool: UnreachableCodeTool
    ) -> None:
        f = tmp_path / "code.py"
        f.write_text("x = 1")
        assert tool._resolve_path(str(f)) == str(f)

    def test_resolves_relative_to_project_root(self, tmp_path) -> None:
        t = UnreachableCodeTool(project_root=str(tmp_path))
        f = tmp_path / "module.py"
        f.write_text("pass")
        result = t._resolve_path("module.py")
        assert result == str(f)

    def test_returns_none_when_not_found(self, tool: UnreachableCodeTool) -> None:
        assert tool._resolve_path("does_not_exist.py") is None


# ---------------------------------------------------------------------------
# execute() — integration paths via mocked analysis
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_file_mode_not_found_returns_error(
        self, tool: UnreachableCodeTool
    ) -> None:
        result = await tool.execute({"mode": "file", "file_path": "/no/such/file.py"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_file_mode_missing_path_raises(
        self, tool: UnreachableCodeTool
    ) -> None:
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({"mode": "file", "file_path": ""})

    @pytest.mark.asyncio
    async def test_file_mode_success_toon(self, tmp_path: Any) -> None:
        f = tmp_path / "x.py"
        f.write_text("def foo():\n    return 1\n    y = 2\n")
        t = UnreachableCodeTool(project_root=str(tmp_path))
        fake_result = _make_result(file_path=str(f))
        with patch(
            "tree_sitter_analyzer.mcp.tools.unreachable_code_tool.analyze_file_unreachable",
            return_value=fake_result,
        ):
            resp = await t.execute(
                {"mode": "file", "file_path": str(f), "output_format": "toon"}
            )
        assert "error" not in resp

    @pytest.mark.asyncio
    async def test_file_mode_analysis_error_returns_error(self, tmp_path: Any) -> None:
        f = tmp_path / "bad.py"
        f.write_text("x = 1")
        t = UnreachableCodeTool(project_root=str(tmp_path))
        with patch(
            "tree_sitter_analyzer.mcp.tools.unreachable_code_tool.analyze_file_unreachable",
            side_effect=RuntimeError("boom"),
        ):
            resp = await t.execute({"mode": "file", "file_path": str(f)})
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_project_mode_no_root_returns_error(self) -> None:
        t = UnreachableCodeTool()  # No project_root
        resp = await t.execute({"mode": "project"})
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_project_mode_success(self, tool: UnreachableCodeTool) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tools.unreachable_code_tool.analyze_project_unreachable",
            return_value=[_make_result()],
        ):
            resp = await tool.execute({"mode": "project", "output_format": "json"})
        assert "files_with_issues" in resp

    @pytest.mark.asyncio
    async def test_project_mode_error_returns_error(
        self, tool: UnreachableCodeTool
    ) -> None:
        with patch(
            "tree_sitter_analyzer.mcp.tools.unreachable_code_tool.analyze_project_unreachable",
            side_effect=RuntimeError("project scan error"),
        ):
            resp = await tool.execute({"mode": "project"})
        assert "error" in resp
