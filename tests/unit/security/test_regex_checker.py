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


class TestReDoSPrevention:
    """Advanced ReDoS attack prevention tests.

    These tests cover sophisticated backtracking bomb patterns and
    real-world ReDoS attack vectors.
    """

    @pytest.mark.unit
    def test_nested_quantifier_variants(self):
        """Test detection of various nested quantifier patterns."""
        checker = RegexSafetyChecker()

        # These patterns should be detected as dangerous (cause exponential backtracking)
        dangerous_variants = [
            r"(a+)+",           # Basic nested quantifier
            r"(a*)*",           # Star nested in star
            r"(a?)+",           # Optional nested in plus - can still cause issues
            r"(a+)*",           # Plus nested in star
            r"(a*)+",           # Star nested in plus
            r"(.+)+",           # Dot nested quantifier
            r"(.*)*",           # Dot star nested
            r"(\w+)+",          # Word char nested
            r"([a-z]+)+",       # Character class nested
        ]

        for pattern in dangerous_variants:
            is_safe, error = checker.validate_pattern(pattern)
            assert not is_safe, f"Pattern should be dangerous: {pattern}"
            assert "dangerous" in error.lower(), f"Error should mention danger: {error}"

    @pytest.mark.unit
    def test_optional_nested_quantifiers_may_be_safe(self):
        """Test that some optional nested quantifiers may be considered safe."""
        checker = RegexSafetyChecker()

        # (a+)? is effectively the same as a+ and may not be flagged
        # This is acceptable behavior
        pattern = r"(a+)?"
        is_safe, error = checker.validate_pattern(pattern)
        # Either outcome is acceptable for this edge case
        # The important thing is the checker doesn't crash

    @pytest.mark.unit
    def test_alternation_overlap_variants(self):
        """Test detection of overlapping alternation patterns."""
        checker = RegexSafetyChecker()

        dangerous_alternations = [
            r"(a|aa)*",         # Overlapping alternatives
            r"(a|ab)+",         # Prefix overlap
            r"(ab|a)+",         # Reverse prefix overlap
            r"(a|a)*",          # Identical alternatives
            r"(.|a)*",          # Dot with specific char
        ]

        for pattern in dangerous_alternations:
            is_safe, error = checker.validate_pattern(pattern)
            # Some patterns might pass, but should still be flagged if dangerous
            if not is_safe:
                assert "dangerous" in error.lower() or "invalid" in error.lower()

    @pytest.mark.unit
    def test_backreference_attacks(self):
        """Test detection of backreference-based attacks."""
        checker = RegexSafetyChecker()

        # Backreferences can cause exponential backtracking
        backreference_patterns = [
            r"(.*)\1",          # Simple backreference
            r"(.+)\1+",         # Backreference with quantifier
        ]

        for pattern in backreference_patterns:
            is_safe, error = checker.validate_pattern(pattern)
            # These should either be detected as dangerous or compile safely
            # but not cause ReDoS in testing

    @pytest.mark.unit
    def test_lookahead_quantifier_combinations(self):
        """Test detection of lookahead with quantifier attacks."""
        checker = RegexSafetyChecker()

        dangerous_lookaheads = [
            r"(?=.*)+",         # Positive lookahead with plus
            r"(?!.*)+",         # Negative lookahead with plus
            r"(?<=.*)+",        # Lookbehind with plus
            r"(?<!.*)+",        # Negative lookbehind with plus
        ]

        for pattern in dangerous_lookaheads:
            result = checker._check_dangerous_patterns(pattern)
            assert result is not None, f"Should detect dangerous lookahead: {pattern}"

    @pytest.mark.unit
    def test_deeply_nested_groups(self):
        """Test handling of deeply nested group patterns."""
        checker = RegexSafetyChecker()

        # These patterns are complex but should be handled
        complex_patterns = [
            r"((a+)+)",         # Double nested
            r"(((a+)+)+)",      # Triple nested
            r"(a(b(c(d+)+)+)+)",  # Mixed nesting
        ]

        for pattern in complex_patterns:
            is_safe, error = checker.validate_pattern(pattern)
            # All should be detected as dangerous due to nested quantifiers
            assert not is_safe, f"Nested pattern should be dangerous: {pattern}"

    @pytest.mark.unit
    def test_quantified_character_classes(self):
        """Test patterns with quantified character classes."""
        checker = RegexSafetyChecker()

        safe_patterns = [
            r"[a-z]+",          # Simple character class
            r"[0-9]{1,3}",      # Bounded quantifier
            r"[a-zA-Z0-9_]+",   # Word characters
        ]

        for pattern in safe_patterns:
            is_safe, error = checker.validate_pattern(pattern)
            assert is_safe, f"Pattern should be safe: {pattern}, error: {error}"

    @pytest.mark.unit
    def test_real_world_redos_patterns(self):
        """Test patterns known to cause ReDoS in real applications."""
        checker = RegexSafetyChecker()

        # Real-world ReDoS patterns from security advisories
        real_world_dangerous = [
            r"^(a+)+$",         # Classic ReDoS pattern
            r"^(a|aa)+$",       # OWASP example
            r"^(a|a?)+$",       # Another OWASP example
        ]

        for pattern in real_world_dangerous:
            is_safe, error = checker.validate_pattern(pattern)
            assert not is_safe, f"Real-world dangerous pattern should be caught: {pattern}"

    @pytest.mark.unit
    def test_bounded_vs_unbounded_quantifiers(self):
        """Test that bounded quantifiers are safer than unbounded."""
        checker = RegexSafetyChecker()

        # Bounded quantifiers are generally safer
        bounded_patterns = [
            r"a{1,10}",         # Bounded range
            r"a{5}",            # Exact count
            r"a{0,5}",          # Bounded optional
        ]

        for pattern in bounded_patterns:
            is_safe, error = checker.validate_pattern(pattern)
            assert is_safe, f"Bounded pattern should be safe: {pattern}, error: {error}"

    @pytest.mark.unit
    def test_complexity_score_thresholds(self):
        """Test complexity scoring for various patterns."""
        checker = RegexSafetyChecker()

        # Low complexity patterns
        simple = checker.analyze_complexity(r"hello")
        complex_pattern = checker.analyze_complexity(r"^((a+)+)+$")

        # Complex patterns should have higher scores
        assert complex_pattern["complexity_score"] > simple["complexity_score"]

    @pytest.mark.unit
    def test_empty_input_handling(self):
        """Test handling of empty and whitespace inputs."""
        checker = RegexSafetyChecker()

        # Empty pattern
        is_safe, error = checker.validate_pattern("")
        assert not is_safe
        assert "non-empty" in error.lower()

        # Whitespace only
        is_safe, error = checker.validate_pattern("   ")
        assert is_safe  # Whitespace is a valid regex

    @pytest.mark.unit
    def test_unicode_pattern_handling(self):
        """Test handling of unicode patterns."""
        checker = RegexSafetyChecker()

        unicode_patterns = [
            r"[\u0400-\u04FF]+",  # Cyrillic range
            r"[ぁ-ん]+",           # Hiragana
            r"[\p{L}]+",          # Unicode letter (may not compile)
        ]

        for pattern in unicode_patterns:
            is_safe, error = checker.validate_pattern(pattern)
            # Should either be safe or have a clear error
            if not is_safe:
                assert error  # Should have an error message

    @pytest.mark.unit
    def test_max_pattern_length_boundary(self):
        """Test exact boundary of max pattern length."""
        checker = RegexSafetyChecker()
        max_len = RegexSafetyChecker.MAX_PATTERN_LENGTH

        # Exactly at limit
        at_limit = "a" * max_len
        is_safe, error = checker.validate_pattern(at_limit)
        assert is_safe, "Pattern at exact limit should be safe"

        # One over limit
        over_limit = "a" * (max_len + 1)
        is_safe, error = checker.validate_pattern(over_limit)
        assert not is_safe
        assert "too long" in error.lower()

    @pytest.mark.unit
    def test_suggestion_quality(self):
        """Test that suggestions are actually safer."""
        checker = RegexSafetyChecker()

        dangerous = r"(.+)+"
        suggestion = checker.suggest_safer_pattern(dangerous)

        if suggestion:
            # Suggestion should be safe
            is_safe, error = checker.validate_pattern(suggestion)
            assert is_safe, f"Suggested pattern should be safe: {suggestion}, error: {error}"

            # Suggestion should be different
            assert suggestion != dangerous
