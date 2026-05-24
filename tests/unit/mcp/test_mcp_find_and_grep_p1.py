import json

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


def _mock_find_and_grep_json_run(monkeypatch, file_path, line_text, match_text):
    """Mock fd then rg JSON output for a single matched file."""
    rg_json = {
        "type": "match",
        "data": {
            "path": {"text": str(file_path)},
            "lines": {"text": line_text},
            "line_number": 1,
            "submatches": [{"match": {"text": match_text}, "start": 0, "end": 5}],
        },
    }

    async def fake_run(cmd, input_data=None, timeout_ms=None):
        if cmd and cmd[0] == "fd":
            return 0, str(file_path).encode(), b""
        if cmd and cmd[0] == "rg":
            out = (json.dumps(rg_json) + "\n").encode()
            return 0, out, b""
        return 1, b"", b"Unknown command"

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture", fake_run
    )


@pytest.mark.unit
@pytest.mark.unit
def test_find_and_grep_validation_requires_roots_and_query(tmp_path):
    """``query`` is always required; ``roots`` is required only when no
    project_root is configured (post-1.12 fallback)."""
    tool = FindAndGrepTool(str(tmp_path))
    # query missing → ValueError (regardless of roots / fallback)
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": [str(tmp_path)]})
    # No-project-root + missing roots → ValueError
    no_root_tool = FindAndGrepTool(None)
    with pytest.raises(ValueError):
        no_root_tool.validate_arguments({"query": "foo"})
    # Tool with project_root + missing roots → succeeds via fallback
    tool.validate_arguments({"query": "foo"})


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
            "output_format": "json",
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["line"] == 1


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
@pytest.mark.asyncio
async def test_find_and_grep_optimize_paths(monkeypatch, tmp_path):
    """Test FindAndGrepTool with path optimization enabled."""
    tool = FindAndGrepTool(str(tmp_path))

    # Create test files with long paths
    long_path = tmp_path / "very" / "long" / "nested" / "directory"
    long_path.mkdir(parents=True)
    f1 = long_path / "test.txt"
    f1.write_text("hello world\n", encoding="utf-8")
    _mock_find_and_grep_json_run(monkeypatch, f1, "hello world\n", "hello")

    # Test with path optimization enabled
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "hello",
            "optimize_paths": True,
            "output_format": "json",
        }
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

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "test", "output_format": "json"}
    )

    assert result["success"] is False
    assert result["error"] == "fd: permission denied"
    assert result["returncode"] == 1


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
