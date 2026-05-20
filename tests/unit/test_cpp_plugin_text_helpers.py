"""Tests for languages._cpp_plugin_text_helpers — fallback text extraction."""

from types import SimpleNamespace

from tree_sitter_analyzer.languages._cpp_plugin_text_helpers import (
    _fallback_multiline_text,
    _fallback_node_text_uncached,
    _slice_fallback_line,
    get_node_text_optimized,
)


def _make_node(start_byte, end_byte, start_row, start_col, end_row, end_col):
    return SimpleNamespace(
        start_byte=start_byte,
        end_byte=end_byte,
        start_point=(start_row, start_col),
        end_point=(end_row, end_col),
    )


class TestGetNodeTextOptimized:
    def test_cache_hit(self):
        node = _make_node(0, 5, 0, 0, 0, 5)
        cache = {(0, 5): "cached"}
        result = get_node_text_optimized(
            node,
            content_lines=["hello world"],
            file_encoding=None,
            node_text_cache=cache,
            extract_text_slice_func=lambda *_: "should not be called",
            safe_encode_func=lambda *_: b"",
        )
        assert result == "cached"

    def test_extraction_success(self):
        node = _make_node(0, 5, 0, 0, 0, 5)
        cache = {}

        def extract_slice(data, start, end, enc):
            return data[start:end].decode(enc)

        result = get_node_text_optimized(
            node,
            content_lines=["hello"],
            file_encoding="utf-8",
            node_text_cache=cache,
            extract_text_slice_func=extract_slice,
            safe_encode_func=lambda text, enc: text.encode(enc),
        )
        assert result == "hello"
        assert cache[(0, 5)] == "hello"

    def test_extraction_failure_uses_fallback(self):
        node = _make_node(0, 100, 0, 0, 1, 5)

        def failing_extract(*_):
            raise RuntimeError("extraction failed")

        result = get_node_text_optimized(
            node,
            content_lines=["first line", "second line here"],
            file_encoding=None,
            node_text_cache={},
            extract_text_slice_func=failing_extract,
            safe_encode_func=lambda text, enc: text.encode(enc),
        )
        assert isinstance(result, str)
        assert "first line" in result


class TestFallbackNodeTextUncached:
    def test_single_line_extraction(self):
        lines = ["hello world", "second line"]
        result = _fallback_node_text_uncached((0, 2), (0, 7), lines)
        assert result == "llo w"

    def test_multiline_extraction(self):
        lines = ["first", "second", "third"]
        result = _fallback_node_text_uncached((0, 2), (2, 3), lines)
        assert result == "rst\nsecond\nthi"


class TestFallbackMultilineText:
    def test_extracts_all_lines_between_points(self):
        lines = ["abc", "def", "ghi", "jkl"]
        result = _fallback_multiline_text((0, 1), (2, 2), lines)
        assert "bc" in result
        assert "def" in result
        assert "gh" in result

    def test_handles_end_beyond_content(self):
        lines = ["abc"]
        result = _fallback_multiline_text((0, 0), (5, 0), lines)
        assert "abc" in result


class TestSliceFallbackLine:
    def test_first_line_slices_from_start(self):
        lines = ["hello world"]
        result = _slice_fallback_line(0, (0, 2), (2, 5), lines)
        assert result == "llo world"

    def test_last_line_slices_to_end(self):
        lines = ["hello", "world"]
        result = _slice_fallback_line(1, (0, 2), (1, 3), lines)
        assert result == "wor"

    def test_middle_line_returns_full(self):
        lines = ["aaa", "bbb", "ccc"]
        result = _slice_fallback_line(1, (0, 0), (2, 0), lines)
        assert result == "bbb"
