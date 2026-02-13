#!/usr/bin/env python3
"""
Enhanced tests for RegexSafetyChecker class - coverage gaps.
"""

import re

import pytest

from tree_sitter_analyzer.security import RegexSafetyChecker


class TestRegexSafetyCheckerEnhanced:
    """Enhanced test suite for RegexSafetyChecker - coverage gaps."""

    def setup_method(self):
        """Set up test fixtures."""
        self.checker = RegexSafetyChecker()

    @pytest.mark.unit
    def test_create_safe_pattern_with_custom_flags(self):
        """create_safe_pattern with custom flags (re.IGNORECASE)."""
        pattern = r"hello"
        compiled = self.checker.create_safe_pattern(pattern, flags=re.IGNORECASE)
        assert compiled is not None
        assert compiled.search("HELLO") is not None

    @pytest.mark.unit
    def test_create_safe_pattern_with_none_flags_uses_default(self):
        """create_safe_pattern with flags=None uses get_safe_flags()."""
        pattern = r"hello"
        compiled = self.checker.create_safe_pattern(pattern, flags=None)
        assert compiled is not None
        default_flags = self.checker.get_safe_flags()
        assert (default_flags & re.MULTILINE) or (default_flags & re.DOTALL)

    @pytest.mark.unit
    def test_analyze_complexity_on_invalid_pattern_returns_error(self):
        """analyze_complexity on invalid input returns dict with error key."""
        metrics = self.checker.analyze_complexity(None)
        assert "error" in metrics
        assert isinstance(metrics["error"], str)

    @pytest.mark.unit
    def test_analyze_complexity_on_complex_patterns(self):
        """analyze_complexity on patterns with nested groups, quantifiers, alternations."""
        patterns = [
            r"(a|b|c)+",
            r"[a-z]{2,5}",
            r"^(\w+)\1$",
            r"(?:foo|bar)+",
        ]
        for p in patterns:
            metrics = self.checker.analyze_complexity(p)
            assert "length" in metrics
            assert "complexity_score" in metrics
            assert "error" not in metrics

    @pytest.mark.unit
    def test_validate_pattern_catastrophic_backtracking_a_plus_plus_b(self):
        """validate_pattern rejects (a+)+b catastrophic pattern."""
        is_safe, error = self.checker.validate_pattern(r"(a+)+b")
        assert not is_safe
        assert "dangerous" in error.lower() or "Invalid" in error

    @pytest.mark.unit
    def test_validate_pattern_catastrophic_alternation(self):
        """validate_pattern rejects (a|aa)+b pattern."""
        is_safe, error = self.checker.validate_pattern(r"(a|aa)+b")
        assert not is_safe

    @pytest.mark.unit
    def test_suggest_safer_pattern_for_dotstar_star(self):
        """suggest_safer_pattern for (.*)* pattern."""
        suggestion = self.checker.suggest_safer_pattern(r"(.*)*")
        assert suggestion is not None
        assert suggestion != r"(.*)*"

    @pytest.mark.unit
    def test_suggest_safer_pattern_for_a_plus_plus(self):
        """suggest_safer_pattern for (a+)+ pattern."""
        suggestion = self.checker.suggest_safer_pattern(r"(a+)+")
        assert suggestion is not None

    @pytest.mark.unit
    def test_suggest_safer_pattern_returns_none_for_safe(self):
        """suggest_safer_pattern returns None for already safe patterns."""
        assert self.checker.suggest_safer_pattern(r"hello") is None
        assert self.checker.suggest_safer_pattern(r"\d+") is None

    @pytest.mark.unit
    def test_get_safe_flags_returns_correct_flags(self):
        """get_safe_flags returns MULTILINE | DOTALL (verify implementation)."""
        flags = self.checker.get_safe_flags()
        assert flags & re.MULTILINE
        assert flags & re.DOTALL
        assert isinstance(flags, int)

    @pytest.mark.unit
    def test_validate_pattern_with_empty_string(self):
        """validate_pattern rejects empty string."""
        is_safe, error = self.checker.validate_pattern("")
        assert not is_safe
        assert "non-empty" in error or "empty" in error.lower()

    @pytest.mark.unit
    def test_validate_pattern_with_unicode(self):
        """validate_pattern with Unicode patterns."""
        pattern = r"[\u4e00-\u9fff]+"
        is_safe, error = self.checker.validate_pattern(pattern)
        assert is_safe or "dangerous" in error.lower()

    @pytest.mark.unit
    def test_check_dangerous_patterns_nested_quantifiers(self):
        """_check_dangerous_patterns detects nested quantifiers."""
        found = self.checker._check_dangerous_patterns(r"(.+)+")
        assert found is not None

    @pytest.mark.unit
    def test_check_dangerous_patterns_star_star(self):
        """_check_dangerous_patterns detects (.*)*."""
        found = self.checker._check_dangerous_patterns(r"(.*)*")
        assert found is not None

    @pytest.mark.unit
    def test_check_dangerous_patterns_safe(self):
        """_check_dangerous_patterns returns None for safe pattern."""
        found = self.checker._check_dangerous_patterns(r"simple")
        assert found is None

    @pytest.mark.unit
    def test_check_compilation_invalid_syntax(self):
        """_check_compilation returns error for invalid regex."""
        error = self.checker._check_compilation(r"[")
        assert error is not None
        assert len(error) > 0

    @pytest.mark.unit
    def test_check_compilation_valid(self):
        """_check_compilation returns None for valid pattern."""
        assert self.checker._check_compilation(r"\d+") is None

    @pytest.mark.unit
    def test_max_pattern_length_constant(self):
        """MAX_PATTERN_LENGTH is 1000."""
        assert RegexSafetyChecker.MAX_PATTERN_LENGTH == 1000

    @pytest.mark.unit
    def test_max_execution_time_constant(self):
        """MAX_EXECUTION_TIME is 1.0 seconds."""
        assert RegexSafetyChecker.MAX_EXECUTION_TIME == 1.0

    @pytest.mark.unit
    def test_validate_pattern_too_long(self):
        """validate_pattern rejects pattern longer than MAX_PATTERN_LENGTH."""
        long_pattern = "a" * 1001
        is_safe, error = self.checker.validate_pattern(long_pattern)
        assert not is_safe
        assert "too long" in error

    @pytest.mark.unit
    def test_create_safe_pattern_with_regex_verbose_flag(self):
        """create_safe_pattern accepts custom flags including re.VERBOSE."""
        pattern = r"\d+"
        compiled = self.checker.create_safe_pattern(pattern, flags=re.VERBOSE)
        assert compiled is not None
        assert compiled.search("123") is not None

    @pytest.mark.unit
    def test_analyze_complexity_exception_path(self):
        """analyze_complexity returns error dict on exception."""
        # Pass something that causes exception in re.findall
        metrics = self.checker.analyze_complexity(123)
        assert "error" in metrics
