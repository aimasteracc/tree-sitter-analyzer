#!/usr/bin/env python3
"""Tests for text utility functions."""

from tree_sitter_analyzer.utils.text_utils import safe_preview


class TestSafePreview:
    """Tests for safe_preview function."""

    def test_text_under_limit(self):
        """Text under limit should be returned as-is."""
        assert safe_preview("hello world", 50) == "hello world"
        assert safe_preview("short", 50) == "short"

    def test_text_over_limit(self):
        """Text over limit should be truncated with ellipsis."""
        long_text = "a" * 100
        result = safe_preview(long_text, 50)
        assert len(result) == 50
        assert result.endswith("...")
        assert result == "a" * 47 + "..."

    def test_multiline_flattens(self):
        """Multi-line text should be flattened to single line."""
        multiline = "line1\nline2\nline3"
        result = safe_preview(multiline, 50)
        assert "\n" not in result
        assert result == "line1 line2 line3"

    def test_multiline_with_carriage_return(self):
        """Carriage returns should also be removed."""
        text = "line1\r\nline2\rline3"
        result = safe_preview(text, 50)
        assert "\r" not in result
        assert "\n" not in result

    def test_unicode_safe(self):
        """Unicode characters should not be split mid-character."""
        # Emoji and CJK characters
        text = "Hello 👋 世界 " * 10  # >50 chars
        result = safe_preview(text, 50)
        assert len(result) <= 50
        # Should end with "..." after proper truncation
        assert result.endswith("...")

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert safe_preview("", 50) == ""
        assert safe_preview("   ", 50) == ""  # whitespace-only

    def test_none_input(self):
        """None input should return empty string (not raise)."""
        assert safe_preview(None, 50) == ""

    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        text = "a" * 100
        result = safe_preview(text, 20)
        assert len(result) == 20
        assert result == "a" * 17 + "..."

    def test_exact_limit(self):
        """Text exactly at limit should not be truncated."""
        text = "a" * 50
        result = safe_preview(text, 50)
        assert result == text
        assert not result.endswith("...")
