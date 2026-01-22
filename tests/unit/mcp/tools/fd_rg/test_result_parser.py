#!/usr/bin/env python3
"""
Unit tests for fd_rg result parsers.

Tests the FdResultParser, RgResultParser, and RgResultTransformer classes.
"""

from __future__ import annotations

import json

from tree_sitter_analyzer.mcp.tools.fd_rg import (
    FdResultParser,
    RgResultParser,
    RgResultTransformer,
)


class TestFdResultParser:
    """Tests for FdResultParser."""

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        parser = FdResultParser()
        result = parser.parse(b"")
        assert result == []

    def test_parse_file_list(self):
        """Test parsing file list."""
        output = b"src/main.py\nsrc/utils.py\ntests/test_main.py\n"
        parser = FdResultParser()
        result = parser.parse(output)

        assert len(result) == 3
        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "tests/test_main.py" in result

    def test_parse_with_limit(self):
        """Test parsing with result limit."""
        output = b"file1.py\nfile2.py\nfile3.py\nfile4.py\nfile5.py\n"
        parser = FdResultParser()
        result = parser.parse(output, limit=3)

        assert len(result) == 3
        assert result == ["file1.py", "file2.py", "file3.py"]

    def test_parse_filters_empty_lines(self):
        """Test that empty lines are filtered out."""
        output = b"file1.py\n\nfile2.py\n  \nfile3.py\n"
        parser = FdResultParser()
        result = parser.parse(output)

        assert len(result) == 3
        assert result == ["file1.py", "file2.py", "file3.py"]


class TestRgResultParser:
    """Tests for RgResultParser."""

    def test_parse_json_matches_empty(self):
        """Test parsing empty JSON output."""
        parser = RgResultParser()
        result = parser.parse_json_matches(b"")
        assert result == []

    def test_parse_json_matches_single_match(self):
        """Test parsing single match."""
        match_event = {
            "type": "match",
            "data": {
                "path": {"text": "src/main.py"},
                "line_number": 42,
                "lines": {"text": "    # TODO: Fix this\n"},
                "submatches": [{"start": 6, "end": 10}],
            },
        }
        output = json.dumps(match_event).encode("utf-8")

        parser = RgResultParser()
        result = parser.parse_json_matches(output)

        assert len(result) == 1
        assert result[0]["file"] == "src/main.py"
        assert result[0]["line"] == 42
        assert "TODO" in result[0]["text"]
        assert result[0]["matches"] == [[6, 10]]

    def test_parse_json_matches_multiple_matches(self):
        """Test parsing multiple matches."""
        events = [
            {
                "type": "match",
                "data": {
                    "path": {"text": "file1.py"},
                    "line_number": 1,
                    "lines": {"text": "match1\n"},
                    "submatches": [{"start": 0, "end": 6}],
                },
            },
            {
                "type": "match",
                "data": {
                    "path": {"text": "file2.py"},
                    "line_number": 2,
                    "lines": {"text": "match2\n"},
                    "submatches": [{"start": 0, "end": 6}],
                },
            },
        ]
        output = b"\n".join(json.dumps(e).encode("utf-8") for e in events)

        parser = RgResultParser()
        result = parser.parse_json_matches(output)

        assert len(result) == 2
        assert result[0]["file"] == "file1.py"
        assert result[1]["file"] == "file2.py"

    def test_parse_json_matches_skips_non_match_events(self):
        """Test that non-match events are skipped."""
        events = [
            {"type": "begin", "data": {}},
            {
                "type": "match",
                "data": {
                    "path": {"text": "file.py"},
                    "line_number": 1,
                    "lines": {"text": "match\n"},
                    "submatches": [],
                },
            },
            {"type": "end", "data": {}},
        ]
        output = b"\n".join(json.dumps(e).encode("utf-8") for e in events)

        parser = RgResultParser()
        result = parser.parse_json_matches(output)

        assert len(result) == 1
        assert result[0]["file"] == "file.py"

    def test_parse_count_output_empty(self):
        """Test parsing empty count output."""
        parser = RgResultParser()
        result = parser.parse_count_output(b"")
        assert result == {"__total__": 0}

    def test_parse_count_output_single_file(self):
        """Test parsing count output for single file."""
        output = b"src/main.py:5\n"
        parser = RgResultParser()
        result = parser.parse_count_output(output)

        assert result["src/main.py"] == 5
        assert result["__total__"] == 5

    def test_parse_count_output_multiple_files(self):
        """Test parsing count output for multiple files."""
        output = b"file1.py:3\nfile2.py:7\nfile3.py:2\n"
        parser = RgResultParser()
        result = parser.parse_count_output(output)

        assert result["file1.py"] == 3
        assert result["file2.py"] == 7
        assert result["file3.py"] == 2
        assert result["__total__"] == 12


