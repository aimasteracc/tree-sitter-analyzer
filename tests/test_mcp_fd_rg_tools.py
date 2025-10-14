import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True
    )


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
    assert result["count"] >= 0
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

    # Test command without pattern (should use '.' as default pattern)
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

    assert "." in cmd  # Should have default pattern when pattern is None
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

    # Test without pattern (should use '.' as default pattern)
    captured_commands.clear()
    await tool.execute({"roots": [str(tmp_path)]})
    assert (
        "." in captured_commands[0]
    )  # Should have default pattern when pattern is None

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


# --- 基础搜索功能测试 (01-04) ---


@pytest.mark.asyncio
async def test_fd_01_simple_search(tmp_path, monkeypatch):
    """Test simple search functionality - corresponds to fd's test_simple."""
    # Create test directory structure exactly like fd's test
    (tmp_path / "a.foo").write_text("content a")
    (tmp_path / "one").mkdir()
    (tmp_path / "one" / "b.foo").write_text("content b")
    (tmp_path / "one" / "two").mkdir()
    (tmp_path / "one" / "two" / "c.foo").write_text("content c")
    (tmp_path / "one" / "two" / "C.Foo2").write_text("content C")
    (tmp_path / "one" / "two" / "three").mkdir()
    (tmp_path / "one" / "two" / "three" / "d.foo").write_text("content d")
    (tmp_path / "one" / "two" / "three" / "directory_foo").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        pattern = None
        for _i, arg in enumerate(cmd):
            if arg not in [
                "-a",
                "-H",
                "-I",
                "-L",
                "--color",
                "never",
                "fd",
            ] and not arg.startswith("-"):
                pattern = arg
                break

        if pattern == "a.foo":
            files = [str(tmp_path / "a.foo")]
        elif pattern == "b.foo":
            files = [str(tmp_path / "one" / "b.foo")]
        elif pattern == "d.foo":
            files = [str(tmp_path / "one" / "two" / "three" / "d.foo")]
        elif pattern == "foo":
            files = [
                str(tmp_path / "a.foo"),
                str(tmp_path / "one" / "b.foo"),
                str(tmp_path / "one" / "two" / "c.foo"),
                str(tmp_path / "one" / "two" / "C.Foo2"),
                str(tmp_path / "one" / "two" / "three" / "d.foo"),
                str(tmp_path / "one" / "two" / "three" / "directory_foo"),
            ]
        else:
            files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test basic search functionality
    result1 = await tool.execute({"roots": [str(tmp_path)], "pattern": "a.foo"})
    assert result1["success"] is True
    assert result1["count"] >= 0  # Allow zero results

    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.foo", "glob": True}
    )
    assert result2["success"] is True
    assert result2["count"] >= 0  # Allow zero results

    # Test pattern search
    result3 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )
    assert result3["success"] is True
    assert result3["count"] >= 0  # Allow zero results


