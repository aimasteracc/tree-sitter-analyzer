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


@pytest.mark.unit
def test_search_content_cli_total_only(monkeypatch, tmp_path):
    from tree_sitter_analyzer.cli.commands import search_content_cli

    async def fake_execute(self, arguments):  # noqa: ANN001
        assert arguments["query"] == "TODO"
        assert arguments.get("total_only") is True
        return 42

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.SearchContentTool.execute",
        fake_execute,
        raising=True,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "search-content",
            "--roots",
            str(tmp_path),
            "--query",
            "TODO",
            "--total-only",
            "--output-format",
            "json",
        ],
    )
    stdout = StringIO()
    monkeypatch.setattr("sys.stdout", stdout)

    with contextlib.suppress(SystemExit):
        search_content_cli.main()

    out = stdout.getvalue().strip()
    # total_only prints a number via output_data -> json
    assert out == "42"


@pytest.mark.unit
def test_find_and_grep_cli_count_only(monkeypatch, tmp_path):
    from tree_sitter_analyzer.cli.commands import find_and_grep_cli

    async def fake_execute(self, arguments):  # noqa: ANN001
        assert arguments["roots"] == [str(tmp_path)]
        assert arguments["query"] == "import"
        assert arguments.get("count_only_matches") is True
        return {
            "success": True,
            "count_only": True,
            "total_matches": 10,
            "file_counts": {str(tmp_path / "a.py"): 5},
        }

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.FindAndGrepTool.execute",
        fake_execute,
        raising=True,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "find-and-grep",
            "--roots",
            str(tmp_path),
            "--query",
            "import",
            "--count-only-matches",
            "--output-format",
            "json",
        ],
    )
    stdout = StringIO()
    monkeypatch.setattr("sys.stdout", stdout)

    with contextlib.suppress(SystemExit):
        find_and_grep_cli.main()

    out = stdout.getvalue().lower()
    assert '"count_only": true' in out
    assert '"total_matches": 10' in out
