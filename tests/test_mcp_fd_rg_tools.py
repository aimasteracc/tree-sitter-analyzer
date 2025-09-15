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
    assert result["results"][0]["line"] == 1  # Updated field name


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
    assert result["results"][0]["line"] == 1


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
        {"file": "file1.py", "line": 10, "text": "import os"},
        {"file": "file1.py", "line": 20, "text": "import sys"},
        {"file": "file1.py", "line": 30, "text": "import json"},
        {"file": "file2.py", "line": 5, "text": "import re"},
        {"file": "file2.py", "line": 15, "text": "import time"},
        {"file": "file3.py", "line": 1, "text": "import logging"},
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
    assert (
        len(summary["top_files"][1]["sample_lines"]) == 1
    )  # limited by max_total_lines


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

    result = await tool.execute({"roots": [str(tmp_path)], "count_only": True})

    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_count"] == 5
    assert "results" not in result  # No detailed results in count_only mode
    assert "elapsed_ms" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_summary_only(monkeypatch, tmp_path):
    """Test search_content tool with summary_only option."""
    tool = SearchContentTool(str(tmp_path))

    # Mock search results
    rg_json1 = {
        "type": "match",
        "data": {
            "path": {"text": "file1.py"},
            "lines": {"text": "import os\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "import"}, "start": 0, "end": 6}],
        },
    }
    rg_json2 = {
        "type": "match",
        "data": {
            "path": {"text": "file1.py"},
            "lines": {"text": "import sys\n"},
            "line_number": 2,
            "submatches": [{"match": {"text": "import"}, "start": 0, "end": 6}],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify --json is in command (not --count-matches)
        assert "--json" in cmd
        assert "--count-matches" not in cmd
        out = (json.dumps(rg_json1) + "\n" + json.dumps(rg_json2) + "\n").encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "import", "summary_only": True}
    )

    assert result["success"] is True
    assert result["count"] == 2
    assert "summary" in result
    assert result["summary"]["total_matches"] == 2
    assert result["summary"]["total_files"] == 1
    assert len(result["summary"]["top_files"]) == 1
    assert result["summary"]["top_files"][0]["file"] == "file1.py"
    assert result["summary"]["top_files"][0]["match_count"] == 2
    assert "elapsed_ms" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_error_handling(monkeypatch, tmp_path):
    """Test ListFilesTool error handling when fd command fails."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 1, b"", b"fd: command failed"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)]})

    assert result["success"] is False
    assert result["error"] == "fd: command failed"
    assert result["returncode"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_error_handling(monkeypatch, tmp_path):
    """Test SearchContentTool error handling when ripgrep command fails."""
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 2, b"", b"rg: invalid regex"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "query": "[invalid"})

    assert result["success"] is False
    assert result["error"] == "rg: invalid regex"
    assert result["returncode"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_optimize_paths(monkeypatch, tmp_path):
    """Test FindAndGrepTool with path optimization enabled."""
    tool = FindAndGrepTool(str(tmp_path))

    # Create test files with long paths
    long_path = tmp_path / "very" / "long" / "nested" / "directory"
    long_path.mkdir(parents=True)
    f1 = long_path / "test.txt"
    f1.write_text("hello world\n", encoding="utf-8")

    # Mock fd output (file discovery)
    fd_output = str(f1).encode()

    # Mock ripgrep JSON output
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
        if cmd and cmd[0] == "fd":
            return 0, fd_output, b""
        elif cmd and cmd[0] == "rg":
            out = (json.dumps(rg_json) + "\n").encode()
            return 0, out, b""
        return 1, b"", b"Unknown command"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with path optimization enabled
    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "hello", "optimize_paths": True}
    )

    assert result["success"] is True
    assert result["count"] == 1

    # The optimized path should be shorter than the original
    original_path = str(f1)
    optimized_path = result["results"][0]["file"]
    assert len(optimized_path) <= len(original_path)
    # Should not contain abs_path field
    assert "abs_path" not in result["results"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_error_handling(monkeypatch, tmp_path):
    """Test FindAndGrepTool error handling when fd command fails."""
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "fd":
            return 1, b"", b"fd: permission denied"
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "query": "test"})

    assert result["success"] is False
    assert result["error"] == "fd: permission denied"
    assert result["returncode"] == 1


@pytest.mark.unit
def test_list_files_validation_invalid_types(tmp_path):
    """Test ListFilesTool validation with invalid parameter types."""
    tool = ListFilesTool(str(tmp_path))

    # Test invalid roots type
    with pytest.raises(ValueError, match="roots must be an array"):
        tool.validate_arguments({"roots": "not_a_list"})

    # Test invalid boolean parameters
    with pytest.raises(ValueError, match="glob must be a boolean"):
        tool.validate_arguments({"roots": [str(tmp_path)], "glob": "true"})

    # Test invalid integer parameters
    with pytest.raises(ValueError, match="depth must be an integer"):
        tool.validate_arguments({"roots": [str(tmp_path)], "depth": "5"})

    # Test invalid array parameters
    with pytest.raises(ValueError, match="extensions must be an array of strings"):
        tool.validate_arguments({"roots": [str(tmp_path)], "extensions": ["py", 123]})


@pytest.mark.unit
def test_search_content_validation_invalid_types(tmp_path):
    """Test SearchContentTool validation with invalid parameter types."""
    tool = SearchContentTool(str(tmp_path))

    # Test missing query and roots/files
    with pytest.raises(ValueError, match="Either roots or files must be provided"):
        tool.validate_arguments({"query": "test"})

    # Test invalid boolean parameters
    with pytest.raises(ValueError, match="count_only_matches must be a boolean"):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "test", "count_only_matches": "true"}
        )

    # Test invalid integer parameters
    with pytest.raises(ValueError, match="max_count must be an integer"):
        tool.validate_arguments(
            {"roots": [str(tmp_path)], "query": "test", "max_count": "10"}
        )


@pytest.mark.unit
def test_build_fd_command():
    """Test building fd command with various options."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_fd_command

    # Test basic command with pattern
    cmd = build_fd_command(
        pattern="*.py",
        glob=True,
        types=None,
        extensions=None,
        exclude=None,
        depth=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        size=None,
        changed_within=None,
        changed_before=None,
        full_path_match=False,
        absolute=True,
        limit=None,
        roots=["/test"],
    )

    assert cmd[0] == "fd"
    assert "--color" in cmd
    assert "never" in cmd
    assert "--glob" in cmd
    assert "-a" in cmd  # absolute
    assert "*.py" in cmd
    assert "/test" in cmd

    # Test command without pattern (should use '.')
    cmd = build_fd_command(
        pattern=None,
        glob=False,
        types=["f"],
        extensions=["py"],
        exclude=["__pycache__"],
        depth=2,
        follow_symlinks=True,
        hidden=True,
        no_ignore=True,
        size=["+1M"],
        changed_within="1day",
        changed_before="2023-01-01",
        full_path_match=True,
        absolute=False,
        limit=100,
        roots=["/test"],
    )

    assert "." in cmd  # default pattern
    assert "-t" in cmd and "f" in cmd  # type
    assert "-e" in cmd and "py" in cmd  # extension
    assert "-E" in cmd and "__pycache__" in cmd  # exclude
    assert "-d" in cmd and "2" in cmd  # depth
    assert "-L" in cmd  # follow symlinks
    assert "-H" in cmd  # hidden
    assert "-I" in cmd  # no ignore
    assert "-S" in cmd and "+1M" in cmd  # size
    assert "--changed-within" in cmd and "1day" in cmd
    assert "--changed-before" in cmd and "2023-01-01" in cmd
    assert "-p" in cmd  # full path match
    assert "--max-results" in cmd and "100" in cmd  # limit
    assert "/test" in cmd


@pytest.mark.unit
def test_parse_rg_count_output_edge_cases():
    """Test parsing ripgrep count output with edge cases."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import parse_rg_count_output

    # Test empty output
    result = parse_rg_count_output(b"")
    assert result["__total__"] == 0

    # Test output with invalid lines
    count_output = b"""file1.py:5
invalid_line_without_colon
file2.py:not_a_number
file3.py:10
"""
    result = parse_rg_count_output(count_output)
    assert result["file1.py"] == 5
    assert result["file3.py"] == 10
    assert result["__total__"] == 15
    assert "invalid_line_without_colon" not in result
    assert "file2.py" not in result

    # Test output with multiple colons
    count_output = b"""C:\\path\\with\\colons\\file.py:7
/unix/path/file.py:3
"""
    result = parse_rg_count_output(count_output)
    assert result["C:\\path\\with\\colons\\file.py"] == 7
    assert result["/unix/path/file.py"] == 3
    assert result["__total__"] == 10


@pytest.mark.unit
def test_summarize_search_results_edge_cases():
    """Test summarizing search results with edge cases."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import summarize_search_results

    # Test empty results
    summary = summarize_search_results([])
    assert summary["total_matches"] == 0
    assert summary["total_files"] == 0
    assert summary["summary"] == "No matches found"
    assert summary["top_files"] == []

    # Test single match
    matches = [{"file": "test.py", "line": 1, "text": "import os"}]
    summary = summarize_search_results(matches, max_files=10, max_total_lines=10)
    assert summary["total_matches"] == 1
    assert summary["total_files"] == 1
    assert summary["truncated"] is False
    assert len(summary["top_files"]) == 1
    assert summary["top_files"][0]["file"] == "test.py"
    assert summary["top_files"][0]["match_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_pattern_and_no_pattern(monkeypatch, tmp_path):
    """Test ListFilesTool with and without pattern to verify fd command building."""
    tool = ListFilesTool(str(tmp_path))

    captured_commands = []

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        captured_commands.append(cmd)
        return 0, b"test.py\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with pattern
    await tool.execute({"roots": [str(tmp_path)], "pattern": "*.py", "glob": True})
    assert "*.py" in captured_commands[0]

    # Test without pattern (should use '.')
    captured_commands.clear()
    await tool.execute({"roots": [str(tmp_path)]})
    assert "." in captured_commands[0]

    # On macOS, PathResolver normalizes /private/var/ to /var/ for consistency
    # So we need to check for the normalized path in the command
    import os

    expected_path = str(tmp_path)
    if os.name == "posix" and expected_path.startswith("/private/var/"):
        expected_path = expected_path.replace("/private/var/", "/var/", 1)

    assert expected_path in captured_commands[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_optimize_paths(monkeypatch, tmp_path):
    """Test SearchContentTool with path optimization enabled."""
    tool = SearchContentTool(str(tmp_path))

    # Create test files with long paths
    long_path = tmp_path / "very" / "long" / "path" / "structure"
    long_path.mkdir(parents=True)
    f1 = long_path / "file1.txt"
    f1.write_text("hello world\n", encoding="utf-8")

    # Mock ripgrep JSON output with long absolute paths
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

    # Test with path optimization enabled
    result = await tool.execute(
        {"files": [str(f1)], "query": "hello", "optimize_paths": True}
    )

    assert result["success"] is True
    assert result["count"] == 1

    # The optimized path should be shorter than the original
    original_path = str(f1)
    optimized_path = result["results"][0]["file"]
    assert len(optimized_path) <= len(original_path)
    # Should not contain abs_path field
    assert "abs_path" not in result["results"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_group_by_file(monkeypatch, tmp_path):
    """Test SearchContentTool with file grouping enabled."""
    tool = SearchContentTool(str(tmp_path), enable_cache=False)

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("hello world\nhello ai\nhello python\n", encoding="utf-8")

    # Mock multiple ripgrep JSON matches from the same file
    rg_events = [
        {
            "type": "match",
            "data": {
                "path": {"text": str(test_file)},
                "lines": {"text": "hello world\n"},
                "line_number": 1,
                "submatches": [{"match": {"text": "hello"}, "start": 0, "end": 5}],
            },
        },
        {
            "type": "match",
            "data": {
                "path": {"text": str(test_file)},
                "lines": {"text": "hello ai\n"},
                "line_number": 2,
                "submatches": [{"match": {"text": "hello"}, "start": 0, "end": 5}],
            },
        },
        {
            "type": "match",
            "data": {
                "path": {"text": str(test_file)},
                "lines": {"text": "hello python\n"},
                "line_number": 3,
                "submatches": [{"match": {"text": "hello"}, "start": 0, "end": 5}],
            },
        },
    ]

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "rg":
            import json

            output_lines = []
            for event in rg_events:
                output_lines.append(json.dumps(event))
            out = "\n".join(output_lines).encode()
            return 0, out, b""
        return 0, str(test_file).encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with file grouping enabled
    result = await tool.execute(
        {"files": [str(test_file)], "query": "hello", "group_by_file": True}
    )

    assert result["success"] is True
    assert result["count"] == 3
    assert "files" in result
    assert len(result["files"]) == 1  # Only one file

    file_result = result["files"][0]
    assert file_result["file"] == str(test_file)
    assert len(file_result["matches"]) == 3  # Three matches in the file

    # Verify match structure
    for i, match in enumerate(file_result["matches"], 1):
        assert match["line"] == i
        assert "hello" in match["text"]
        assert match["positions"] == [[0, 5]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_total_only(monkeypatch, tmp_path):
    """Test SearchContentTool with total_only mode for maximum token efficiency."""
    tool = SearchContentTool(str(tmp_path), enable_cache=False)

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("hello world\nhello ai\nhello python\n", encoding="utf-8")

    # Mock ripgrep count output (simulating --count-matches)
    count_output = f"{test_file}:3\n".encode()

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "rg" and "--count-matches" in cmd:
            return 0, count_output, b""
        return 0, str(test_file).encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with total_only enabled
    result = await tool.execute(
        {"files": [str(test_file)], "query": "hello", "total_only": True}
    )

    # Should return just the number
    assert result == 3
    assert isinstance(result, int)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_with_files_parameter(monkeypatch, tmp_path):
    """Test SearchContentTool with files parameter instead of roots."""
    tool = SearchContentTool(str(tmp_path))

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("import os\n", encoding="utf-8")

    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(test_file)},
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

    result = await tool.execute({"files": [str(test_file)], "query": "import"})

    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(test_file)


# ============================================================================
# COMPREHENSIVE TEST ENHANCEMENTS
# ============================================================================

# --- ListFilesTool Enhanced Tests ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_size_filters(monkeypatch, tmp_path):
    """Test ListFilesTool with size filter parameters."""
    tool = ListFilesTool(str(tmp_path))

    # Create test files
    small_file = tmp_path / "small.txt"
    small_file.write_text("small", encoding="utf-8")
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 1000, encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify size filters are in command
        assert "-S" in cmd
        assert "+500B" in cmd
        return 0, f"{large_file}\n".encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)], "size": ["+500B"]})

    assert result["success"] is True
    assert result["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_time_filters(monkeypatch, tmp_path):
    """Test ListFilesTool with time-based filters."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify time filters are in command
        assert "--changed-within" in cmd
        assert "1d" in cmd
        assert "--changed-before" in cmd
        assert "1w" in cmd
        return 0, b"test.txt\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "changed_within": "1d", "changed_before": "1w"}
    )

    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_types_and_extensions(monkeypatch, tmp_path):
    """Test ListFilesTool with file type and extension filters."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify type and extension filters
        assert "-t" in cmd and "f" in cmd  # files only
        assert "-e" in cmd and "py" in cmd  # Python extension
        return 0, b"test.py\nscript.py\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "types": ["f"], "extensions": ["py"]}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_depth_and_symlinks(monkeypatch, tmp_path):
    """Test ListFilesTool with depth limit and symlink following."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify depth and symlink options
        assert "-d" in cmd and "2" in cmd  # max depth 2
        assert "-L" in cmd  # follow symlinks
        assert "-H" in cmd  # include hidden
        return 0, b"file1.txt\n.hidden\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "depth": 2, "follow_symlinks": True, "hidden": True}
    )

    assert result["success"] is True
    assert result["count"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_with_full_path_match(monkeypatch, tmp_path):
    """Test ListFilesTool with full path matching."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify full path match option
        assert "-p" in cmd  # full path match
        return 0, b"src/main.py\n", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "src/main.py", "full_path_match": True}
    )

    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_files_metadata_fields(monkeypatch, tmp_path):
    """Test ListFilesTool returns correct metadata fields."""
    tool = ListFilesTool(str(tmp_path))

    # Create test file with known properties
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        return 0, f"{test_file}\n".encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute({"roots": [str(tmp_path)]})

    assert result["success"] is True
    assert "elapsed_ms" in result
    assert "truncated" in result
    assert len(result["results"]) == 1

    file_result = result["results"][0]
    assert "path" in file_result
    assert "is_dir" in file_result
    assert "size_bytes" in file_result
    assert "mtime" in file_result
    assert "ext" in file_result
    assert file_result["ext"] == "py"
    assert file_result["is_dir"] is False