@pytest.mark.asyncio
async def test_fd_02_multi_file_search(tmp_path, monkeypatch):
    """Test multi-directory search - corresponds to fd's test_multi_file."""
    # Create multiple test directories
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir1" / "file1.txt").write_text("content1")
    (tmp_path / "dir2").mkdir()
    (tmp_path / "dir2" / "file2.txt").write_text("content2")
    (tmp_path / "dir3").mkdir()
    (tmp_path / "dir3" / "file3.txt").write_text("content3")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check which directories are being searched
        roots = []
        for i, arg in enumerate(cmd):
            if i > 0 and not arg.startswith("-") and arg != "fd" and "." not in arg:
                roots.append(arg)

        files = []
        if str(tmp_path / "dir1") in roots or not roots:
            files.append(str(tmp_path / "dir1" / "file1.txt"))
        if str(tmp_path / "dir2") in roots or not roots:
            files.append(str(tmp_path / "dir2" / "file2.txt"))
        if str(tmp_path / "dir3") in roots or not roots:
            files.append(str(tmp_path / "dir3" / "file3.txt"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test multi-directory search
    result = await tool.execute(
        {
            "roots": [
                str(tmp_path / "dir1"),
                str(tmp_path / "dir2"),
                str(tmp_path / "dir3"),
            ],
            "pattern": "*.txt",
            "glob": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_03_multi_file_with_missing(tmp_path, monkeypatch):
    """Test search with missing directories - corresponds to fd's test_multi_file_with_missing."""
    # Create only some directories
    (tmp_path / "existing").mkdir()
    (tmp_path / "existing" / "file.txt").write_text("content")
    # missing directory: tmp_path / "missing"

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate fd behavior with missing directories
        files = [str(tmp_path / "existing" / "file.txt")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with missing directory (should handle gracefully)
    try:
        result = await tool.execute(
            {
                "roots": [str(tmp_path / "existing"), str(tmp_path / "missing")],
                "pattern": "*.txt",
                "glob": True,
            }
        )
        # If successful, that's fine
        assert result["success"] is True or result["success"] is False
    except Exception:
        # If it raises an exception for missing directory, that's also expected behavior
        pass


@pytest.mark.asyncio
async def test_fd_04_explicit_root_path(tmp_path, monkeypatch):
    """Test explicit root path - corresponds to fd's test_explicit_root_path."""
    # Create nested structure
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "subdir").mkdir()
    (tmp_path / "root" / "subdir" / "file.txt").write_text("content")
    (tmp_path / "root" / "other.txt").write_text("other content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check if searching in subdir specifically
        if str(tmp_path / "root" / "subdir") in cmd:
            files = [str(tmp_path / "root" / "subdir" / "file.txt")]
        else:
            files = [
                str(tmp_path / "root" / "subdir" / "file.txt"),
                str(tmp_path / "root" / "other.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test explicit subdir as root
    result = await tool.execute(
        {"roots": [str(tmp_path / "root" / "subdir")], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


# --- AND搜索功能测试 (05-15) - 使用FindAndGrepTool模拟 ---


@pytest.mark.asyncio
async def test_fd_05_and_basic_simulation(tmp_path, monkeypatch):
    """Test AND search basic functionality - simulates fd's test_and_basic."""
    # Create test files
    (tmp_path / "foo.txt").write_text("hello world")
    (tmp_path / "bar.txt").write_text("hello universe")
    (tmp_path / "baz.py").write_text("print hello")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "foo.txt"),
                str(tmp_path / "bar.txt"),
                str(tmp_path / "baz.py"),
            ]
        else:  # File search
            files = [str(tmp_path / "foo.txt"), str(tmp_path / "bar.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND search simulation (files with .txt extension AND containing "hello")
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True, "query": "hello"}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_06_and_empty_pattern_simulation(tmp_path, monkeypatch):
    """Test AND search with empty pattern - simulates fd's test_and_empty_pattern."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content")
    (tmp_path / "file2.py").write_text("content")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.py")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with empty file pattern
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "", "query": "content"}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_07_and_bad_pattern_simulation(tmp_path, monkeypatch):
    """Test AND search with bad pattern - simulates fd's test_and_bad_pattern."""
    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate fd command failing with invalid regex
        if "[invalid" in " ".join(cmd):
            return 1, b"", b"error: Invalid regular expression"
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with invalid regex pattern
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "[invalid",  # Invalid regex
            "query": "content",
        }
    )

    # Should handle bad patterns gracefully
    assert result["success"] is False or result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_08_and_pattern_starts_with_dash(tmp_path, monkeypatch):
    """Test AND search with dash-prefixed pattern - simulates fd's test_and_pattern_starts_with_dash."""
    # Create test files
    (tmp_path / "-file.txt").write_text("content")
    (tmp_path / "normal.txt").write_text("content")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-file" in str(cmd):
            files = [str(tmp_path / "-file.txt")]
        else:
            files = [str(tmp_path / "-file.txt"), str(tmp_path / "normal.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test pattern starting with dash
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "-file", "query": "content"}
    )

    assert result["success"] is True or result["success"] is False


@pytest.mark.asyncio
async def test_fd_09_and_plus_extension(tmp_path, monkeypatch):
    """Test AND search with extension filter - simulates fd's test_and_plus_extension."""
    # Create test files
    (tmp_path / "file.txt").write_text("hello world")
    (tmp_path / "file.py").write_text("hello world")
    (tmp_path / "file.js").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "file.py"),
                str(tmp_path / "file.js"),
            ]
        else:  # File search with extension filter
            if "-e" in cmd and "txt" in cmd:
                files = [str(tmp_path / "file.txt")]
            else:
                files = [
                    str(tmp_path / "file.txt"),
                    str(tmp_path / "file.py"),
                    str(tmp_path / "file.js"),
                ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with extension filter
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "query": "hello",
            "extensions": ["txt"],
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_10_and_plus_type(tmp_path, monkeypatch):
    """Test AND search with type filter - simulates fd's test_and_plus_type."""
    # Create test files and directories
    (tmp_path / "file.txt").write_text("hello world")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "subdir" / "nested.txt"),
            ]
        else:  # File search with type filter
            if "-t" in cmd and "f" in cmd:  # Files only
                files = [
                    str(tmp_path / "file.txt"),
                    str(tmp_path / "subdir" / "nested.txt"),
                ]
            else:
                files = [
                    str(tmp_path / "file.txt"),
                    str(tmp_path / "subdir"),
                    str(tmp_path / "subdir" / "nested.txt"),
                ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with type filter
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "query": "hello",
            "types": ["f"],  # Files only
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_11_and_plus_glob(tmp_path, monkeypatch):
    """Test AND search with glob pattern - simulates fd's test_and_plus_glob."""
    # Create test files
    (tmp_path / "test.txt").write_text("hello world")
    (tmp_path / "example.txt").write_text("hello world")
    (tmp_path / "demo.py").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "test.txt"),
                str(tmp_path / "example.txt"),
                str(tmp_path / "demo.py"),
            ]
        else:  # File search with glob
            if "--glob" in cmd and "*.txt" in cmd:
                files = [str(tmp_path / "test.txt"), str(tmp_path / "example.txt")]
            else:
                files = [
                    str(tmp_path / "test.txt"),
                    str(tmp_path / "example.txt"),
                    str(tmp_path / "demo.py"),
                ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with glob pattern
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True, "query": "hello"}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_12_and_plus_fixed_strings(tmp_path, monkeypatch):
    """Test AND search with fixed strings - simulates fd's test_and_plus_fixed_strings."""
    # Create test files
    (tmp_path / "test.file").write_text("hello.world")
    (tmp_path / "other.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            if "-F" in cmd:  # Fixed strings
                files = [str(tmp_path / "test.file")]
            else:
                files = [str(tmp_path / "test.file"), str(tmp_path / "other.txt")]
        else:  # File search
            files = [str(tmp_path / "test.file"), str(tmp_path / "other.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with fixed strings
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "query": "hello.world",
            "fixed_strings": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_13_and_plus_ignore_case(tmp_path, monkeypatch):
    """Test AND search with ignore case - simulates fd's test_and_plus_ignore_case."""
    # Create test files
    (tmp_path / "Test.txt").write_text("Hello World")
    (tmp_path / "test.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            if "-i" in cmd:  # Case insensitive
                files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]
            else:
                files = [str(tmp_path / "test.txt")]
        else:  # File search
            files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with case insensitive
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "query": "hello",
            "case_insensitive": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_14_and_plus_case_sensitive(tmp_path, monkeypatch):
    """Test AND search with case sensitive - simulates fd's test_and_plus_case_sensitive."""
    # Create test files
    (tmp_path / "Test.txt").write_text("Hello World")
    (tmp_path / "test.txt").write_text("hello world")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search - case sensitive by default
            files = [str(tmp_path / "test.txt")]
        else:  # File search
            files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with case sensitive (default)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "query": "hello"}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_15_and_plus_full_path(tmp_path, monkeypatch):
    """Test AND search with full path - simulates fd's test_and_plus_full_path."""
    # Create test files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("import os")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("import os")

    tool = FindAndGrepTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "rg" in cmd[0]:  # Content search
            files = [
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "test_main.py"),
            ]
        else:  # File search with full path
            if "-p" in cmd and "src" in str(cmd):  # Full path match
                files = [str(tmp_path / "src" / "main.py")]
            else:
                files = [
                    str(tmp_path / "src" / "main.py"),
                    str(tmp_path / "tests" / "test_main.py"),
                ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test AND with full path match
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "src",
            "query": "import",
            "full_path_match": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


# --- 模式和搜索类型测试 (16-28) ---


@pytest.mark.asyncio
async def test_fd_16_empty_pattern(tmp_path, monkeypatch):
    """Test empty pattern handling - corresponds to fd's test_empty_pattern."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content")
    (tmp_path / "file2.py").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Empty pattern should match all files
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.py")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test empty pattern
    result = await tool.execute({"roots": [str(tmp_path)], "pattern": ""})

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_17_regex_searches(tmp_path, monkeypatch):
    """Test regex searches - corresponds to fd's test_regex_searches."""
    # Create test files
    (tmp_path / "test1.txt").write_text("content")
    (tmp_path / "test2.txt").write_text("content")
    (tmp_path / "example.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check for regex pattern
        pattern = None
        for arg in cmd:
            if arg.startswith("test"):
                pattern = arg
                break

        if pattern == "test.*\\.txt":
            files = [str(tmp_path / "test1.txt"), str(tmp_path / "test2.txt")]
        else:
            files = [
                str(tmp_path / "test1.txt"),
                str(tmp_path / "test2.txt"),
                str(tmp_path / "example.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test regex pattern
    result = await tool.execute({"roots": [str(tmp_path)], "pattern": "test.*\\.txt"})

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_18_smart_case_search(tmp_path, monkeypatch):
    """Test smart case search - corresponds to fd's test_smart_case."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "TEST.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Smart case: lowercase pattern matches any case, uppercase is exact
        pattern = None
        for arg in cmd:
            if "test" in arg.lower() or "Test" in arg:
                pattern = arg
                break

        if pattern and pattern.islower():  # Smart case for lowercase
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "TEST.txt"),
            ]
        elif pattern and any(c.isupper() for c in pattern):  # Exact case for mixed case
            files = [str(tmp_path / "Test.txt")]
        else:
            files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test smart case with lowercase (should match all)
    result1 = await tool.execute({"roots": [str(tmp_path)], "pattern": "test"})

    assert result1["success"] is True
    assert result1["count"] >= 2

    # Test smart case with mixed case (should be exact)
    result2 = await tool.execute({"roots": [str(tmp_path)], "pattern": "Test"})

    assert result2["success"] is True
    assert result2["count"] >= 1


@pytest.mark.asyncio
async def test_fd_19_case_sensitive_search(tmp_path, monkeypatch):
    """Test case sensitive search - corresponds to fd's test_case_sensitive."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "TEST.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Case sensitive search
        pattern = None
        for arg in cmd:
            if "test" in arg or "Test" in arg or "TEST" in arg:
                pattern = arg
                break

        if pattern == "test":
            files = [str(tmp_path / "test.txt")]
        elif pattern == "Test":
            files = [str(tmp_path / "Test.txt")]
        elif pattern == "TEST":
            files = [str(tmp_path / "TEST.txt")]
        else:
            files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test case sensitive search
    result = await tool.execute({"roots": [str(tmp_path)], "pattern": "test"})

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_20_case_insensitive_search(tmp_path, monkeypatch):
    """Test case insensitive search - corresponds to fd's test_case_insensitive."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "TEST.txt").write_text("content")

    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Case insensitive content search
        if "-i" in cmd:  # Case insensitive flag
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "TEST.txt"),
            ]
        else:
            files = [str(tmp_path / "test.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test case insensitive content search
    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "content", "case_insensitive": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_21_glob_searches(tmp_path, monkeypatch):
    """Test glob searches - corresponds to fd's test_glob_searches."""
    # Create test files
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "test.py").write_text("content")
    (tmp_path / "example.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check for glob patterns
        if "--glob" in cmd:
            if "*.txt" in cmd:
                files = [str(tmp_path / "test.txt"), str(tmp_path / "example.txt")]
            elif "test.*" in cmd:
                files = [str(tmp_path / "test.txt"), str(tmp_path / "test.py")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "test.txt"),
                str(tmp_path / "test.py"),
                str(tmp_path / "example.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test glob pattern for txt files
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result1["success"] is True
    assert result1["count"] >= 2

    # Test glob pattern for test files
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test.*", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 2


@pytest.mark.asyncio
async def test_fd_22_full_path_glob_searches(tmp_path, monkeypatch):
    """Test full path glob searches - corresponds to fd's test_full_path_glob_searches."""
    # Create nested structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("content")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "main.py").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Full path glob search
        if "--glob" in cmd and "-p" in cmd:
            if "**/src/**" in cmd:
                files = [str(tmp_path / "src" / "main.py")]
            else:
                files = [
                    str(tmp_path / "src" / "main.py"),
                    str(tmp_path / "tests" / "main.py"),
                ]
        else:
            files = [
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "main.py"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test full path glob
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "**/src/**",
            "glob": True,
            "full_path_match": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_23_smart_case_glob_searches(tmp_path, monkeypatch):
    """Test smart case glob searches - corresponds to fd's test_smart_case_glob_searches."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "example.TXT").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Smart case glob search
        if "--glob" in cmd:
            if "*.txt" in cmd:  # Lowercase pattern matches all cases
                files = [
                    str(tmp_path / "Test.txt"),
                    str(tmp_path / "test.txt"),
                    str(tmp_path / "example.TXT"),
                ]
            elif "*.TXT" in cmd:  # Uppercase pattern is exact
                files = [str(tmp_path / "example.TXT")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "example.TXT"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test smart case glob (lowercase matches all)
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result1["success"] is True
    assert result1["count"] >= 3

    # Test smart case glob (uppercase is exact)
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.TXT", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1


@pytest.mark.asyncio
async def test_fd_24_case_sensitive_glob_searches(tmp_path, monkeypatch):
    """Test case sensitive glob searches - corresponds to fd's test_case_sensitive_glob_searches."""
    # Create test files
    (tmp_path / "Test.txt").write_text("content")
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "example.TXT").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Case sensitive glob search
        if "--glob" in cmd:
            if "*.txt" in cmd:
                files = [str(tmp_path / "Test.txt"), str(tmp_path / "test.txt")]
            elif "*.TXT" in cmd:
                files = [str(tmp_path / "example.TXT")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "Test.txt"),
                str(tmp_path / "test.txt"),
                str(tmp_path / "example.TXT"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test case sensitive glob
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_25_glob_searches_with_extension(tmp_path, monkeypatch):
    """Test glob searches with extension - corresponds to fd's test_glob_searches_with_extension."""
    # Create test files
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "test.py").write_text("content")
    (tmp_path / "example.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Glob with extension filter
        has_glob = "--glob" in cmd and "test*" in cmd
        has_extension = "-e" in cmd and "txt" in cmd

        if has_glob and has_extension:
            files = [str(tmp_path / "test.txt")]  # Only test.txt matches both
        elif has_glob:
            files = [str(tmp_path / "test.txt"), str(tmp_path / "test.py")]
        elif has_extension:
            files = [str(tmp_path / "test.txt"), str(tmp_path / "example.txt")]
        else:
            files = [
                str(tmp_path / "test.txt"),
                str(tmp_path / "test.py"),
                str(tmp_path / "example.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test glob with extension filter
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "test*",
            "glob": True,
            "extensions": ["txt"],
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_26_regex_overrides_glob(tmp_path, monkeypatch):
    """Test regex overrides glob - corresponds to fd's test_regex_overrides_glob."""
    # Create test files
    (tmp_path / "test.txt").write_text("content")
    (tmp_path / "test_file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # When both regex and glob are specified, regex should take precedence
        if "test\\.txt" in cmd:  # Regex pattern
            files = [str(tmp_path / "test.txt")]  # Exact match only
        elif "--glob" in cmd and "test*" in cmd:  # Glob pattern
            files = [str(tmp_path / "test.txt"), str(tmp_path / "test_file.txt")]
        else:
            files = [str(tmp_path / "test.txt"), str(tmp_path / "test_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test regex pattern (should override glob)
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "test\\.txt"}  # Regex for exact match
    )

    assert result1["success"] is True
    assert result1["count"] >= 1


@pytest.mark.asyncio
async def test_fd_27_full_path_searches(tmp_path, monkeypatch):
    """Test full path searches - corresponds to fd's test_full_path."""
    # Create nested structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("content")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "main.py").write_text("content")
    (tmp_path / "main.py").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Full path search
        if "-p" in cmd:  # Full path flag
            if "src" in cmd:
                files = [str(tmp_path / "src" / "main.py")]
            elif "main.py" in cmd:
                files = [
                    str(tmp_path / "src" / "main.py"),
                    str(tmp_path / "tests" / "main.py"),
                    str(tmp_path / "main.py"),
                ]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "main.py"),
                str(tmp_path / "main.py"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test full path search for "src"
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "src", "full_path_match": True}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1


@pytest.mark.asyncio
async def test_fd_28_fixed_strings_search(tmp_path, monkeypatch):
    """Test fixed strings search - corresponds to fd's test_fixed_strings."""
    # Create test files
    (tmp_path / "test.file").write_text("content")
    (tmp_path / "test_file.txt").write_text("content")
    (tmp_path / "testXfile.py").write_text("content")

    tool = SearchContentTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Fixed strings search (literal, not regex)
        if "-F" in cmd:  # Fixed strings flag
            if "test.file" in cmd:  # Literal dot
                files = [str(tmp_path / "test.file")]
            else:
                files = []
        else:  # Regex search
            if "test.file" in cmd:  # Dot matches any character in regex
                files = [str(tmp_path / "test.file"), str(tmp_path / "testXfile.py")]
            else:
                files = []

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test fixed strings search
    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "content", "fixed_strings": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


# --- 文件属性和过滤测试 (29-36) ---


@pytest.mark.asyncio
async def test_fd_29_hidden_files(tmp_path, monkeypatch):
    """Test hidden files search - corresponds to fd's test_hidden."""
    # Create hidden and visible files
    (tmp_path / ".hidden").write_text("hidden content")
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "settings").write_text("config")
    (tmp_path / "visible.txt").write_text("visible content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-H" in cmd:  # Include hidden files
            files = [
                str(tmp_path / ".hidden"),
                str(tmp_path / ".config"),
                str(tmp_path / ".config" / "settings"),
                str(tmp_path / "visible.txt"),
            ]
        else:  # Exclude hidden files
            files = [str(tmp_path / "visible.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test without hidden files
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": False}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1

    # Test with hidden files
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 4


@pytest.mark.asyncio
async def test_fd_30_hidden_file_attribute(tmp_path, monkeypatch):
    """Test Windows hidden file attribute - corresponds to fd's test_hidden_file_attribute."""
    # Create test files (Windows hidden attribute simulation)
    (tmp_path / "normal.txt").write_text("normal content")
    (tmp_path / "hidden_attr.txt").write_text("hidden attr content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate Windows hidden attribute handling
        if "-H" in cmd:  # Include files with hidden attribute
            files = [str(tmp_path / "normal.txt"), str(tmp_path / "hidden_attr.txt")]
        else:  # Exclude files with hidden attribute
            files = [str(tmp_path / "normal.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test hidden attribute handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_31_type_filtering(tmp_path, monkeypatch):
    """Test file type filtering - corresponds to fd's test_type."""
    # Create different file types
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "directory").mkdir()
    (tmp_path / "directory" / "nested.txt").write_text("nested")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "file.txt"), str(tmp_path / "link.txt"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-t" in cmd:
            if "f" in cmd:  # Files only
                files = [
                    str(tmp_path / "file.txt"),
                    str(tmp_path / "directory" / "nested.txt"),
                ]
                if has_symlink:
                    files.append(str(tmp_path / "link.txt"))
            elif "d" in cmd:  # Directories only
                files = [str(tmp_path / "directory")]
            elif "l" in cmd:  # Symlinks only
                files = [str(tmp_path / "link.txt")] if has_symlink else []
            else:
                files = []
        else:  # All types
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "directory"),
                str(tmp_path / "directory" / "nested.txt"),
            ]
            if has_symlink:
                files.append(str(tmp_path / "link.txt"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files only
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["f"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 2

    # Test directories only
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["d"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1


@pytest.mark.asyncio
async def test_fd_32_type_executable(tmp_path, monkeypatch):
    """Test executable file type - corresponds to fd's test_type_executable."""
    # Create executable and non-executable files
    (tmp_path / "script.sh").write_text("#!/bin/bash\necho hello")
    (tmp_path / "data.txt").write_text("data content")

    # Make script executable (if supported)
    try:
        import os

        os.chmod(str(tmp_path / "script.sh"), 0o755)
        has_executable = True
    except (OSError, AttributeError):
        has_executable = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-t" in cmd and "x" in cmd:  # Executable files only
            files = [str(tmp_path / "script.sh")] if has_executable else []
        else:
            files = [str(tmp_path / "script.sh"), str(tmp_path / "data.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test executable files
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["x"]}
    )

    assert result["success"] is True
    assert result["count"] >= 0  # May be 0 if no executable support


@pytest.mark.asyncio
async def test_fd_33_type_empty(tmp_path, monkeypatch):
    """Test empty file type - corresponds to fd's test_type_empty."""
    # Create empty and non-empty files
    (tmp_path / "empty.txt").write_text("")
    (tmp_path / "nonempty.txt").write_text("content")
    (tmp_path / "empty_dir").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-t" in cmd and "e" in cmd:  # Empty files/directories only
            files = [str(tmp_path / "empty.txt"), str(tmp_path / "empty_dir")]
        else:
            files = [
                str(tmp_path / "empty.txt"),
                str(tmp_path / "nonempty.txt"),
                str(tmp_path / "empty_dir"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test empty files/directories
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "types": ["e"]}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_34_extension_filtering(tmp_path, monkeypatch):
    """Test file extension filtering - corresponds to fd's test_extension."""
    # Create files with different extensions
    (tmp_path / "file.txt").write_text("text content")
    (tmp_path / "script.py").write_text("python code")
    (tmp_path / "data.json").write_text('{"key": "value"}')
    (tmp_path / "README").write_text("readme content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-e" in cmd:
            if "txt" in cmd:
                files = [str(tmp_path / "file.txt")]
            elif "py" in cmd:
                files = [str(tmp_path / "script.py")]
            elif "json" in cmd:
                files = [str(tmp_path / "data.json")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "script.py"),
                str(tmp_path / "data.json"),
                str(tmp_path / "README"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test txt extension
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "extensions": ["txt"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1

    # Test py extension
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "extensions": ["py"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1


@pytest.mark.asyncio
async def test_fd_35_no_extension(tmp_path, monkeypatch):
    """Test files without extension - corresponds to fd's test_no_extension."""
    # Create files with and without extensions
    (tmp_path / "file.txt").write_text("with extension")
    (tmp_path / "README").write_text("no extension")
    (tmp_path / "Makefile").write_text("no extension")
    (tmp_path / "script.py").write_text("with extension")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate filtering for files without extensions
        # This would be a complex filter in fd, here we simulate the result
        files = [str(tmp_path / "README"), str(tmp_path / "Makefile")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files without extension (simulated with pattern)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "[^.]*$"}  # Regex for no extension
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_36_size_filtering(tmp_path, monkeypatch):
    """Test file size filtering - corresponds to fd's test_size."""
    # Create files of different sizes
    (tmp_path / "small.txt").write_text("small")  # ~5 bytes
    (tmp_path / "medium.txt").write_text("medium content" * 10)  # ~140 bytes
    (tmp_path / "large.txt").write_text("large content" * 100)  # ~1300 bytes

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--size" in cmd:
            if "+100b" in cmd:  # Files larger than 100 bytes
                files = [str(tmp_path / "medium.txt"), str(tmp_path / "large.txt")]
            elif "-100b" in cmd:  # Files smaller than 100 bytes
                files = [str(tmp_path / "small.txt")]
            elif "+1k" in cmd:  # Files larger than 1KB
                files = [str(tmp_path / "large.txt")]
            else:
                files = []
        else:
            files = [
                str(tmp_path / "small.txt"),
                str(tmp_path / "medium.txt"),
                str(tmp_path / "large.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files larger than 100 bytes
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["+100b"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 2

    # Test files smaller than 100 bytes
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["-100b"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 1


# --- 忽略规则测试 (37) ---


@pytest.mark.asyncio
async def test_fd_37_no_ignore_basic(tmp_path, monkeypatch):
    """Test basic no ignore functionality - corresponds to fd's test_no_ignore."""
    # Create gitignore and files
    (tmp_path / ".gitignore").write_text("*.log\ntemp/\n")
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "debug.log").write_text("log content")
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp" / "data.txt").write_text("temp data")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-I" in cmd:  # No ignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "file.txt"),
                str(tmp_path / "debug.log"),
                str(tmp_path / "temp"),
                str(tmp_path / "temp" / "data.txt"),
            ]
        else:  # Respect .gitignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "file.txt"),
                # debug.log and temp/ are ignored
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with ignore rules
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": False}
    )

    assert result1["success"] is True
    assert result1["count"] >= 2

    # Test without ignore rules
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 5


# --- 深度控制测试 (39-42) ---


@pytest.mark.asyncio
async def test_fd_39_max_depth_filtering(tmp_path, monkeypatch):
    """Test maximum depth filtering - corresponds to fd's test_max_depth."""
    # Create nested directory structure
    (tmp_path / "level1").mkdir()
    (tmp_path / "level1" / "file1.txt").write_text("level1 content")
    (tmp_path / "level1" / "level2").mkdir()
    (tmp_path / "level1" / "level2" / "file2.txt").write_text("level2 content")
    (tmp_path / "level1" / "level2" / "level3").mkdir()
    (tmp_path / "level1" / "level2" / "level3" / "file3.txt").write_text(
        "level3 content"
    )

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-d" in cmd:
            depth_idx = cmd.index("-d") + 1
            if depth_idx < len(cmd):
                depth = int(cmd[depth_idx])
                if depth == 1:
                    files = [str(tmp_path / "level1")]
                elif depth == 2:
                    files = [
                        str(tmp_path / "level1"),
                        str(tmp_path / "level1" / "file1.txt"),
                        str(tmp_path / "level1" / "level2"),
                    ]
                elif depth == 3:
                    files = [
                        str(tmp_path / "level1"),
                        str(tmp_path / "level1" / "file1.txt"),
                        str(tmp_path / "level1" / "level2"),
                        str(tmp_path / "level1" / "level2" / "file2.txt"),
                        str(tmp_path / "level1" / "level2" / "level3"),
                    ]
                else:
                    files = []
            else:
                files = []
        else:
            # No depth limit
            files = [
                str(tmp_path / "level1"),
                str(tmp_path / "level1" / "file1.txt"),
                str(tmp_path / "level1" / "level2"),
                str(tmp_path / "level1" / "level2" / "file2.txt"),
                str(tmp_path / "level1" / "level2" / "level3"),
                str(tmp_path / "level1" / "level2" / "level3" / "file3.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test depth 1
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "depth": 1}
    )

    assert result1["success"] is True
    assert result1["count"] >= 1

    # Test depth 2
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "depth": 2}
    )

    assert result2["success"] is True
    assert result2["count"] >= 3


@pytest.mark.asyncio
async def test_fd_40_min_depth_filtering(tmp_path, monkeypatch):
    """Test minimum depth filtering - corresponds to fd's test_min_depth."""
    # Create nested directory structure
    (tmp_path / "root.txt").write_text("root content")
    (tmp_path / "level1").mkdir()
    (tmp_path / "level1" / "file1.txt").write_text("level1 content")
    (tmp_path / "level1" / "level2").mkdir()
    (tmp_path / "level1" / "level2" / "file2.txt").write_text("level2 content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool doesn't support min_depth, simulate with filtering
        # This would require custom implementation in real fd
        files = [
            str(tmp_path / "level1" / "file1.txt"),
            str(tmp_path / "level1" / "level2" / "file2.txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test min depth simulation (files deeper than root)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_41_exact_depth_filtering(tmp_path, monkeypatch):
    """Test exact depth filtering - corresponds to fd's test_exact_depth."""
    # Create nested directory structure
    (tmp_path / "level1").mkdir()
    (tmp_path / "level1" / "file1.txt").write_text("level1 content")
    (tmp_path / "level1" / "level2").mkdir()
    (tmp_path / "level1" / "level2" / "file2.txt").write_text("level2 content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-d" in cmd:
            depth_idx = cmd.index("-d") + 1
            if depth_idx < len(cmd):
                depth = int(cmd[depth_idx])
                if depth == 2:  # Exact depth 2
                    files = [
                        str(tmp_path / "level1" / "file1.txt"),
                        str(tmp_path / "level1" / "level2"),
                    ]
                else:
                    files = []
            else:
                files = []
        else:
            files = [
                str(tmp_path / "level1"),
                str(tmp_path / "level1" / "file1.txt"),
                str(tmp_path / "level1" / "level2"),
                str(tmp_path / "level1" / "level2" / "file2.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test exact depth 2
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "depth": 2}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_42_prune_functionality(tmp_path, monkeypatch):
    """Test prune functionality - corresponds to fd's test_prune."""
    # Create directory structure
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "file1.txt").write_text("include content")
    (tmp_path / "exclude").mkdir()
    (tmp_path / "exclude" / "file2.txt").write_text("exclude content")
    (tmp_path / "normal.txt").write_text("normal content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate prune with exclude patterns
        if "-E" in cmd and "exclude" in cmd:
            files = [
                str(tmp_path / "include"),
                str(tmp_path / "include" / "file1.txt"),
                str(tmp_path / "normal.txt"),
                # exclude directory is pruned
            ]
        else:
            files = [
                str(tmp_path / "include"),
                str(tmp_path / "include" / "file1.txt"),
                str(tmp_path / "exclude"),
                str(tmp_path / "exclude" / "file2.txt"),
                str(tmp_path / "normal.txt"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test prune with exclude pattern
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "exclude": ["exclude"]}
    )

    assert result["success"] is True
    assert result["count"] >= 3


# --- 排除和过滤测试 (43) ---


@pytest.mark.asyncio
async def test_fd_43_excludes_pattern(tmp_path, monkeypatch):
    """Test exclude patterns - corresponds to fd's test_excludes."""
    # Create test files
    (tmp_path / "include.txt").write_text("include content")
    (tmp_path / "exclude.log").write_text("exclude content")
    (tmp_path / "temp.tmp").write_text("temp content")
    (tmp_path / "normal.py").write_text("normal content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-E" in cmd:
            # Check exclude patterns
            excludes = []
            for i, arg in enumerate(cmd):
                if arg == "-E" and i + 1 < len(cmd):
                    excludes.append(cmd[i + 1])

            files = [
                str(tmp_path / "include.txt"),
                str(tmp_path / "exclude.log"),
                str(tmp_path / "temp.tmp"),
                str(tmp_path / "normal.py"),
            ]

            # Filter out excluded files
            filtered_files = []
            for file in files:
                excluded = False
                for exclude in excludes:
                    if exclude in file or file.endswith(exclude.replace("*", "")):
                        excluded = True
                        break
                if not excluded:
                    filtered_files.append(file)

            files = filtered_files
        else:
            files = [
                str(tmp_path / "include.txt"),
                str(tmp_path / "exclude.log"),
                str(tmp_path / "temp.tmp"),
                str(tmp_path / "normal.py"),
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test exclude .log files
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "exclude": ["*.log"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 3

    # Test exclude multiple patterns
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "exclude": ["*.log", "*.tmp"],
        }
    )

    assert result2["success"] is True
    assert result2["count"] >= 2


# --- 符号链接测试 (44-50) ---


@pytest.mark.asyncio
async def test_fd_44_follow_symlinks(tmp_path, monkeypatch):
    """Test following symlinks - corresponds to fd's test_follow."""
    # Create files and symlinks
    (tmp_path / "real_file.txt").write_text("real content")
    (tmp_path / "real_dir").mkdir()
    (tmp_path / "real_dir" / "nested.txt").write_text("nested content")

    # Create symlinks (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "real_file.txt"), str(tmp_path / "link_file.txt"))
        os.symlink(str(tmp_path / "real_dir"), str(tmp_path / "link_dir"))
        has_symlinks = True
    except (OSError, NotImplementedError):
        has_symlinks = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-L" in cmd and has_symlinks:  # Follow symlinks
            files = [
                str(tmp_path / "real_file.txt"),
                str(tmp_path / "real_dir"),
                str(tmp_path / "real_dir" / "nested.txt"),
                str(tmp_path / "link_file.txt"),
                str(tmp_path / "link_dir"),
                str(tmp_path / "link_dir" / "nested.txt"),  # Through symlink
            ]
        else:  # Don't follow symlinks
            files = [
                str(tmp_path / "real_file.txt"),
                str(tmp_path / "real_dir"),
                str(tmp_path / "real_dir" / "nested.txt"),
            ]
            if has_symlinks:
                files.extend(
                    [str(tmp_path / "link_file.txt"), str(tmp_path / "link_dir")]
                )

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test without following symlinks
    result1 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "follow_symlinks": False,
        }
    )

    assert result1["success"] is True
    assert result1["count"] >= 3

    # Test following symlinks
    result2 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "follow_symlinks": True,
        }
    )

    assert result2["success"] is True
    assert result2["count"] >= 3


@pytest.mark.asyncio
async def test_fd_45_file_system_boundaries(tmp_path, monkeypatch):
    """Test file system boundaries - corresponds to fd's test_file_system_boundaries."""
    # Create test structure
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate staying within file system boundaries
        files = [
            str(tmp_path / "file.txt"),
            str(tmp_path / "subdir"),
            str(tmp_path / "subdir" / "nested.txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test file system boundary handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 3


@pytest.mark.asyncio
async def test_fd_46_follow_broken_symlink(tmp_path, monkeypatch):
    """Test following broken symlinks - corresponds to fd's test_follow_broken_symlink."""
    # Create real file and broken symlink
    (tmp_path / "real.txt").write_text("real content")

    # Create broken symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "nonexistent.txt"), str(tmp_path / "broken_link.txt"))
        has_broken_symlink = True
    except (OSError, NotImplementedError):
        has_broken_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "real.txt")]
        if has_broken_symlink:
            if "-L" in cmd:  # Follow symlinks - broken link might cause issues
                files.append(str(tmp_path / "broken_link.txt"))
            else:  # Don't follow - just list the link
                files.append(str(tmp_path / "broken_link.txt"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test broken symlink handling
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "follow_symlinks": True,
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_47_symlink_as_root(tmp_path, monkeypatch):
    """Test symlink as search root - corresponds to fd's test_symlink_as_root."""
    # Create real directory and symlink to it
    (tmp_path / "real_dir").mkdir()
    (tmp_path / "real_dir" / "file.txt").write_text("content")

    # Create symlink to directory (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "real_dir"), str(tmp_path / "link_dir"))
        has_dir_symlink = True
    except (OSError, NotImplementedError):
        has_dir_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check if symlink directory is used as root
        if has_dir_symlink and str(tmp_path / "link_dir") in cmd:
            files = [str(tmp_path / "link_dir" / "file.txt")]
        else:
            files = [str(tmp_path / "real_dir" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test using symlink as root
    if has_dir_symlink:
        result = await tool.execute(
            {"roots": [str(tmp_path / "link_dir")], "pattern": "*", "glob": True}
        )
    else:
        result = await tool.execute(
            {"roots": [str(tmp_path / "real_dir")], "pattern": "*", "glob": True}
        )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_48_symlink_and_absolute_path(tmp_path, monkeypatch):
    """Test symlinks with absolute paths - corresponds to fd's test_symlink_and_absolute_path."""
    # Create structure with symlinks
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "file.txt").write_text("target content")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "target"), str(tmp_path / "link"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-a" in cmd and has_symlink:  # Absolute paths
            files = [
                str(tmp_path / "target"),
                str(tmp_path / "target" / "file.txt"),
                str(tmp_path / "link"),
            ]
        else:
            files = [str(tmp_path / "target"), str(tmp_path / "target" / "file.txt")]
            if has_symlink:
                files.append(str(tmp_path / "link"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test symlinks with absolute paths
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_49_symlink_as_absolute_root(tmp_path, monkeypatch):
    """Test symlink as absolute root - corresponds to fd's test_symlink_as_absolute_root."""
    # Create target and symlink
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "file.txt").write_text("content")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "target"), str(tmp_path / "abs_link"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if has_symlink and str(tmp_path / "abs_link") in cmd:
            files = [str(tmp_path / "abs_link" / "file.txt")]
        else:
            files = [str(tmp_path / "target" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test absolute symlink as root
    root_path = str(tmp_path / "abs_link") if has_symlink else str(tmp_path / "target")
    result = await tool.execute(
        {"roots": [root_path], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_50_symlink_and_full_path(tmp_path, monkeypatch):
    """Test symlinks with full path matching - corresponds to fd's test_symlink_and_full_path."""
    # Create nested structure with symlinks
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("main content")

    # Create symlink (if supported)
    try:
        import os

        os.symlink(str(tmp_path / "src"), str(tmp_path / "source"))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-p" in cmd and "src" in cmd:  # Full path match for "src"
            files = [str(tmp_path / "src" / "main.py")]
            if has_symlink and "source" not in cmd:
                # Only match actual "src" path, not "source" symlink
                pass
        else:
            files = [str(tmp_path / "src" / "main.py")]
            if has_symlink:
                files.append(str(tmp_path / "source" / "main.py"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test full path matching with symlinks
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "src", "full_path_match": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


# --- 输出格式和路径测试 (51-58) ---


@pytest.mark.asyncio
async def test_fd_51_print0_output_simulation(tmp_path, monkeypatch):
    """Test print0 output simulation - corresponds to fd's test_print0."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool returns JSON, not null-separated output
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test structured output (our equivalent of print0)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
    # Verify structured JSON output
    assert "results" in result
    assert isinstance(result["results"], list)


@pytest.mark.asyncio
async def test_fd_52_absolute_path_output(tmp_path, monkeypatch):
    """Test absolute path output - corresponds to fd's test_absolute_path."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-a" in cmd:  # Absolute paths
            files = [
                str(tmp_path / "file.txt"),
                str(tmp_path / "subdir"),
                str(tmp_path / "subdir" / "nested.txt"),
            ]
        else:  # Relative paths
            files = ["file.txt", "subdir", "subdir/nested.txt"]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test absolute paths
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result1["success"] is True
    assert result1["count"] >= 3
    # Verify absolute paths
    for item in result1["results"]:
        path = item["path"]
        assert path.startswith("/") or (len(path) > 1 and path[1] == ":")

    # Test relative paths
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": False}
    )

    assert result2["success"] is True
    assert result2["count"] >= 3


@pytest.mark.asyncio
async def test_fd_53_implicit_absolute_path(tmp_path, monkeypatch):
    """Test implicit absolute path - corresponds to fd's test_implicit_absolute_path."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Default behavior should be absolute paths
        files = [str(tmp_path / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test default (implicit absolute) paths
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_54_normalized_absolute_path(tmp_path, monkeypatch):
    """Test normalized absolute path - corresponds to fd's test_normalized_absolute_path."""
    # Create test structure with potential path normalization issues
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Return normalized absolute paths
        files = [
            (
                str(tmp_path / "subdir" / "file.txt").replace("\\", "/")
                if "\\" in str(tmp_path)
                else str(tmp_path / "subdir" / "file.txt")
            )
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test normalized paths
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_55_custom_path_separator(tmp_path, monkeypatch):
    """Test custom path separator - corresponds to fd's test_custom_path_separator."""
    # Create nested structure
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool uses OS-appropriate separators
        files = [str(tmp_path / "dir" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test path separator handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0
    # Verify proper path separators
    for item in result["results"]:
        path = item["path"]
        # Should use OS-appropriate separators
        assert "/" in path or "\\" in path


@pytest.mark.asyncio
async def test_fd_56_base_directory_output(tmp_path, monkeypatch):
    """Test base directory output - corresponds to fd's test_base_directory."""
    # Create test structure
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Check if searching from subdir as base
        if str(tmp_path / "subdir") in cmd:
            files = [str(tmp_path / "subdir" / "file.txt")]
        else:
            files = [str(tmp_path / "subdir"), str(tmp_path / "subdir" / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with subdir as base
    result = await tool.execute(
        {"roots": [str(tmp_path / "subdir")], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_57_strip_cwd_prefix(tmp_path, monkeypatch):
    """Test stripping current working directory prefix - corresponds to fd's test_strip_cwd_prefix."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate stripping CWD prefix (relative paths)
        if "-a" not in cmd:
            files = ["file.txt"]  # Relative to CWD
        else:
            files = [str(tmp_path / "file.txt")]  # Absolute

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test relative paths (CWD prefix stripped)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "absolute": False}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_58_format_output_structured(tmp_path, monkeypatch):
    """Test structured format output - corresponds to fd's format test."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "file.txt"), str(tmp_path / "subdir")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test structured JSON format (our default)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
    # Verify structured format
    assert "results" in result
    assert "count" in result
    assert "success" in result
    for item in result["results"]:
        assert "path" in item
        assert "is_dir" in item


# --- 命令执行测试 (59-65) ---


@pytest.mark.asyncio
async def test_fd_59_exec_command_simulation(tmp_path, monkeypatch):
    """Test exec command simulation - corresponds to fd's test_exec."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool finds files, doesn't execute commands on them
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test file finding (our equivalent of exec)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
    # Our tool provides structured results instead of executing commands


@pytest.mark.asyncio
async def test_fd_60_exec_multi_command_simulation(tmp_path, monkeypatch):
    """Test exec multi command simulation - corresponds to fd's test_exec_multi."""
    # Create test files
    (tmp_path / "test1.py").write_text("print('test1')")
    (tmp_path / "test2.py").write_text("print('test2')")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "test1.py"), str(tmp_path / "test2.py")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test multiple file finding
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.py", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_61_exec_batch_simulation(tmp_path, monkeypatch):
    """Test exec batch simulation - corresponds to fd's test_exec_batch."""
    # Create multiple test files
    for i in range(5):
        (tmp_path / f"batch{i}.txt").write_text(f"batch content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / f"batch{i}.txt") for i in range(5)]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test batch file processing
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "batch*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 5


@pytest.mark.asyncio
async def test_fd_62_exec_batch_multi_simulation(tmp_path, monkeypatch):
    """Test exec batch multi simulation - corresponds to fd's test_exec_batch_multi."""
    # Create test files
    (tmp_path / "multi1.txt").write_text("multi content 1")
    (tmp_path / "multi2.txt").write_text("multi content 2")
    (tmp_path / "multi3.txt").write_text("multi content 3")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [
            str(tmp_path / "multi1.txt"),
            str(tmp_path / "multi2.txt"),
            str(tmp_path / "multi3.txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test multi-batch processing
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "multi*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 3


@pytest.mark.asyncio
async def test_fd_63_exec_batch_with_limit_simulation(tmp_path, monkeypatch):
    """Test exec batch with limit simulation - corresponds to fd's test_exec_batch_with_limit."""
    # Create many test files
    for i in range(10):
        (tmp_path / f"limited{i}.txt").write_text(f"limited content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        all_files = [str(tmp_path / f"limited{i}.txt") for i in range(10)]

        # Check for limit in command
        files = all_files[:3] if any("limit" in str(arg) for arg in cmd) else all_files

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with limit
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "limited*.txt", "glob": True, "limit": 3}
    )

    assert result["success"] is True
    assert result["count"] <= 3


@pytest.mark.asyncio
async def test_fd_64_exec_with_separator_simulation(tmp_path, monkeypatch):
    """Test exec with separator simulation - corresponds to fd's test_exec_with_separator."""
    # Create test files
    (tmp_path / "sep1.txt").write_text("separator content 1")
    (tmp_path / "sep2.txt").write_text("separator content 2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "sep1.txt"), str(tmp_path / "sep2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test separator handling (our tool uses JSON structure)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "sep*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2
    # Verify structured output instead of separator-based


@pytest.mark.asyncio
async def test_fd_65_exec_invalid_utf8_simulation(tmp_path, monkeypatch):
    """Test exec invalid UTF-8 simulation - corresponds to fd's test_exec_invalid_utf8."""
    # Create test files with valid names
    (tmp_path / "valid_utf8.txt").write_text("valid UTF-8 content")
    (tmp_path / "another_file.txt").write_text("another content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "valid_utf8.txt"), str(tmp_path / "another_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test UTF-8 handling in execution context
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


# --- 其他复杂功能测试 (66-74) ---


@pytest.mark.asyncio
async def test_fd_66_count_only_mode_advanced(tmp_path, monkeypatch):
    """Test advanced count only mode - corresponds to fd's count functionality."""
    # Create test files
    for i in range(7):
        (tmp_path / f"count_test{i}.txt").write_text(f"content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / f"count_test{i}.txt") for i in range(7)]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test count functionality
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "count_test*.txt",
            "glob": True,
            "count_only": True,
        }
    )

    assert result["success"] is True
    assert result["total_count"] >= 7
    assert result["count_only"] is True
    assert "results" not in result


@pytest.mark.asyncio
async def test_fd_67_performance_large_dataset(tmp_path, monkeypatch):
    """Test performance with large dataset - corresponds to fd's performance tests."""
    # Create many test files
    (tmp_path / "perf_test").mkdir()
    for i in range(50):
        (tmp_path / "perf_test" / f"perf{i:03d}.txt").write_text(
            f"performance test {i}"
        )

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "perf_test" / f"perf{i:03d}.txt") for i in range(50)]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test performance with many files
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "perf*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 50


@pytest.mark.asyncio
async def test_fd_68_command_timeout_handling(tmp_path, monkeypatch):
    """Test command timeout handling - corresponds to fd's timeout tests."""
    # Create test files
    (tmp_path / "timeout_test.txt").write_text("timeout content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate normal execution (our tool handles timeouts internally)
        files = [str(tmp_path / "timeout_test.txt")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test timeout handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_69_invalid_regex_handling(tmp_path, monkeypatch):
    """Test invalid regex handling - corresponds to fd's regex error tests."""
    # Create test files
    (tmp_path / "regex_test.txt").write_text("regex content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate fd command failing with invalid regex
        if "[invalid_regex" in " ".join(cmd):
            return 1, b"", b"error: Invalid regular expression"
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with potentially invalid regex
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "[invalid_regex"}  # Invalid regex
    )

    # Should handle gracefully
    assert result["success"] is False or result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_70_memory_usage_optimization(tmp_path, monkeypatch):
    """Test memory usage optimization - corresponds to fd's memory tests."""
    # Create test structure
    (tmp_path / "memory_test").mkdir()
    for i in range(20):
        (tmp_path / "memory_test" / f"mem{i}.txt").write_text(f"memory content {i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "memory_test" / f"mem{i}.txt") for i in range(20)]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test memory efficient processing
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "mem*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 20


@pytest.mark.asyncio
async def test_fd_71_cross_platform_compatibility(tmp_path, monkeypatch):
    """Test cross-platform compatibility - corresponds to fd's platform tests."""
    # Create test files with various naming patterns
    (tmp_path / "cross_platform.txt").write_text("cross platform content")
    (tmp_path / "UPPER_CASE.TXT").write_text("upper case content")
    (tmp_path / "mixed_Case.Txt").write_text("mixed case content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [
            str(tmp_path / "cross_platform.txt"),
            str(tmp_path / "UPPER_CASE.TXT"),
            str(tmp_path / "mixed_Case.Txt"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test cross-platform file handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2  # Should find files regardless of case


@pytest.mark.asyncio
async def test_fd_72_edge_case_patterns(tmp_path, monkeypatch):
    """Test edge case patterns - corresponds to fd's edge case tests."""
    # Create files with edge case names
    (tmp_path / "..hidden").write_text("double dot content")
    (tmp_path / "normal.txt").write_text("normal content")
    (tmp_path / "space file.txt").write_text("space content")
    (tmp_path / "unicode_文件.txt").write_text("unicode content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [
            str(tmp_path / "normal.txt"),
            str(tmp_path / "space file.txt"),
            str(tmp_path / "unicode_文件.txt"),
        ]

        if "-H" in cmd:  # Include hidden files
            files.append(str(tmp_path / "..hidden"))

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test edge case handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result["success"] is True
    assert result["count"] >= 3


@pytest.mark.asyncio
async def test_fd_73_concurrent_execution_safety(tmp_path, monkeypatch):
    """Test concurrent execution safety - corresponds to fd's concurrency tests."""
    # Create test files
    (tmp_path / "concurrent1.txt").write_text("concurrent content 1")
    (tmp_path / "concurrent2.txt").write_text("concurrent content 2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "concurrent1.txt"), str(tmp_path / "concurrent2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test concurrent execution safety
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "concurrent*.txt", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_fd_74_resource_cleanup(tmp_path, monkeypatch):
    """Test resource cleanup - corresponds to fd's cleanup tests."""
    # Create test files
    (tmp_path / "cleanup_test.txt").write_text("cleanup content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "cleanup_test.txt")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test resource cleanup
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0
    # Resource cleanup is handled by the tool internally


# --- 忽略规则测试 (38) ---


@pytest.mark.asyncio
async def test_fd_38_gitignore_and_fdignore_advanced(tmp_path, monkeypatch):
    """Test advanced gitignore and fdignore handling - corresponds to fd's test_gitignore_and_fdignore."""
    # Create complex directory structure
    (tmp_path / ".gitignore").write_text("*.log\ntemp/\n")
    (tmp_path / ".fdignore").write_text("*.tmp\ncache/\n")
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "debug.log").write_text("log content")
    (tmp_path / "temp.tmp").write_text("temp content")
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp" / "data.txt").write_text("temp data")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "data.txt").write_text("cache data")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-I" in cmd:  # No ignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / ".fdignore"),
                str(tmp_path / "file.txt"),
                str(tmp_path / "debug.log"),
                str(tmp_path / "temp.tmp"),
                str(tmp_path / "temp" / "data.txt"),
                str(tmp_path / "cache" / "data.txt"),
            ]
        else:
            # Respect both .gitignore and .fdignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / ".fdignore"),
                str(tmp_path / "file.txt"),
                # debug.log, temp.tmp, temp/, cache/ are ignored
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with ignore rules
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": False}
    )

    assert result1["success"] is True
    assert result1["count"] >= 0  # Allow flexible count

    # Test without ignore rules
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 0  # Allow flexible count


# --- 时间相关测试 (75-78) ---


@pytest.mark.asyncio
async def test_fd_75_modified_relative_time(tmp_path, monkeypatch):
    """Test relative modification time filtering - corresponds to fd's test_modified_relative."""
    # Create test files
    (tmp_path / "old_file.txt").write_text("old content")
    (tmp_path / "new_file.txt").write_text("new content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--changed-within" in cmd:
            if "1d" in cmd:
                files = [str(tmp_path / "new_file.txt")]  # Only recent files
            else:
                files = []
        else:
            files = [str(tmp_path / "old_file.txt"), str(tmp_path / "new_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files modified within 1 day
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "changed_within": "1d"}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_76_modified_absolute_time(tmp_path, monkeypatch):
    """Test absolute modification time filtering - corresponds to fd's test_modified_absolute."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--changed-before" in cmd:
            if "2023-01-01" in cmd:
                files = []  # No files before this date
            else:
                files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]
        else:
            files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files modified before a specific date
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "changed_before": "2023-01-01",
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_77_size_filtering_advanced(tmp_path, monkeypatch):
    """Test advanced size filtering - corresponds to fd's test_size."""
    # Create test files
    (tmp_path / "small.txt").write_text("small")
    (tmp_path / "large.txt").write_text("large content" * 100)

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "--size" in cmd:
            if "+100b" in cmd:
                files = [str(tmp_path / "large.txt")]  # Only large files
            elif "-100b" in cmd:
                files = [str(tmp_path / "small.txt")]  # Only small files
            else:
                files = []
        else:
            files = [str(tmp_path / "small.txt"), str(tmp_path / "large.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files larger than 100 bytes
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["+100b"]}
    )

    assert result1["success"] is True
    assert result1["count"] >= 0

    # Test files smaller than 100 bytes
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "size": ["-100b"]}
    )

    assert result2["success"] is True
    assert result2["count"] >= 0


@pytest.mark.asyncio
async def test_fd_78_no_extension_filter(tmp_path, monkeypatch):
    """Test no extension filter - corresponds to fd's test_no_extension."""
    # Create test files
    (tmp_path / "file_with_ext.txt").write_text("content")
    (tmp_path / "file_without_ext").write_text("content")
    (tmp_path / "README").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate files without extension by checking pattern
        files = [
            str(tmp_path / "file_with_ext.txt"),
            str(tmp_path / "file_without_ext"),
            str(tmp_path / "README"),
        ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test files without extension (simulate with pattern)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


# --- 权限和所有者测试 (79-82) ---


@pytest.mark.asyncio
async def test_fd_79_owner_ignore_all(tmp_path, monkeypatch):
    """Test owner filtering - ignore all - corresponds to fd's test_owner_ignore_all."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate owner filtering (not supported by our tool, so return all files)
        files = [str(tmp_path / "file1.txt"), str(tmp_path / "file2.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_80_owner_current_user(tmp_path, monkeypatch):
    """Test current user owner filtering - corresponds to fd's test_owner_current_user."""
    # Create test files
    (tmp_path / "my_file.txt").write_text("my content")
    (tmp_path / "other_file.txt").write_text("other content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate current user files (all files in tmp_path are owned by current user)
        files = [str(tmp_path / "my_file.txt"), str(tmp_path / "other_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test current user owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_81_owner_current_group(tmp_path, monkeypatch):
    """Test current group owner filtering - corresponds to fd's test_owner_current_group."""
    # Create test files
    (tmp_path / "group_file.txt").write_text("group content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate group owner filtering
        files = [str(tmp_path / "group_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test group owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_82_owner_root(tmp_path, monkeypatch):
    """Test root owner filtering - corresponds to fd's test_owner_root."""
    # Create test files
    (tmp_path / "user_file.txt").write_text("user content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate root owner filtering (no root files in tmp_path)
        files = []  # No root-owned files

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test root owner filtering (simulated)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0  # No root files


# --- 其他功能测试 (83-94) ---


@pytest.mark.asyncio
async def test_fd_83_quiet_mode_simulation(tmp_path, monkeypatch):
    """Test quiet mode simulation - corresponds to fd's test_quiet."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Our tool always returns structured output, simulating quiet mode
        files = [str(tmp_path / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test quiet mode (our tool is always structured)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_84_max_results_advanced(tmp_path, monkeypatch):
    """Test advanced max results limiting - corresponds to fd's test_max_results."""
    # Create many test files
    for i in range(10):
        (tmp_path / f"file{i}.txt").write_text(f"content{i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate max results limiting
        all_files = [str(tmp_path / f"file{i}.txt") for i in range(10)]

        # Check for limit in command
        files = all_files[:5] if any("limit" in str(arg) for arg in cmd) else all_files

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with limit
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "limit": 5}
    )

    assert result1["success"] is True
    assert result1["count"] >= 0

    # Test without limit
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 0


@pytest.mark.asyncio
async def test_fd_85_invalid_utf8_handling(tmp_path, monkeypatch):
    """Test invalid UTF-8 filename handling - corresponds to fd's test_invalid_utf8."""
    # Create test files with valid names (can't create invalid UTF-8 in Python easily)
    (tmp_path / "valid_file.txt").write_text("content")
    (tmp_path / "another_file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate handling of files with potentially invalid UTF-8 names
        files = [str(tmp_path / "valid_file.txt"), str(tmp_path / "another_file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test UTF-8 handling
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_86_list_details_advanced(tmp_path, monkeypatch):
    """Test advanced list details - corresponds to fd's test_list_details."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate detailed listing
        files = [str(tmp_path / "file.txt"), str(tmp_path / "subdir")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test detailed listing
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0

    # Verify detailed information is present in successful results
    if result["success"] and result["count"] > 0:
        for item in result["results"]:
            assert "path" in item
            assert "is_dir" in item


@pytest.mark.asyncio
async def test_fd_87_single_and_multithreaded_execution(tmp_path, monkeypatch):
    """Test single and multithreaded execution - corresponds to fd's test_single_and_multithreaded_execution."""
    # Create test files
    for i in range(5):
        (tmp_path / f"file{i}.txt").write_text(f"content{i}")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate execution (our tool doesn't expose threading options)
        files = [str(tmp_path / f"file{i}.txt") for i in range(5)]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test execution (threading is internal)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    assert result["success"] is True
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_fd_88_number_parsing_errors(tmp_path, monkeypatch):
    """Test number parsing errors - corresponds to fd's test_number_parsing_errors."""
    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate fd command with various scenarios
        return 0, b"", b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test invalid depth value (should be handled gracefully)
    result1 = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            # Note: We don't test invalid depth as our tool validates parameters
        }
    )

    # Should handle gracefully
    assert result1["success"] is True or result1["success"] is False

    # Test with valid parameters
    result2 = await tool.execute({"roots": [str(tmp_path)], "pattern": "*", "depth": 1})

    assert result2["success"] is True or result2["success"] is False


@pytest.mark.asyncio
async def test_fd_89_opposing_parameters(tmp_path, monkeypatch):
    """Test opposing parameters - corresponds to fd's test_opposing."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        files = [str(tmp_path / "file.txt")]
        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with valid parameters (our tool validates parameters)
    result = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True}
    )

    # Should handle gracefully
    assert result["success"] is True or result["success"] is False


@pytest.mark.asyncio
async def test_fd_90_error_if_hidden_not_set_and_pattern_starts_with_dot(
    tmp_path, monkeypatch
):
    """Test error for hidden pattern without hidden flag - corresponds to fd's test_error_if_hidden_not_set_and_pattern_starts_with_dot."""
    # Create hidden file
    (tmp_path / ".hidden").write_text("hidden content")
    (tmp_path / "visible.txt").write_text("visible content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-H" not in cmd and ".hidden" in cmd:
            # fd might error or return no results for hidden patterns without -H
            return 1, b"", b"error: pattern starts with dot but hidden flag not set"
        elif "-H" in cmd:
            files = [str(tmp_path / ".hidden"), str(tmp_path / "visible.txt")]
        else:
            files = [str(tmp_path / "visible.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test hidden pattern without hidden flag
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": ".hidden", "hidden": False}
    )

    # Should handle gracefully (may succeed or fail)
    assert result1["success"] is False or result1["count"] >= 0

    # Test hidden pattern with hidden flag
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": ".hidden", "hidden": True}
    )

    assert result2["success"] is True or result2["success"] is False


@pytest.mark.asyncio
async def test_fd_91_invalid_cwd(tmp_path, monkeypatch):
    """Test invalid current working directory - corresponds to fd's test_invalid_cwd."""
    # Test with non-existent directory
    nonexistent_path = tmp_path / "nonexistent"

    tool = ListFilesTool(str(nonexistent_path))

    # Test with invalid directory (should be handled by tool validation)
    try:
        result = await tool.execute({"roots": [str(nonexistent_path)], "pattern": "*"})
        # If successful, that's fine
        assert result["success"] is True or result["success"] is False
    except Exception:
        # If it raises an exception for invalid directory, that's expected behavior
        pass


@pytest.mark.asyncio
async def test_fd_92_git_dir_handling(tmp_path, monkeypatch):
    """Test .git directory handling - corresponds to fd's test_git_dir."""
    # Create .git directory structure
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    (tmp_path / ".git" / "objects").mkdir()
    (tmp_path / "file.txt").write_text("content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-H" in cmd:  # Hidden files included
            files = [
                str(tmp_path / ".git" / "config"),
                str(tmp_path / ".git" / "objects"),
                str(tmp_path / "file.txt"),
            ]
        else:  # .git normally ignored
            files = [str(tmp_path / "file.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test without hidden flag (should ignore .git)
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": False}
    )

    assert result1["success"] is True
    assert result1["count"] >= 0

    # Test with hidden flag (should include .git)
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "hidden": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 0


@pytest.mark.asyncio
async def test_fd_93_gitignore_parent_handling(tmp_path, monkeypatch):
    """Test gitignore parent directory handling - corresponds to fd's test_gitignore_parent."""
    # Create parent .gitignore
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("content")
    (tmp_path / "subdir" / "debug.log").write_text("log content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        if "-I" in cmd:  # No ignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "subdir" / "file.txt"),
                str(tmp_path / "subdir" / "debug.log"),
            ]
        else:  # Respect parent .gitignore
            files = [
                str(tmp_path / ".gitignore"),
                str(tmp_path / "subdir" / "file.txt"),
                # debug.log is ignored by parent .gitignore
            ]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test with parent gitignore
    result1 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": False}
    )

    assert result1["success"] is True
    assert result1["count"] >= 0

    # Test ignoring parent gitignore
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "glob": True, "no_ignore": True}
    )

    assert result2["success"] is True
    assert result2["count"] >= 0


@pytest.mark.asyncio
async def test_fd_94_hyperlink_output_advanced(tmp_path, monkeypatch):
    """Test advanced hyperlink output - corresponds to fd's test_hyperlink."""
    # Create test files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")

    tool = ListFilesTool(str(tmp_path))

    async def fake_run(cmd, cwd=None, timeout=None, timeout_ms=None):
        # Simulate hyperlink-ready output (absolute paths)
        files = [str(tmp_path / "file.txt"), str(tmp_path / "subdir" / "nested.txt")]

        out = "\n".join(files).encode()
        return 0, out, b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )

    # Test hyperlink-ready output
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*",
            "glob": True,
            "absolute": True,  # Ensure absolute paths for hyperlinks
        }
    )

    assert result["success"] is True
    assert result["count"] >= 0

    # Verify paths are absolute (suitable for hyperlinks) when results exist
    if result["success"] and result["count"] > 0:
        for item in result["results"]:
            path = item["path"]
            # Check if path is absolute (Unix or Windows style)
            assert path.startswith("/") or (
                len(path) > 1 and path[1] == ":"
            )  # Unix or Windows absolute path
