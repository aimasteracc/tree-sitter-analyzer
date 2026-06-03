#!/usr/bin/env python3
"""
Tests for query_code include_body parameter.

Verifies that include_body=true attaches the symbol's source code to each
definition result, eliminating a follow-up read_partial call.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.query_symbol_search import _read_lines


class TestReadLines:
    """Unit tests for the _read_lines helper."""

    def test_reads_requested_range(self, tmp_path: Path) -> None:
        fp = tmp_path / "f.py"
        fp.write_text("line1\nline2\nline3\nline4\nline5\n")
        assert _read_lines(fp, 2, 4) == "line2\nline3\nline4"

    def test_returns_empty_on_missing_file(self, tmp_path: Path) -> None:
        assert _read_lines(tmp_path / "missing.py", 1, 5) == ""

    def test_clamps_to_file_length(self, tmp_path: Path) -> None:
        fp = tmp_path / "short.py"
        fp.write_text("a\nb\n")
        result = _read_lines(fp, 1, 100)
        assert "a" in result
        assert "b" in result

    def test_truncates_at_max_lines(self, tmp_path: Path) -> None:
        fp = tmp_path / "big.py"
        fp.write_text("\n".join(f"line{i}" for i in range(300)) + "\n")
        result = _read_lines(fp, 1, 300)
        assert "more lines" in result

    def test_single_line(self, tmp_path: Path) -> None:
        fp = tmp_path / "one.py"
        fp.write_text("def foo(): pass\n")
        assert _read_lines(fp, 1, 1) == "def foo(): pass"


class TestIncludeBodyParameter:
    """Integration tests for include_body via QueryTool.execute."""

    @pytest.fixture
    def project_with_python(self, tmp_path: Path) -> Path:
        src = tmp_path / "src.py"
        src.write_text(
            "def greet(name: str) -> str:\n"
            "    return f'Hello, {name}'\n"
            "\n"
            "class Greeter:\n"
            "    def hello(self) -> str:\n"
            "        return greet('world')\n"
        )
        return tmp_path

    @pytest.mark.asyncio
    async def test_include_body_adds_source(
        self, project_with_python: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        tool = QueryTool(str(project_with_python))
        result = await tool.execute(
            {"symbol": "greet", "include_body": True, "output_format": "json"}
        )
        assert result.get("success") is True
        definitions = result.get("definitions", [])
        assert definitions, "expected at least one definition"
        body = definitions[0].get("body", "")
        assert "greet" in body or "Hello" in body

    @pytest.mark.asyncio
    async def test_no_include_body_has_no_body_key(
        self, project_with_python: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        tool = QueryTool(str(project_with_python))
        result = await tool.execute(
            {"symbol": "greet", "include_body": False, "output_format": "json"}
        )
        definitions = result.get("definitions", [])
        if definitions:
            assert "body" not in definitions[0]

    @pytest.mark.asyncio
    async def test_workflow_hint_mentions_include_body_when_absent(
        self, project_with_python: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        tool = QueryTool(str(project_with_python))
        result = await tool.execute(
            {"symbol": "greet", "include_body": False, "output_format": "json"}
        )
        hint = result.get("smart_workflow_hint", "")
        assert "include_body" in hint