# --- SearchContentTool Enhanced Tests ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_with_context_lines(monkeypatch, tmp_path):
    """Test SearchContentTool with context before/after parameters."""
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify context options are in command
        assert "-B" in cmd and "2" in cmd  # before context
        assert "-A" in cmd and "3" in cmd  # after context
        return (
            0,
            b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"match"},"line_number":1,"submatches":[]}}\n',
            b"",
        )

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "test",
            "context_before": 2,
            "context_after": 3,
        }
    )

    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_with_encoding_and_filesize(monkeypatch, tmp_path):
    """Test SearchContentTool with encoding and max filesize parameters."""
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify encoding and filesize options
        assert "--encoding" in cmd and "latin1" in cmd  # encoding
        assert "--max-filesize" in cmd and "5M" in cmd  # max filesize
        return (
            0,
            b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"match"},"line_number":1,"submatches":[]}}\n',
            b"",
        )

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "test",
            "encoding": "latin1",
            "max_filesize": "5M",
        }
    )

    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_with_word_and_fixed_strings(monkeypatch, tmp_path):
    """Test SearchContentTool with word boundary and fixed string matching."""
    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        # Verify word and fixed string options
        assert "-w" in cmd  # word boundary
        assert "-F" in cmd  # fixed strings
        return (
            0,
            b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"test"},"line_number":1,"submatches":[]}}\n',
            b"",
        )

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "test", "word": True, "fixed_strings": True}
    )

    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_case_sensitivity_modes(monkeypatch, tmp_path):
    """Test SearchContentTool with different case sensitivity modes."""
    tool = SearchContentTool(str(tmp_path))

    test_cases = [
        ("smart", ["-S"]),  # smart case
        ("insensitive", ["-i"]),  # case insensitive
        ("sensitive", []),  # case sensitive (default)
    ]

    for case_mode, expected_flags in test_cases:
        captured_cmd = []

        def make_fake_run(cmd_list):
            async def fake_run(cmd, input_data=None, timeout_ms=None):
                cmd_list.extend(cmd)
                return (
                    0,
                    b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"Test"},"line_number":1,"submatches":[]}}\n',
                    b"",
                )

            return fake_run

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            make_fake_run(captured_cmd),
        )

        result = await tool.execute(
            {"roots": [str(tmp_path)], "query": "Test", "case": case_mode}
        )

        assert result["success"] is True
        for flag in expected_flags:
            assert flag in captured_cmd
        captured_cmd.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_content_with_timeout_and_max_count(monkeypatch, tmp_path):
    """Test SearchContentTool with timeout and max count limits."""
    tool = SearchContentTool(str(tmp_path))

    captured_timeout = None

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        nonlocal captured_timeout
        captured_timeout = timeout_ms
        # Verify max count option
        assert "-m" in cmd and "10" in cmd
        return (
            0,
            b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"match"},"line_number":1,"submatches":[]}}\n',
            b"",
        )

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "test", "timeout_ms": 3000, "max_count": 10}
    )

    assert result["success"] is True
    # Verify timeout was passed correctly
    assert captured_timeout == 3000