class TestRgResultTransformer:
    """Tests for RgResultTransformer."""

    def test_group_by_file_empty(self):
        """Test grouping empty matches."""
        transformer = RgResultTransformer()
        result = transformer.group_by_file([])

        assert result["success"] is True
        assert result["count"] == 0
        assert result["files"] == []

    def test_group_by_file_single_file(self):
        """Test grouping matches from single file."""
        matches = [
            {"file": "test.py", "line": 1, "text": "match1", "matches": []},
            {"file": "test.py", "line": 2, "text": "match2", "matches": []},
        ]

        transformer = RgResultTransformer()
        result = transformer.group_by_file(matches)

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["files"]) == 1
        assert result["files"][0]["file"] == "test.py"
        assert result["files"][0]["match_count"] == 2
        assert len(result["files"][0]["matches"]) == 2

    def test_group_by_file_multiple_files(self):
        """Test grouping matches from multiple files."""
        matches = [
            {"file": "file1.py", "line": 1, "text": "match1", "matches": []},
            {"file": "file2.py", "line": 1, "text": "match2", "matches": []},
            {"file": "file1.py", "line": 2, "text": "match3", "matches": []},
        ]

        transformer = RgResultTransformer()
        result = transformer.group_by_file(matches)

        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["files"]) == 2

    def test_optimize_paths_empty(self):
        """Test optimizing empty matches."""
        transformer = RgResultTransformer()
        result = transformer.optimize_paths([])
        assert result == []

    def test_optimize_paths_removes_common_prefix(self):
        """Test that common prefix is removed."""
        matches = [
            {"file": "/home/user/project/src/file1.py", "line": 1},
            {"file": "/home/user/project/src/file2.py", "line": 2},
        ]

        transformer = RgResultTransformer()
        result = transformer.optimize_paths(matches)

        # Common prefix should be removed
        assert not result[0]["file"].startswith("/home/user/project/")
        assert not result[1]["file"].startswith("/home/user/project/")

    def test_summarize_empty(self):
        """Test summarizing empty matches."""
        transformer = RgResultTransformer()
        result = transformer.summarize([])

        assert result["total_matches"] == 0
        assert result["total_files"] == 0
        assert result["summary"] == "No matches found"
        assert result["top_files"] == []

    def test_summarize_single_file(self):
        """Test summarizing matches from single file."""
        matches = [
            {"file": "test.py", "line": 1, "text": "match1"},
            {"file": "test.py", "line": 2, "text": "match2"},
        ]

        transformer = RgResultTransformer()
        result = transformer.summarize(matches, max_files=10, max_total_lines=50)

        assert result["total_matches"] == 2
        assert result["total_files"] == 1
        assert len(result["top_files"]) == 1
        assert result["top_files"][0]["match_count"] == 2

    def test_summarize_respects_max_files(self):
        """Test that summarize respects max_files limit."""
        matches = [
            {"file": f"file{i}.py", "line": 1, "text": "match"} for i in range(20)
        ]

        transformer = RgResultTransformer()
        result = transformer.summarize(matches, max_files=5, max_total_lines=50)

        assert result["total_matches"] == 20
        assert result["total_files"] == 20
        assert len(result["top_files"]) == 5
        assert result["truncated"] is True

    def test_create_file_summary_from_count(self):
        """Test creating file summary from count data."""
        count_data = {
            "file1.py": 5,
            "file2.py": 3,
            "__total__": 8,
        }

        transformer = RgResultTransformer()
        result = transformer.create_file_summary_from_count(count_data)

        assert result["success"] is True
        assert result["total_matches"] == 8
        assert result["file_count"] == 2
        assert len(result["files"]) == 2
        assert result["derived_from_count"] is True
