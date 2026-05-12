#!/usr/bin/env python3
"""
Tests for OutputFormatValidator

Covers language detection, error messages, mutual exclusion validation,
and active format retrieval.
"""

import locale
import os
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.output_format_validator import (
    OutputFormatValidator,
    get_default_validator,
)


class TestOutputFormatValidatorDetectLanguage:
    """Tests for _detect_language method"""

    def test_detect_language_japanese_locale(self):
        """Detect Japanese from locale setting (lines 43-48)"""
        validator = OutputFormatValidator()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(locale, "getlocale", return_value=("ja_JP.UTF-8", "UTF-8")):
                result = validator._detect_language()
                assert result == "ja"

    def test_detect_language_english_fallback(self):
        """Detect English as default when no Japanese indicators (line 51)"""
        validator = OutputFormatValidator()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(locale, "getlocale", return_value=(None, None)):
                result = validator._detect_language()
                assert result == "en"

    def test_detect_language_locale_exception(self):
        """Handle locale exception gracefully (line 47-48)"""
        validator = OutputFormatValidator()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(locale, "getlocale", side_effect=Exception("locale error")):
                result = validator._detect_language()
                assert result == "en"

    def test_detect_language_non_japanese_locale(self):
        """Detect English for non-Japanese locale"""
        validator = OutputFormatValidator()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(locale, "getlocale", return_value=("en_US.UTF-8", "UTF-8")):
                result = validator._detect_language()
                assert result == "en"


class TestOutputFormatValidatorJapaneseError:
    """Tests for Japanese error messages (lines 81, 87-88, 90)"""

    def test_japanese_error_message(self):
        """Generate Japanese error message when language is ja"""
        validator = OutputFormatValidator()
        with patch.object(validator, "_detect_language", return_value="ja"):
            msg = validator._get_error_message(["total_only", "summary_only"])
            assert "出力形式パラメータエラー" in msg
            assert "相互排他的" in msg
            assert "total_only" in msg
            assert "summary_only" in msg

    def test_japanese_error_includes_efficiency_guide(self):
        """Japanese error includes token efficiency guide"""
        validator = OutputFormatValidator()
        with patch.object(validator, "_detect_language", return_value="ja"):
            msg = validator._get_error_message(["group_by_file"])
            assert "トークン効率ガイド" in msg
            assert "total_only" in msg
            assert "count_only_matches" in msg


class TestOutputFormatValidatorEnglishError:
    """Tests for English error messages"""

    def test_english_error_message(self):
        """Generate English error message"""
        validator = OutputFormatValidator()
        with patch.object(validator, "_detect_language", return_value="en"):
            msg = validator._get_error_message(["total_only", "suppress_output"])
            assert "Output Format Parameter Error" in msg
            assert "Mutually Exclusive" in msg
            assert "total_only" in msg

    def test_english_error_includes_usage_patterns(self):
        """English error includes recommended usage patterns"""
        validator = OutputFormatValidator()
        with patch.object(validator, "_detect_language", return_value="en"):
            msg = validator._get_error_message(["summary_only"])
            assert "Recommended Usage Patterns" in msg


class TestOutputFormatValidatorExclusion:
    """Tests for validate_output_format_exclusion"""

    def test_single_format_no_error(self):
        """Single format parameter raises no error"""
        validator = OutputFormatValidator()
        validator.validate_output_format_exclusion({"total_only": True})

    def test_no_format_no_error(self):
        """No format parameter raises no error"""
        validator = OutputFormatValidator()
        validator.validate_output_format_exclusion({})

    def test_multiple_formats_raises_error(self):
        """Multiple format parameters raises ValueError"""
        validator = OutputFormatValidator()
        with pytest.raises(ValueError, match="出力形式|Output Format"):
            validator.validate_output_format_exclusion(
                {"total_only": True, "summary_only": True}
            )

    def test_all_formats_raises_error(self):
        """All format parameters together raises ValueError"""
        validator = OutputFormatValidator()
        with pytest.raises(ValueError):
            validator.validate_output_format_exclusion(
                {
                    "total_only": True,
                    "count_only_matches": True,
                    "summary_only": True,
                    "group_by_file": True,
                    "suppress_output": True,
                }
            )


class TestOutputFormatValidatorActiveFormat:
    """Tests for get_active_format"""

    def test_get_active_total_only(self):
        validator = OutputFormatValidator()
        assert validator.get_active_format({"total_only": True}) == "total_only"

    def test_get_active_count_only_matches(self):
        validator = OutputFormatValidator()
        assert (
            validator.get_active_format({"count_only_matches": True})
            == "count_only_matches"
        )

    def test_get_active_summary_only(self):
        validator = OutputFormatValidator()
        assert validator.get_active_format({"summary_only": True}) == "summary_only"

    def test_get_active_group_by_file(self):
        validator = OutputFormatValidator()
        assert validator.get_active_format({"group_by_file": True}) == "group_by_file"

    def test_get_active_suppress_output(self):
        validator = OutputFormatValidator()
        assert validator.get_active_format({"suppress_output": True}) == "suppress_output"

    def test_get_active_normal_default(self):
        validator = OutputFormatValidator()
        assert validator.get_active_format({}) == "normal"

    def test_get_active_first_match(self):
        """Returns first matching format, not all"""
        validator = OutputFormatValidator()
        assert (
            validator.get_active_format({"total_only": True, "summary_only": True})
            == "total_only"
        )


class TestGetDefaultValidator:
    """Tests for get_default_validator singleton"""

    def test_returns_validator_instance(self):
        validator = get_default_validator()
        assert isinstance(validator, OutputFormatValidator)

    def test_singleton_behavior(self):
        validator1 = get_default_validator()
        validator2 = get_default_validator()
        assert validator1 is validator2
