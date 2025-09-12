import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.mark.unit
def test_list_files_validation_requires_roots(tmp_path):
    """Test that ListFilesTool validation fails when roots parameter is missing."""
    tool = ListFilesTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments({})


@pytest.mark.unit
def test_search_content_validation_requires_query():
    """Test that SearchContentTool validation fails when query parameter is missing."""
    tool = SearchContentTool(str(Path.cwd()))
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": [str(Path.cwd())]})


@pytest.mark.unit
def test_find_and_grep_validation_requires_roots_and_query(tmp_path):
    """Test that FindAndGrepTool validation fails when either roots or query parameter is missing."""
    tool = FindAndGrepTool(str(tmp_path))
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": [str(tmp_path)]})
    with pytest.raises(ValueError):
        tool.validate_arguments({"query": "foo"})


class DummyProc:
    def __init__(self, rc=0, stdout=b"", stderr=b""):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_exec_happy_path(monkeypatch, tmp_path):
    """Test successful execution of ListFilesTool with file extension filtering."""
    tool = ListFilesTool(str(tmp_path))
    # Create files
    f1 = tmp_path / "a.py"
    f1.write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "b").mkdir()

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # fd will list both entries, one per line
        out = f"{f1}\n{tmp_path / 'b'}\n".encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "extensions": ["py"]})
    assert result["success"] is True
    assert result["count"] >= 1
    assert any(x["path"].endswith("a.py") for x in result["results"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_exec_files_list(monkeypatch, tmp_path):
    """Test SearchContentTool execution with explicit file list and query matching."""
    tool = SearchContentTool(str(tmp_path))
    f1 = tmp_path / "a.txt"
    f1.write_text("hello world\nhello ai\n", encoding="utf-8")

    # ripgrep JSON match event for line 1
    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f1)},
            "lines": {"text": "hello world\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "hello"}, "start": 0, "end": 5}],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "rg":
            out = (json.dumps(rg_json) + "\n").encode()
            return 0, out, b""
        return 0, str(f1).encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"files": [str(f1)], "query": "hello"})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["line_number"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_exec_composed(monkeypatch, tmp_path):
    """Test FindAndGrepTool execution combining file discovery (fd) and content search (rg)."""
    tool = FindAndGrepTool(str(tmp_path))
    f1 = tmp_path / "a.txt"
    f1.write_text("hello\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f1)},
            "lines": {"text": "hello\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "hello"}, "start": 0, "end": 5}],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "fd":
            return 0, f"{f1}\n".encode(), b""
        if cmd and cmd[0] == "rg":
            return 0, (json.dumps(rg_json) + "\n").encode(), b""
        return 1, b"", b"bad cmd"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "a.txt",
            "query": "hello",
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["meta"]["searched_file_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_exclude(monkeypatch, tmp_path):
    """Test ListFilesTool with exclude patterns to filter out specific directories."""
    tool = ListFilesTool(str(tmp_path))
    # Create files
    f1 = tmp_path / "a.py"
    f1.write_text("print('a')\n", encoding="utf-8")
    d1 = tmp_path / "excluded"
    d1.mkdir()
    f2 = d1 / "b.py"
    f2.write_text("print('b')\n", encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # fd will list only a.py, excluding the 'excluded' dir
        out = f"{f1}\n".encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "glob": True,
            "pattern": "*.py",
            "exclude": ["excluded/"],
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert any(x["path"].endswith("a.py") for x in result["results"])
    assert not any(x["path"].endswith("b.py") for x in result["results"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_globs(monkeypatch, tmp_path):
    """Test SearchContentTool with include and exclude glob patterns for file filtering."""
    tool = SearchContentTool(str(tmp_path))
    f1 = tmp_path / "a.py"
    f1.write_text("import os\n", encoding="utf-8")
    f2 = tmp_path / "b_test.py"
    f2.write_text("import sys\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f1)},
            "lines": {"text": "import os\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "import"}, "start": 0, "end": 6}],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        out = (json.dumps(rg_json) + "\n").encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "import",
            "include_globs": ["*.py"],
            "exclude_globs": ["*_test.py"],
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(f1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_multiline_case_insensitive(monkeypatch, tmp_path):
    """Test FindAndGrepTool with multiline regex patterns and case-insensitive matching."""
    tool = FindAndGrepTool(str(tmp_path))
    f1 = tmp_path / "a.py"
    f1.write_text('class MyClass:\n    """docstring"""\n', encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(f1)},
            "lines": {"text": 'class MyClass:\n    """docstring"""\n'},
            "line_number": 1,
            "submatches": [
                {
                    "match": {"text": 'class MyClass:\n    """docstring"""'},
                    "start": 0,
                    "end": 35,
                }
            ],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "fd":
            return 0, f"{f1}\n".encode(), b""
        if cmd and cmd[0] == "rg":
            out = (json.dumps(rg_json) + "\n").encode()
            return 0, out, b""
        return 1, b"", b"bad cmd"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*.py",
            "glob": True,
            "query": 'class \\w+\\([^\\)]*\\):\\n    """[^"]*"""',
            "case": "insensitive",
            "multiline": True,
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["line_number"] == 1


@pytest.mark.unit
def test_parse_rg_count_output():
    """Test parsing ripgrep --count-matches output."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import parse_rg_count_output

    # Mock count output
    count_output = b"""file1.py:5
file2.py:3
file3.py:0
file4.py:12
"""

    result = parse_rg_count_output(count_output)

    assert result["file1.py"] == 5
    assert result["file2.py"] == 3
    assert result["file3.py"] == 0
    assert result["file4.py"] == 12
    assert result["__total__"] == 20  # 5 + 3 + 0 + 12


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_count_only_matches(monkeypatch, tmp_path):
    """Test search_content tool with count_only_matches option."""
    tool = SearchContentTool(str(tmp_path))

    # Mock count output
    mock_count_output = b"""file1.py:5
file2.py:3
file4.py:12
"""

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify --count-matches is in command
        assert "--count-matches" in cmd
        return 0, mock_count_output, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "import", "count_only_matches": True}
    )

    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_matches"] == 20
    assert result["file_counts"]["file1.py"] == 5
    assert result["file_counts"]["file2.py"] == 3
    assert result["file_counts"]["file4.py"] == 12
    assert "elapsed_ms" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_count_only_matches(monkeypatch, tmp_path):
    """Test find_and_grep tool with count_only_matches option."""
    tool = FindAndGrepTool(str(tmp_path))

    # Mock fd output (file list)
    mock_fd_output = b"""file1.py
file2.py
file4.py
"""

    # Mock rg count output
    mock_rg_count_output = b"""file1.py:5
file2.py:3
file4.py:12
"""

    call_count = 0

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        nonlocal call_count
        call_count += 1

        if call_count == 1:  # fd command
            assert "fd" in cmd[0]
            return 0, mock_fd_output, b""
        else:  # rg command
            assert "--count-matches" in cmd
            return 0, mock_rg_count_output, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "import", "count_only_matches": True}
    )

    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_matches"] == 20
    assert result["file_counts"]["file1.py"] == 5
    assert result["file_counts"]["file2.py"] == 3
    assert result["file_counts"]["file4.py"] == 12
    assert result["meta"]["searched_file_count"] == 3
    assert "fd_elapsed_ms" in result["meta"]
    assert "rg_elapsed_ms" in result["meta"]


@pytest.mark.unit
def test_build_rg_command_with_count_only():
    """Test building ripgrep command with count_only_matches option."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_rg_command

    # Test with count_only_matches=True
    cmd = build_rg_command(
        query="test",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=["/test"],
        files_from=None,
        count_only_matches=True,
    )

    assert "--count-matches" in cmd
    assert "--json" not in cmd
    assert "test" in cmd
    assert "/test" in cmd

    # Test with count_only_matches=False (default)
    cmd = build_rg_command(
        query="test",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=["/test"],
        files_from=None,
        count_only_matches=False,
    )

    assert "--json" in cmd
    assert "--count-matches" not in cmd
    assert "test" in cmd
    assert "/test" in cmd


@pytest.mark.unit
def test_summarize_search_results():
    """Test summarizing search results for context reduction."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import summarize_search_results
    
    # Mock search results
    matches = [
        {"file": "file1.py", "line_number": 10, "line": "import os"},
        {"file": "file1.py", "line_number": 20, "line": "import sys"},
        {"file": "file1.py", "line_number": 30, "line": "import json"},
        {"file": "file2.py", "line_number": 5, "line": "import re"},
        {"file": "file2.py", "line_number": 15, "line": "import time"},
        {"file": "file3.py", "line_number": 1, "line": "import logging"},
    ]
    
    summary = summarize_search_results(matches, max_files=2, max_total_lines=4)
    
    assert summary["total_matches"] == 6
    assert summary["total_files"] == 3
    assert summary["truncated"] is True  # 3 files > max_files=2
    assert len(summary["top_files"]) == 2
    
    # file1.py should be first (3 matches)
    assert summary["top_files"][0]["file"] == "file1.py"
    assert summary["top_files"][0]["match_count"] == 3
    assert len(summary["top_files"][0]["sample_lines"]) == 3
    
    # file2.py should be second (2 matches)
    assert summary["top_files"][1]["file"] == "file2.py"
    assert summary["top_files"][1]["match_count"] == 2
    assert len(summary["top_files"][1]["sample_lines"]) == 1  # limited by max_total_lines


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_count_only(monkeypatch, tmp_path):
    """Test list_files tool with count_only option."""
    tool = ListFilesTool(str(tmp_path))
    
    # Mock fd output
    mock_fd_output = b"""file1.py
file2.py
file3.py
file4.py
file5.py
"""
    
    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, mock_fd_output, b""
    
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )
    
    result = await tool.execute({
        "roots": [str(tmp_path)],
        "count_only": True
    })
    
    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_count"] == 5
    assert "results" not in result  # No detailed results in count_only mode
    assert "elapsed_ms" in result