# --- FindAndGrepTool Enhanced Tests ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_file_discovery_parameters(monkeypatch, tmp_path):
    """Test FindAndGrepTool with comprehensive file discovery parameters."""
    tool = FindAndGrepTool(str(tmp_path))

    call_count = 0

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        nonlocal call_count
        call_count += 1

        if call_count == 1:  # fd command
            # Verify fd parameters
            assert "fd" in cmd[0]
            assert "-t" in cmd and "f" in cmd  # file type
            assert "-e" in cmd and "py" in cmd  # extension
            assert "-E" in cmd and "*.tmp" in cmd  # exclude
            assert "-d" in cmd and "3" in cmd  # depth
            assert "-L" in cmd  # follow symlinks
            assert "-H" in cmd  # hidden files
            assert "-S" in cmd and "+1K" in cmd  # size filter
            return 0, b"test.py\n", b""
        else:  # rg command
            return (
                0,
                b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"import"},"line_number":1,"submatches":[]}}\n',
                b"",
            )

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "import",
            "types": ["f"],
            "extensions": ["py"],
            "exclude": ["*.tmp"],
            "depth": 3,
            "follow_symlinks": True,
            "hidden": True,
            "size": ["+1K"],
        }
    )

    assert result["success"] is True
    assert call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_content_search_parameters(monkeypatch, tmp_path):
    """Test FindAndGrepTool with comprehensive content search parameters."""
    tool = FindAndGrepTool(str(tmp_path))

    call_count = 0

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        nonlocal call_count
        call_count += 1

        if call_count == 1:  # fd command
            return 0, b"test.py\n", b""
        else:  # rg command
            # Verify rg parameters
            assert "rg" in cmd[0]
            assert "-i" in cmd  # case insensitive
            assert "-F" in cmd  # fixed strings
            assert "-w" in cmd  # word boundary
            assert "--multiline" in cmd  # multiline (uses --multiline not -U)
            assert "--max-filesize" in cmd and "10M" in cmd
            assert "-B" in cmd and "2" in cmd  # context before
            assert "-A" in cmd and "3" in cmd  # context after
            return (
                0,
                b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"TEST"},"line_number":1,"submatches":[]}}\n',
                b"",
            )

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "TEST",
            "case": "insensitive",
            "fixed_strings": True,
            "word": True,
            "multiline": True,
            "max_filesize": "10M",
            "context_before": 2,
            "context_after": 3,
        }
    )

    assert result["success"] is True
    assert call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_with_file_sorting(monkeypatch, tmp_path):
    """Test FindAndGrepTool with file sorting options."""
    tool = FindAndGrepTool(str(tmp_path))

    # Create test files with different properties
    file1 = tmp_path / "a.py"
    file2 = tmp_path / "b.py"
    file1.write_text("small", encoding="utf-8")
    file2.write_text("larger content", encoding="utf-8")

    call_count = 0

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        nonlocal call_count
        call_count += 1

        if call_count == 1:  # fd command
            # Return files in unsorted order
            return 0, f"{file2}\n{file1}\n".encode(), b""
        else:  # rg command
            rg_json = {
                "type": "match",
                "data": {
                    "path": {"text": str(file1)},
                    "lines": {"text": "small"},
                    "line_number": 1,
                    "submatches": [],
                },
            }
            return 0, (json.dumps(rg_json) + "\n").encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test path sorting
    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "small", "sort": "path"}
    )

    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_and_grep_summary_only_mode(monkeypatch, tmp_path):
    """Test FindAndGrepTool with summary_only output format."""
    tool = FindAndGrepTool(str(tmp_path))

    call_count = 0

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        nonlocal call_count
        call_count += 1

        if call_count == 1:  # fd command
            return 0, b"file1.py\nfile2.py\n", b""
        else:  # rg command
            # Multiple matches for summary
            matches = [
                '{"type":"match","data":{"path":{"text":"file1.py"},"lines":{"text":"import os"},"line_number":1,"submatches":[]}}',
                '{"type":"match","data":{"path":{"text":"file1.py"},"lines":{"text":"import sys"},"line_number":2,"submatches":[]}}',
                '{"type":"match","data":{"path":{"text":"file2.py"},"lines":{"text":"import json"},"line_number":1,"submatches":[]}}',
            ]
            return 0, "\n".join(matches).encode(), b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "import", "summary_only": True}
    )

    assert result["success"] is True
    assert result["summary_only"] is True
    assert "summary" in result
    assert "meta" in result
    assert result["meta"]["searched_file_count"] == 2


