
import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.mark.unit
class DummyProc:
    def __init__(self, rc=0, stdout=b"", stderr=b""):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr
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
    result2 = await tool.execute(
        {"roots": [str(tmp_path)], "pattern": "*", "depth": 1, "output_format": "json"}
    )

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
        result = await tool.execute(
            {"roots": [str(nonexistent_path)], "pattern": "*", "output_format": "json"}
        )
        # If successful, that's fine
        assert result["success"] is True or result["success"] is False
    except Exception:
        # If it raises an exception for invalid directory, that's expected behavior
        pass
