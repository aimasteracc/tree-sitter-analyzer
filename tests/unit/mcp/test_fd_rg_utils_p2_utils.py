#!/usr/bin/env python3
"""
Tests for fd_rg_utils module - utility functions.

This module tests the shared utilities for fd and ripgrep
result processing, parallel execution, and constants.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils


class TestParseRgJsonLinesToMatches:
    """Tests for parse_rg_json_lines_to_matches function."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON output."""
        json_line = b'{"type":"match","data":{"path":{"text":"file.py"},"line_number":1,"lines":{"text":"test"},"submatches":[]}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 1
        assert result[0]["file"] == "file.py"
        assert result[0]["line"] == 1
        assert result[0]["text"] == "test"

    def test_parse_multiple_lines(self):
        """Test parsing multiple JSON lines."""
        json_lines = b'{"type":"match","data":{"path":{"text":"file1.py"},"line_number":1,"lines":{"text":"test"},"submatches":[]}}\n{"type":"match","data":{"path":{"text":"file2.py"},"line_number":2,"lines":{"text":"test"},"submatches":[]}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_lines)
        assert len(result) == 2
        assert result[0]["file"] == "file1.py"
        assert result[1]["file"] == "file2.py"

    def test_parse_non_match_event(self):
        """Test that non-match events are skipped."""
        json_line = b'{"type":"begin","data":{}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 0

    def test_parse_invalid_json(self):
        """Test that invalid JSON is skipped."""
        json_line = b"invalid json"
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 0

    def test_parse_empty_lines(self):
        """Test that empty lines are skipped."""
        json_lines = b"\n\n"
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_lines)
        assert len(result) == 0

    def test_parse_with_submatches(self):
        """Test parsing with submatches."""
        json_line = b'{"type":"match","data":{"path":{"text":"file.py"},"submatches":[{"start":0,"end":5}]}}'
        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_line)
        assert len(result) == 1
        assert "matches" in result[0]
        assert result[0]["matches"] == [[0, 5]]

    def test_parse_hard_cap(self):
        """Test that results are capped at hard limit."""
        # Create more than hard cap results
        json_lines = b"\n".join(
            [b'{"type":"match","data":{"path":{"text":"file.py"}}}']
            * (fd_rg_utils.MAX_RESULTS_HARD_CAP + 10)
        )

        result = fd_rg_utils.parse_rg_json_lines_to_matches(json_lines)
        assert len(result) == fd_rg_utils.MAX_RESULTS_HARD_CAP


class TestGroupMatchesByFile:
    """Tests for group_matches_by_file function."""

    def test_group_empty_matches(self):
        """Test grouping empty matches."""
        result = fd_rg_utils.group_matches_by_file([])
        assert result["success"] is True
        assert result["count"] == 0
        assert result["files"] == []

    def test_group_single_file(self):
        """Test grouping matches from single file."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "test1"},
            {"file": "file1.py", "line": 2, "text": "test2"},
        ]
        result = fd_rg_utils.group_matches_by_file(matches)
        assert result["count"] == 2
        assert len(result["files"]) == 1
        assert result["files"][0]["file"] == "file1.py"
        assert result["files"][0]["match_count"] == 2

    def test_group_multiple_files(self):
        """Test grouping matches from multiple files."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "test1"},
            {"file": "file2.py", "line": 1, "text": "test2"},
            {"file": "file1.py", "line": 2, "text": "test3"},
        ]
        result = fd_rg_utils.group_matches_by_file(matches)
        assert result["count"] == 3
        assert len(result["files"]) == 2
        assert result["files"][0]["match_count"] == 2
        assert result["files"][1]["match_count"] == 1


class TestOptimizeMatchPaths:
    """Tests for optimize_match_paths function."""

    def test_optimize_empty_matches(self):
        """Test optimizing empty matches."""
        result = fd_rg_utils.optimize_match_paths([])
        assert result == []

    def test_optimize_single_match(self):
        """Test optimizing single match."""
        matches = [{"file": "/path/to/file.py", "line": 1}]
        result = fd_rg_utils.optimize_match_paths(matches)
        assert len(result) == 1
        # Path should be optimized
        assert result[0]["file"] == "/path/to/file.py"

    def test_optimize_with_common_prefix(self):
        """Test optimizing with common prefix."""
        matches = [
            {"file": "/common/path/file1.py", "line": 1},
            {"file": "/common/path/file2.py", "line": 1},
        ]
        result = fd_rg_utils.optimize_match_paths(matches)
        assert len(result) == 2
        # Common prefix should be removed, leaving relative paths
        assert "file1.py" in result[0]["file"] or result[0]["file"] == "file1.py"
        assert "file2.py" in result[1]["file"] or result[1]["file"] == "file2.py"

    def test_optimize_with_long_path(self):
        """Test optimizing with long path."""
        matches = [
            {
                "file": "/very/long/path/that/goes/deep/into/many/directories/to/file.py",
                "line": 1,
            }
        ]
        result = fd_rg_utils.optimize_match_paths(matches)
        assert len(result) == 1
        # Long path should be shortened
        assert "..." in result[0]["file"]


