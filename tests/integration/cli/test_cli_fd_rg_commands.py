#!/usr/bin/env python3
"""
Unit tests for newly added fd/rg CLI commands.

These tests monkeypatch the underlying MCP tools to avoid requiring
actual fd/rg binaries and focus on argument mapping and outputs.
"""

import contextlib
import sys
from io import StringIO

import pytest


@pytest.mark.unit
def test_list_files_cli_basic(monkeypatch, tmp_path):
    from tree_sitter_analyzer.cli.commands import list_files_cli

    async def fake_execute(self, arguments):  # noqa: ANN001
        assert arguments["roots"] == [str(tmp_path)]
        return {"success": True, "count": 0, "results": []}

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.ListFilesTool.execute",
        fake_execute,
        raising=True,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "list-files",
            str(tmp_path),
            "--output-format",
            "json",
        ],
    )
    stdout = StringIO()
    monkeypatch.setattr("sys.stdout", stdout)

    with contextlib.suppress(SystemExit):
        list_files_cli.main()

    out = stdout.getvalue()
    assert '"success": true' in out.lower()


@pytest.mark.skip(
    reason="search_content (SearchContentTool) is deprecated and removed. "
    "Text search is now done via CC built-in Grep tool."
)
@pytest.mark.unit
def test_search_content_cli_total_only(monkeypatch, tmp_path):
    pass  # deprecated — search_content_cli module deleted


@pytest.mark.skip(
    reason="find_and_grep (FindAndGrepTool) is deprecated and removed. "
    "Use CC Glob + Grep tools instead."
)
@pytest.mark.unit
def test_find_and_grep_cli_count_only(monkeypatch, tmp_path):
    pass  # deprecated — find_and_grep_cli module deleted
