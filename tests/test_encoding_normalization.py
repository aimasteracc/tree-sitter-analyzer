#!/usr/bin/env python3
"""
Tests for encoding normalization functionality in fd_rg_utils.
"""

import pytest
from tree_sitter_analyzer.mcp.tools.fd_rg_utils import normalize_encoding_name


class TestEncodingNormalization:
    """Test encoding name normalization for ripgrep compatibility."""

    def test_shift_jis_variants(self):
        """Test various Shift_JIS encoding name variants."""
        # Test cases that should all normalize to 'shift-jis'
        test_cases = [
            ("Shift_JIS", "shift-jis"),
            ("shift_jis", "shift-jis"),
            ("SHIFT_JIS", "shift-jis"),
            ("shift-jis", "shift-jis"),
            ("sjis", "shift-jis"),
            ("SJIS", "shift-jis"),
            ("cp932", "shift-jis"),
            ("CP932", "shift-jis"),
            ("windows-31j", "shift-jis"),
            ("Windows-31J", "shift-jis"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_utf_variants(self):
        """Test UTF encoding variants."""
        test_cases = [
            ("UTF-8", "utf-8"),
            ("utf-8", "utf-8"),
            ("utf8", "utf-8"),
            ("UTF8", "utf-8"),
            ("UTF-16", "utf-16"),
            ("utf16", "utf-16"),
            ("UTF-16LE", "utf-16le"),
            ("utf-16le", "utf-16le"),
            ("UTF-16BE", "utf-16be"),
            ("utf-16be", "utf-16be"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_latin_variants(self):
        """Test Latin/Western encoding variants."""
        test_cases = [
            ("latin1", "latin1"),
            ("Latin1", "latin1"),
            ("latin-1", "latin1"),
            ("Latin-1", "latin1"),
            ("iso-8859-1", "latin1"),
            ("ISO-8859-1", "latin1"),
            ("cp1252", "latin1"),
            ("CP1252", "latin1"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_ascii_variants(self):
        """Test ASCII encoding variants."""
        test_cases = [
            ("ascii", "ascii"),
            ("ASCII", "ascii"),
            ("us-ascii", "ascii"),
            ("US-ASCII", "ascii"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_chinese_variants(self):
        """Test Chinese encoding variants."""
        test_cases = [
            ("gbk", "gbk"),
            ("GBK", "gbk"),
            ("gb2312", "gbk"),
            ("GB2312", "gbk"),
            ("gb18030", "gbk"),
            ("GB18030", "gbk"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_japanese_variants(self):
        """Test Japanese encoding variants."""
        test_cases = [
            ("euc-jp", "euc-jp"),
            ("EUC-JP", "euc-jp"),
            ("eucjp", "euc-jp"),
            ("EUCJP", "euc-jp"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_korean_variants(self):
        """Test Korean encoding variants."""
        test_cases = [
            ("euc-kr", "euc-kr"),
            ("EUC-KR", "euc-kr"),
            ("euckr", "euc-kr"),
            ("EUCKR", "euc-kr"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"

    def test_none_and_empty_inputs(self):
        """Test None and empty string inputs."""
        assert normalize_encoding_name(None) is None
        assert normalize_encoding_name("") is None
        assert normalize_encoding_name("   ") is None

    def test_unknown_encoding(self):
        """Test unknown encoding names are returned as-is."""
        unknown_encodings = [
            "unknown-encoding",
            "custom-charset",
            "weird_encoding_123",
        ]
        
        for encoding in unknown_encodings:
            result = normalize_encoding_name(encoding)
            assert result == encoding, f"Unknown encoding '{encoding}' should be returned as-is, got '{result}'"

    def test_whitespace_handling(self):
        """Test that whitespace is properly handled."""
        test_cases = [
            ("  Shift_JIS  ", "shift-jis"),
            ("\tUTF-8\n", "utf-8"),
            ("  latin1  ", "latin1"),
        ]
        
        for input_encoding, expected in test_cases:
            result = normalize_encoding_name(input_encoding)
            assert result == expected, f"Expected '{input_encoding}' to normalize to '{expected}', got '{result}'"


class TestEncodingIntegration:
    """Integration tests for encoding handling in search functionality."""

    def test_shift_jis_encoding_in_command_building(self):
        """Test that Shift_JIS encoding is properly normalized in command building."""
        from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_rg_command
        
        # Test with original problematic encoding name
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
            encoding="Shift_JIS",  # Original problematic encoding
            max_count=None,
            timeout_ms=None,
            roots=["./"],
            files_from=None,
            count_only_matches=False,
        )
        
        # Check that the command contains the normalized encoding
        assert "--encoding" in cmd
        encoding_index = cmd.index("--encoding")
        assert cmd[encoding_index + 1] == "shift-jis", f"Expected 'shift-jis' in command, got '{cmd[encoding_index + 1]}'"

    def test_utf8_encoding_passthrough(self):
        """Test that UTF-8 encoding is handled correctly."""
        from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_rg_command
        
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
            encoding="utf-8",
            max_count=None,
            timeout_ms=None,
            roots=["./"],
            files_from=None,
            count_only_matches=False,
        )
        
        # Check that the command contains the correct encoding
        assert "--encoding" in cmd
        encoding_index = cmd.index("--encoding")
        assert cmd[encoding_index + 1] == "utf-8"

    def test_no_encoding_specified(self):
        """Test that no encoding parameter is added when encoding is None."""
        from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_rg_command
        
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
            roots=["./"],
            files_from=None,
            count_only_matches=False,
        )
        
        # Check that no encoding parameter is in the command
        assert "--encoding" not in cmd


if __name__ == "__main__":
    pytest.main([__file__])