class TestSummarizeSearchResults:
    """Tests for summarize_search_results function."""

    def test_summarize_empty_results(self):
        """Test summarizing empty results."""
        result = fd_rg_utils.summarize_search_results([])
        assert result["total_matches"] == 0
        assert result["total_files"] == 0
        assert result["summary"] == "No matches found"
        assert result["top_files"] == []

    def test_summarize_single_file(self):
        """Test summarizing single file."""
        matches = [
            {"file": "file.py", "line": 1, "text": "test1"},
            {"file": "file.py", "line": 2, "text": "test2"},
        ]
        result = fd_rg_utils.summarize_search_results(matches, max_files=5)
        assert result["total_matches"] == 2
        assert result["total_files"] == 1
        assert result["top_files"][0]["file"] == "file.py"
        assert result["top_files"][0]["match_count"] == 2

    def test_summarize_multiple_files(self):
        """Test summarizing multiple files."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "test"},
            {"file": "file2.py", "line": 1, "text": "test"},
        ]
        result = fd_rg_utils.summarize_search_results(matches, max_files=10)
        assert result["total_matches"] == 2
        assert result["total_files"] == 2
        assert len(result["top_files"]) == 2

    def test_summarize_with_max_files_limit(self):
        """Test summarizing with max files limit."""
        matches = [
            {"file": f"file{i}.py", "line": 1, "text": "test"} for i in range(15)
        ]
        result = fd_rg_utils.summarize_search_results(matches, max_files=5)
        assert result["total_files"] == 15
        assert len(result["top_files"]) == 5

    def test_summarize_truncates_long_lines(self):
        """Test that long lines are truncated."""
        matches = [
            {
                "file": "file.py",
                "line": 1,
                "text": "a" * 100,  # Very long line
            }
        ]
        result = fd_rg_utils.summarize_search_results(matches)
        assert "..." in result["top_files"][0]["sample_lines"][0]


class TestParseRgCountOutput:
    """Tests for parse_rg_count_output function."""

    def test_parse_valid_output(self):
        """Test parsing valid count output."""
        output = b"file1.py:10\nfile2.py:5\n"
        result = fd_rg_utils.parse_rg_count_output(output)
        assert result["file1.py"] == 10
        assert result["file2.py"] == 5
        assert result["__total__"] == 15

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        result = fd_rg_utils.parse_rg_count_output(b"")
        assert result == {"__total__": 0}

    def test_parse_with_whitespace_lines(self):
        """Test that whitespace lines are skipped."""
        output = b"file1.py:10\n  \nfile2.py:5\n"
        result = fd_rg_utils.parse_rg_count_output(output)
        assert result["file1.py"] == 10
        assert result["file2.py"] == 5
        assert result["__total__"] == 15

    def test_parse_invalid_format(self):
        """Test that invalid format lines are skipped."""
        output = b"invalid line\nfile1.py:10\n"
        result = fd_rg_utils.parse_rg_count_output(output)
        assert "file1.py" in result
        assert result["__total__"] == 10


class TestExtractFileListFromCountData:
    """Tests for extract_file_list_from_count_data function."""

    def test_extract_file_list(self):
        """Test extracting file list from count data."""
        count_data = {
            "file1.py": 10,
            "file2.py": 5,
            "__total__": 15,
        }
        result = fd_rg_utils.extract_file_list_from_count_data(count_data)
        assert len(result) == 2
        assert "file1.py" in result
        assert "file2.py" in result
        assert "__total__" not in result


class TestCreateFileSummaryFromCountData:
    """Tests for create_file_summary_from_count_data function."""

    def test_create_summary(self):
        """Test creating file summary from count data."""
        count_data = {
            "file1.py": 10,
            "file2.py": 5,
            "__total__": 15,
        }
        result = fd_rg_utils.create_file_summary_from_count_data(count_data)
        assert result["success"] is True
        assert result["total_matches"] == 15
        assert result["file_count"] == 2
        assert len(result["files"]) == 2
        assert result["derived_from_count"] is True


class TestSplitRootsForParallelProcessing:
    """Tests for split_roots_for_parallel_processing function."""

    def test_split_empty_roots(self):
        """Test splitting empty roots."""
        result = fd_rg_utils.split_roots_for_parallel_processing([], max_chunks=4)
        assert result == []

    def test_split_single_root(self):
        """Test splitting single root."""
        result = fd_rg_utils.split_roots_for_parallel_processing(
            ["/path"], max_chunks=4
        )
        assert len(result) == 1
        assert result[0] == ["/path"]

    def test_split_multiple_roots(self):
        """Test splitting multiple roots."""
        roots = [f"/path{i}" for i in range(10)]
        result = fd_rg_utils.split_roots_for_parallel_processing(roots, max_chunks=4)
        assert len(result) == 4

    def test_split_with_remainder(self):
        """Test splitting with remainder."""
        roots = [f"/path{i}" for i in range(9)]  # 9 roots
        result = fd_rg_utils.split_roots_for_parallel_processing(roots, max_chunks=4)
        assert len(result) == 4
        # chunk_size = 9 // 4 = 2, remainder = 9 % 4 = 1
        # First chunk gets extra item due to remainder, so it has 3 roots
        # Remaining 3 chunks have 2 roots each
        # So chunks are: [3, 2, 2, 2]
        assert len(result[0]) == 3
        assert len(result[1]) == 2
        assert len(result[2]) == 2
        assert len(result[3]) == 2


class TestRunParallelRgSearches:
    """Tests for run_parallel_rg_searches function."""

    @pytest.mark.asyncio
    async def test_run_single_command(self):
        """Test running single command."""
        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
        ):
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            commands = [["rg", "test"]]
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, max_concurrent=2
            )

            assert len(results) == 1
            assert results[0] == (0, b"output", b"")

    @pytest.mark.asyncio
    async def test_run_multiple_commands(self):
        """Test running multiple commands."""
        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
        ):
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            commands = [["rg", "test1"], ["rg", "test2"]]
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, max_concurrent=2
            )

            assert len(results) == 2
            assert results[0] == (0, b"output", b"")
            assert results[1] == (0, b"output", b"")

    @pytest.mark.asyncio
    async def test_run_with_timeout(self):
        """Test running with timeout."""
        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch("asyncio.create_subprocess_exec") as mock_subprocess,
        ):
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output", b"")
            mock_subprocess.return_value = mock_proc

            commands = [["rg", "test"]]
            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, timeout_ms=5000, max_concurrent=2
            )

            assert len(results) == 1


class TestMergeRgResults:
    """Tests for merge_rg_results function."""

    def test_merge_successful_results(self):
        """Test merging successful results."""
        results = [
            (0, b"output1", b""),
            (0, b"output2", b""),
        ]
        rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_mode=False)
        assert rc == 0
        assert b"output1" in out
        assert b"output2" in out

    def test_merge_count_only_results(self):
        """Test merging count-only results."""
        results = [
            (0, b"file1.py:10\n", b""),
            (0, b"file2.py:5\n", b""),
        ]
        rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_mode=True)
        assert rc == 0
        assert b"file1.py:10" in out
        assert b"file2.py:5" in out

    def test_merge_with_failure(self):
        """Test merging with a failure."""
        results = [
            (0, b"output1", b""),  # First result has output (rc=0)
            (1, b"", b"error"),  # Second result is error (rc=1)
        ]
        rc, out, err = fd_rg_utils.merge_rg_results(results, count_only_mode=False)
        # When first result has output (rc=0 with stdout), has_matches should be True
        # So return code should be 0, not 1
        assert rc == 0
        assert b"output1" in out


class TestNormalizeMaxFilesize:
    """Tests for normalize_max_filesize function."""

    def test_normalize_valid_size(self):
        """Test normalizing valid size."""
        result = fd_rg_utils.normalize_max_filesize("10M")
        assert result == "10M"

    def test_normalize_none(self):
        """Test normalizing None."""
        result = fd_rg_utils.normalize_max_filesize(None)
        assert result == "10M"  # Default value

    def test_normalize_above_hard_cap(self):
        """Test normalizing size above hard cap."""
        result = fd_rg_utils.normalize_max_filesize("500M")
        assert result == "200M"  # Capped at hard limit

    def test_normalize_invalid_format(self):
        """Test normalizing invalid format."""
        result = fd_rg_utils.normalize_max_filesize("invalid")
        assert result == "10M"  # Default value


class TestConstants:
    """Tests for module constants."""

    def test_max_results_hard_cap(self):
        """Test MAX_RESULTS_HARD_CAP constant."""
        assert fd_rg_utils.MAX_RESULTS_HARD_CAP == 10000

    def test_default_results_limit(self):
        """Test DEFAULT_RESULTS_LIMIT constant."""
        assert fd_rg_utils.DEFAULT_RESULTS_LIMIT == 2000

    def test_default_rg_max_filesize(self):
        """Test DEFAULT_RG_MAX_FILESIZE constant."""
        assert fd_rg_utils.DEFAULT_RG_MAX_FILESIZE == "10M"

    def test_rg_max_filesize_hard_cap_bytes(self):
        """Test RG_MAX_FILESIZE_HARD_CAP_BYTES constant."""
        assert fd_rg_utils.RG_MAX_FILESIZE_HARD_CAP_BYTES == 200 * 1024 * 1024

    def test_default_rg_timeout_ms(self):
        """Test DEFAULT_RG_TIMEOUT_MS constant."""
        assert fd_rg_utils.DEFAULT_RG_TIMEOUT_MS == 4000

    def test_rg_timeout_hard_cap_ms(self):
        """Test RG_TIMEOUT_HARD_CAP_MS constant."""
        assert fd_rg_utils.RG_TIMEOUT_HARD_CAP_MS == 30000
