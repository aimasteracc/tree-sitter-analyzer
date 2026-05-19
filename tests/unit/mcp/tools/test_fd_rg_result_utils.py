#!/usr/bin/env python3

import json

from tree_sitter_analyzer.mcp.tools.fd_rg_result_utils import (
    create_file_summary_from_count_data,
    extract_file_list_from_count_data,
    group_matches_by_file,
    optimize_match_paths,
    parse_rg_json_lines_to_matches,
    summarize_search_results,
)


def _rg_match_event(file_path: str, line_number: int, text: str, submatches: list | None = None) -> bytes:
    evt = {
        "type": "match",
        "data": {
            "path": {"text": file_path},
            "line_number": line_number,
            "lines": {"text": text},
            "submatches": submatches or [],
        },
    }
    return json.dumps(evt).encode()


def _rg_summary_event() -> bytes:
    return json.dumps({"type": "summary", "data": {"elapsed_total": {"human": "0.001s"}}}).encode()


class TestParseRgJsonLinesToMatches:
    def test_empty_input(self):
        assert parse_rg_json_lines_to_matches(b"") == []

    def test_whitespace_only(self):
        assert parse_rg_json_lines_to_matches(b"   \n  \n") == []

    def test_single_match(self):
        data = _rg_match_event("src/main.py", 10, "def hello():", [{"start": 4, "end": 9}])
        result = parse_rg_json_lines_to_matches(data)
        assert len(result) == 1
        assert result[0]["file"] == "src/main.py"
        assert result[0]["line"] == 10
        assert result[0]["text"] == "def hello():"
        assert result[0]["matches"] == [[4, 9]]

    def test_skips_non_match_events(self):
        data = _rg_summary_event()
        assert parse_rg_json_lines_to_matches(data) == []

    def test_invalid_json_line(self):
        result = parse_rg_json_lines_to_matches(b"not json\n")
        assert result == []

    def test_multiple_matches(self):
        lines = b"\n".join([
            _rg_match_event("a.py", 1, "foo"),
            _rg_match_event("b.py", 5, "bar"),
        ])
        result = parse_rg_json_lines_to_matches(lines)
        assert len(result) == 2
        assert result[0]["file"] == "a.py"
        assert result[1]["file"] == "b.py"

    def test_missing_path_text_skipped(self):
        evt = {"type": "match", "data": {"path": {}, "line_number": 1, "lines": {"text": "x"}}}
        result = parse_rg_json_lines_to_matches(json.dumps(evt).encode())
        assert result == []

    def test_missing_data_skipped(self):
        evt = {"type": "match", "data": {}}
        result = parse_rg_json_lines_to_matches(json.dumps(evt).encode())
        assert result == []

    def test_hard_cap_enforced(self):
        events = b"\n".join(
            _rg_match_event(f"f{i}.py", i, f"line {i}") for i in range(10001)
        )
        result = parse_rg_json_lines_to_matches(events)
        assert len(result) == 10000

    def test_line_normalization(self):
        evt = _rg_match_event("a.py", 1, "  hello   world  ")
        result = parse_rg_json_lines_to_matches(evt)
        assert result[0]["text"] == "hello world"

    def test_unicode_handling(self):
        evt = _rg_match_event("a.py", 1, "日本語テスト")
        result = parse_rg_json_lines_to_matches(evt)
        assert result[0]["text"] == "日本語テスト"

    def test_invalid_utf8_replaced(self):
        raw = b'{"type":"match","data":{"path":{"text":"a.py"},"line_number":1,"lines":{"text":"\xff\xfe"},"submatches":[]}}\n'
        result = parse_rg_json_lines_to_matches(raw)
        assert len(result) == 1


class TestGroupMatchesByFile:
    def test_empty_input(self):
        result = group_matches_by_file([])
        assert result["success"] is True
        assert result["count"] == 0
        assert result["files"] == []

    def test_single_match(self):
        matches = [{"file": "a.py", "line": 1, "text": "hello", "matches": []}]
        result = group_matches_by_file(matches)
        assert result["count"] == 1
        assert len(result["files"]) == 1
        assert result["files"][0]["file"] == "a.py"
        assert result["files"][0]["match_count"] == 1

    def test_multiple_files(self):
        matches = [
            {"file": "a.py", "line": 1, "text": "hello", "matches": []},
            {"file": "b.py", "line": 5, "text": "world", "matches": []},
            {"file": "a.py", "line": 3, "text": "foo", "matches": []},
        ]
        result = group_matches_by_file(matches)
        assert result["count"] == 3
        assert len(result["files"]) == 2

    def test_fallback_keys(self):
        matches = [{"line_number": 10, "line": "text", "submatches": [[0, 4]]}]
        result = group_matches_by_file(matches)
        assert result["count"] == 1
        assert result["files"][0]["file"] == "unknown"


