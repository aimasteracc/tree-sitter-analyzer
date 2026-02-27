#!/usr/bin/env python3
"""
Tests for RegexSafetyChecker class.
"""

import re
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.security import RegexSafetyChecker


class TestRegexSafetyChecker:
    """Test suite for RegexSafetyChecker class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.checker = RegexSafetyChecker()

    @pytest.mark.unit
    def test_validate_pattern_safe(self):
        """Test validation of safe regex patterns."""
        # Arrange
        safe_patterns = [
            r"hello.*world",
            r"\d+",
            r"[a-zA-Z]+",
            r"^start.*end$",
            r"simple",
        ]

        for pattern in safe_patterns:
            # Act
            is_safe, error = self.checker.validate_pattern(pattern)

            # Assert
            assert is_safe, f"Pattern should be safe: {pattern}, error: {error}"
            assert error == ""

    @pytest.mark.unit
    def test_validate_pattern_empty(self):
        """Test validation fails for empty pattern."""
        # Act
        is_safe, error = self.checker.validate_pattern("")

        # Assert
        assert not is_safe
        assert "non-empty string" in error

    @pytest.mark.unit
    def test_validate_pattern_too_long(self):
        """Test validation fails for too long pattern."""
        # Arrange
        long_pattern = "a" * 2000

        # Act
        is_safe, error = self.checker.validate_pattern(long_pattern)

        # Assert
        assert not is_safe
        assert "too long" in error

    @pytest.mark.unit
    def test_validate_pattern_dangerous(self):
        """Test validation fails for dangerous patterns."""
        # Arrange
        dangerous_patterns = [
            r"(.+)+",  # Nested quantifiers
            r"(.*)*",  # Nested quantifiers
            r"(.{0,})+",  # Potential ReDoS
            r"(a|a)*",  # Alternation with overlap
        ]

        for pattern in dangerous_patterns:
            # Act
            is_safe, error = self.checker.validate_pattern(pattern)

            # Assert
            assert not is_safe, f"Pattern should be dangerous: {pattern}"
            assert "dangerous" in error.lower()

    @pytest.mark.unit
    def test_validate_pattern_invalid_syntax(self):
        """Test validation fails for invalid regex syntax."""
        # Arrange
        invalid_patterns = [
            r"[",  # Unclosed bracket
            r"(?P<",  # Incomplete group
            r"*",  # Invalid quantifier
            r"(?",  # Incomplete group
        ]

        for pattern in invalid_patterns:
            # Act
            is_safe, error = self.checker.validate_pattern(pattern)

            # Assert
            assert not is_safe, f"Pattern should be invalid: {pattern}"

    @pytest.mark.unit
    def test_analyze_complexity(self):
        """Test regex complexity analysis."""
        # Arrange
        pattern = r"^[a-zA-Z]+\d{2,4}(test|demo)*$"

        # Act
        metrics = self.checker.analyze_complexity(pattern)

        # Assert
        assert "length" in metrics
        assert "quantifiers" in metrics
        assert "groups" in metrics
        assert "alternations" in metrics
        assert "complexity_score" in metrics
        assert metrics["length"] > 0
        assert metrics["quantifiers"] > 0
        assert metrics["groups"] > 0
        assert metrics["alternations"] > 0

    @pytest.mark.unit
    def test_suggest_safer_pattern(self):
        """Test safer pattern suggestions."""
        # Arrange
        dangerous_pattern = r"(.+)+"

        # Act
        suggestion = self.checker.suggest_safer_pattern(dangerous_pattern)

        # Assert
        assert suggestion is not None
        assert suggestion != dangerous_pattern

    @pytest.mark.unit
    def test_suggest_safer_pattern_no_suggestion(self):
        """Test no suggestion for safe patterns."""
        # Arrange
        safe_pattern = r"hello.*world"

        # Act
        suggestion = self.checker.suggest_safer_pattern(safe_pattern)

        # Assert
        assert suggestion is None

    @pytest.mark.unit
    def test_get_safe_flags(self):
        """Test getting safe regex flags."""
        # Act
        flags = self.checker.get_safe_flags()

        # Assert
        assert isinstance(flags, int)
        assert flags > 0

    @pytest.mark.unit
    def test_create_safe_pattern_success(self):
        """Test creating safe compiled pattern."""
        # Arrange
        safe_pattern = r"hello.*world"

        # Act
        compiled = self.checker.create_safe_pattern(safe_pattern)

        # Assert
        assert compiled is not None
        assert hasattr(compiled, "search")
        assert hasattr(compiled, "match")

    @pytest.mark.unit
    def test_create_safe_pattern_dangerous(self):
        """Test creating safe pattern fails for dangerous input."""
        # Arrange
        dangerous_pattern = r"(.+)+"

        # Act
        compiled = self.checker.create_safe_pattern(dangerous_pattern)

        # Assert
        assert compiled is None

    @pytest.mark.unit
    def test_create_safe_pattern_invalid(self):
        """Test creating safe pattern fails for invalid syntax."""
        # Arrange
        invalid_pattern = r"["

        # Act
        compiled = self.checker.create_safe_pattern(invalid_pattern)

        # Assert
        assert compiled is None

    @pytest.mark.unit
    def test_performance_check_fast_pattern(self):
        """Test performance check passes for fast patterns."""
        # Arrange
        fast_pattern = r"hello"

        # Act
        is_safe, error = self.checker.validate_pattern(fast_pattern)

        # Assert
        assert is_safe
        assert error == ""

    @pytest.mark.unit
    def test_check_dangerous_patterns_detection(self):
        """Test dangerous pattern detection."""
        # Arrange
        dangerous_pattern = r"(.+)+"

        # Act
        dangerous_found = self.checker._check_dangerous_patterns(dangerous_pattern)

        # Assert
        assert dangerous_found is not None

    @pytest.mark.unit
    def test_check_dangerous_patterns_safe(self):
        """Test safe pattern passes dangerous pattern check."""
        # Arrange
        safe_pattern = r"hello.*world"

        # Act
        dangerous_found = self.checker._check_dangerous_patterns(safe_pattern)

        # Assert
        assert dangerous_found is None


class TestRegexCheckerEdgeCases:
    """Tests for edge cases and additional code paths merged from variant files."""

    @pytest.mark.unit
    def test_validate_pattern_none(self):
        """Test validation fails for None pattern."""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(None)
        assert not is_safe
        assert "non-empty string" in error

    @pytest.mark.unit
    def test_validate_pattern_non_string(self):
        """Test validation fails for non-string pattern."""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(123)
        assert not is_safe
        assert "non-empty string" in error

    @pytest.mark.unit
    def test_validate_pattern_at_max_length(self):
        """Test validation passes for pattern at exact max length."""
        checker = RegexSafetyChecker()
        max_pattern = "a" * RegexSafetyChecker.MAX_PATTERN_LENGTH
        is_safe, error = checker.validate_pattern(max_pattern)
        assert is_safe
        assert error == ""

    @pytest.mark.unit
    def test_validate_pattern_exception_handling(self):
        """Test validation handles internal exceptions gracefully."""
        checker = RegexSafetyChecker()
        with patch.object(
            checker, "_check_dangerous_patterns", side_effect=Exception("Test error")
        ):
            is_safe, error = checker.validate_pattern(r"test")
            assert not is_safe
            assert "Validation error" in error

    @pytest.mark.unit
    def test_check_dangerous_patterns_negative_lookahead(self):
        """Test detection of negative lookahead with quantifier."""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(?!.*)+")
        assert result is not None

    @pytest.mark.unit
    def test_check_dangerous_patterns_negative_lookbehind(self):
        """Test detection of negative lookbehind with quantifier."""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(?<!.*)+")
        assert result is not None

    @pytest.mark.unit
    def test_check_compilation_valid(self):
        """Test _check_compilation returns None for valid pattern."""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"test.*pattern")
        assert result is None

    @pytest.mark.unit
    def test_check_compilation_invalid(self):
        """Test _check_compilation returns error for invalid pattern."""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"[invalid(regex")
        assert result is not None
        assert "unterminated" in result.lower() or "missing" in result.lower()

    @pytest.mark.unit
    def test_check_performance_exception_handling(self):
        """Test _check_performance handles exceptions gracefully."""
        checker = RegexSafetyChecker()
        with patch("re.compile", side_effect=Exception("Test error")):
            result = checker._check_performance(r"test")
            assert result is not None
            assert "Performance check failed" in result

    @pytest.mark.unit
    def test_create_safe_pattern_with_flags(self):
        """Test creating safe pattern with custom flags."""
        checker = RegexSafetyChecker()
        pattern = checker.create_safe_pattern(r"test.*pattern", flags=re.IGNORECASE)
        assert pattern is not None
        assert isinstance(pattern, re.Pattern)