# --- Error Handling and Edge Cases ---


@pytest.mark.unit
def test_list_files_validation_comprehensive(tmp_path):
    """Test comprehensive parameter validation for ListFilesTool."""
    tool = ListFilesTool(str(tmp_path))

    # Test all invalid parameter types
    invalid_cases = [
        ({"roots": "not_a_list"}, "roots must be an array"),
        ({"roots": [str(tmp_path)], "glob": "true"}, "glob must be a boolean"),
        ({"roots": [str(tmp_path)], "depth": "5"}, "depth must be an integer"),
        ({"roots": [str(tmp_path)], "limit": "100"}, "limit must be an integer"),
        (
            {"roots": [str(tmp_path)], "extensions": ["py", 123]},
            "extensions must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "types": [1, 2]},
            "types must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "exclude": "*.tmp"},
            "exclude must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "size": "large"},
            "size must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "follow_symlinks": "yes"},
            "follow_symlinks must be a boolean",
        ),
        ({"roots": [str(tmp_path)], "hidden": 1}, "hidden must be a boolean"),
        (
            {"roots": [str(tmp_path)], "no_ignore": "false"},
            "no_ignore must be a boolean",
        ),
        (
            {"roots": [str(tmp_path)], "full_path_match": "true"},
            "full_path_match must be a boolean",
        ),
        ({"roots": [str(tmp_path)], "absolute": 0}, "absolute must be a boolean"),
        ({"roots": [str(tmp_path)], "pattern": 123}, "pattern must be a string"),
        (
            {"roots": [str(tmp_path)], "changed_within": 30},
            "changed_within must be a string",
        ),
        (
            {"roots": [str(tmp_path)], "changed_before": []},
            "changed_before must be a string",
        ),
    ]

    for invalid_args, expected_error in invalid_cases:
        with pytest.raises(ValueError, match=expected_error):
            tool.validate_arguments(invalid_args)


