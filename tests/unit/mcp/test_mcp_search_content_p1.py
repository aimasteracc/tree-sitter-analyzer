import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
@pytest.mark.unit
def test_search_content_validation_requires_query():
    """Test that SearchContentTool validation fails when query parameter is missing."""
    tool = SearchContentTool(str(Path.cwd()))
    with pytest.raises(ValueError):
        tool.validate_arguments({"roots": [str(Path.cwd())]})


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

    result = await tool.execute(
        {"files": [str(f1)], "query": "hello", "output_format": "json"}
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["agent_summary"]["mode"] == "normal"
    assert result["agent_summary"]["total_matches"] == 1
    assert result["results"][0]["line"] == 1  # Updated field name


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
            "output_format": "json",
        }
    )
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(f1)


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
    assert result["agent_summary"]["mode"] == "count_only"
    assert result["agent_summary"]["total_matches"] == 20
    assert result["agent_summary"]["file_count"] == 3


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
    assert result["agent_summary"]["mode"] == "summary"
    assert result["agent_summary"]["file_count"] == 1


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

    result = await tool.execute(
        {"roots": [str(tmp_path)], "query": "[invalid", "output_format": "json"}
    )

    assert result["success"] is False
    assert result["error"] == "rg: invalid regex"
    assert result["returncode"] == 2


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

    # Results are embedded in toon_content or available as 'results' key
    assert "results" in result or "toon_content" in result


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
    assert result["agent_summary"]["mode"] == "group_by_file"
    assert result["agent_summary"]["file_count"] == 1
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

    result = await tool.execute(
        {"files": [str(test_file)], "query": "import", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["file"] == str(test_file)


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