class TestOptimizeMatchPaths:
    def test_empty_input(self):
        assert optimize_match_paths([]) == []

    def test_common_prefix_removed(self):
        matches = [
            {"file": "/home/user/project/src/a.py"},
            {"file": "/home/user/project/lib/b.py"},
        ]
        result = optimize_match_paths(matches)
        assert result[0]["file"] == "src/a.py"
        assert result[1]["file"] == "lib/b.py"

    def test_no_common_prefix(self):
        matches = [{"file": "a.py"}, {"file": "b.py"}]
        result = optimize_match_paths(matches)
        assert result[0]["file"] == "a.py"

    def test_deep_path_shortened(self):
        matches = [{"file": "/a/b/c/d/e/f/g/h.py"}]
        result = optimize_match_paths(matches)
        assert "..." in result[0]["file"]

    def test_no_file_key(self):
        matches = [{"line": 1, "text": "x"}]
        result = optimize_match_paths(matches)
        assert len(result) == 1


class TestSummarizeSearchResults:
    def test_empty_input(self):
        result = summarize_search_results([])
        assert result["total_matches"] == 0
        assert result["total_files"] == 0
        assert result["summary"] == "No matches found"
        assert result["top_files"] == []

    def test_single_file(self):
        matches = [{"file": "a.py", "line": 1, "text": "hello world"}]
        result = summarize_search_results(matches)
        assert result["total_matches"] == 1
        assert result["total_files"] == 1
        assert result["truncated"] is False

    def test_max_files_limit(self):
        matches = [{"file": f"f{i}.py", "line": 1, "text": "x"} for i in range(15)]
        result = summarize_search_results(matches, max_files=3)
        assert len(result["top_files"]) == 3
        assert result["truncated"] is True

    def test_line_truncation(self):
        long_text = "x" * 100
        matches = [{"file": "a.py", "line": 1, "text": long_text}]
        result = summarize_search_results(matches)
        sample = result["top_files"][0]["sample_lines"]
        assert any("..." in s for s in sample)

    def test_empty_text_uses_count_fallback(self):
        matches = [{"file": "a.py", "line": 1, "text": ""}]
        result = summarize_search_results(matches)
        sample = result["top_files"][0]["sample_lines"]
        assert any("matches" in s for s in sample)

    def test_remaining_lines_budget(self):
        matches = [
            {"file": "a.py", "line": i, "text": f"line {i}"}
            for i in range(10)
        ]
        result = summarize_search_results(matches, max_total_lines=2)
        total_sample_lines = sum(
            len(f["sample_lines"]) for f in result["top_files"]
        )
        assert total_sample_lines <= 2

    def test_summary_text_few_files(self):
        matches = [{"file": "a.py", "line": 1, "text": "x"}]
        result = summarize_search_results(matches, max_files=10)
        assert "1 matches in 1 files" in result["summary"]

    def test_summary_text_many_files(self):
        matches = [{"file": f"f{i}.py", "line": 1, "text": "x"} for i in range(15)]
        result = summarize_search_results(matches, max_files=5)
        assert "showing top" in result["summary"]


class TestExtractFileListFromCountData:
    def test_basic(self):
        data = {"a.py": 3, "b.py": 5, "__total__": 8}
        result = extract_file_list_from_count_data(data)
        assert set(result) == {"a.py", "b.py"}

    def test_empty(self):
        assert extract_file_list_from_count_data({}) == []

    def test_only_total(self):
        assert extract_file_list_from_count_data({"__total__": 0}) == []


class TestCreateFileSummaryFromCountData:
    def test_basic(self):
        data = {"a.py": 3, "b.py": 5, "__total__": 8}
        result = create_file_summary_from_count_data(data)
        assert result["success"] is True
        assert result["total_matches"] == 8
        assert result["file_count"] == 2
        assert result["derived_from_count"] is True
        assert len(result["files"]) == 2

    def test_missing_total(self):
        data = {"a.py": 3}
        result = create_file_summary_from_count_data(data)
        assert result["total_matches"] == 0

    def test_empty(self):
        result = create_file_summary_from_count_data({})
        assert result["success"] is True
        assert result["file_count"] == 0
        assert result["files"] == []