@pytest.mark.unit
def test_search_content_validation_comprehensive(tmp_path):
    """Test comprehensive parameter validation for SearchContentTool."""
    tool = SearchContentTool(str(tmp_path))

    # Test all invalid parameter types
    invalid_cases = [
        ({"query": "test"}, "Either roots or files must be provided"),
        ({"roots": [str(tmp_path)]}, "query is required"),
        ({"roots": [str(tmp_path)], "query": ""}, "query is required"),
        (
            {"roots": [str(tmp_path)], "query": "test", "case": 123},
            "case must be a string",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "encoding": []},
            "encoding must be a string",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "max_filesize": 100},
            "max_filesize must be a string",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "fixed_strings": "true"},
            "fixed_strings must be a boolean",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "word": 1},
            "word must be a boolean",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "multiline": "false"},
            "multiline must be a boolean",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "context_before": "2"},
            "context_before must be an integer",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "context_after": 2.5},
            "context_after must be an integer",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "max_count": "10"},
            "max_count must be an integer",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "timeout_ms": "5000"},
            "timeout_ms must be an integer",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "include_globs": "*.py"},
            "include_globs must be an array of strings",
        ),
        (
            {"roots": [str(tmp_path)], "query": "test", "exclude_globs": [1, 2]},
            "exclude_globs must be an array of strings",
        ),
    ]

    for invalid_args, expected_error in invalid_cases:
        with pytest.raises(ValueError, match=expected_error):
            tool.validate_arguments(invalid_args)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tools_timeout_handling(monkeypatch, tmp_path):
    """Test timeout handling for all tools."""
    tools = [
        ListFilesTool(str(tmp_path)),
        SearchContentTool(str(tmp_path)),
        FindAndGrepTool(str(tmp_path)),
    ]

    async def fake_timeout_run(cmd, input_data=None, timeout_ms=None):
        # Simulate timeout
        return 124, b"", b"Timeout after 1000 ms"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        fake_timeout_run,
    )

    test_args = [
        {"roots": [str(tmp_path)]},  # ListFilesTool
        {"roots": [str(tmp_path)], "query": "test"},  # SearchContentTool
        {"roots": [str(tmp_path)], "query": "test"},  # FindAndGrepTool
    ]

    for tool, args in zip(tools, test_args, strict=False):
        result = await tool.execute(args)
        assert result["success"] is False
        assert result["returncode"] == 124


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tools_with_empty_results(monkeypatch, tmp_path):
    """Test all tools with empty results."""
    tools = [
        (ListFilesTool(str(tmp_path)), {"roots": [str(tmp_path)]}),
        (
            SearchContentTool(str(tmp_path)),
            {"roots": [str(tmp_path)], "query": "nonexistent"},
        ),
        (
            FindAndGrepTool(str(tmp_path)),
            {"roots": [str(tmp_path)], "query": "nonexistent"},
        ),
    ]

    async def fake_empty_run(cmd, input_data=None, timeout_ms=None):
        return 0, b"", b""  # Empty results

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_empty_run
    )

    for tool, args in tools:
        result = await tool.execute(args)
        assert result["success"] is True
        if "count" in result:
            assert result["count"] == 0
        if "results" in result:
            assert len(result["results"]) == 0


@pytest.mark.unit
def test_fd_rg_utils_edge_cases():
    """Test edge cases in fd_rg_utils functions."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import (
        clamp_int,
        normalize_max_filesize,
        parse_size_to_bytes,
    )

    # Test clamp_int edge cases
    assert clamp_int(None, 100, 1000) == 100
    assert clamp_int(-50, 100, 1000) == 0
    assert clamp_int(2000, 100, 1000) == 1000
    assert clamp_int("invalid", 100, 1000) == 100

    # Test parse_size_to_bytes edge cases
    assert parse_size_to_bytes("") is None
    assert parse_size_to_bytes("invalid") is None
    assert parse_size_to_bytes("10.5K") == 10752
    assert parse_size_to_bytes("2.5M") == 2621440
    assert parse_size_to_bytes("1G") == 1073741824

    # Test normalize_max_filesize edge cases
    assert normalize_max_filesize(None) == "10M"
    assert normalize_max_filesize("500M") == "200M"  # Clamped to hard cap
    assert normalize_max_filesize("5M") == "5M"  # Within limits
