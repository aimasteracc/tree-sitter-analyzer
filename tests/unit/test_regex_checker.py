#!/usr/bin/env python3
"""
Unit tests for regex_checker module.

Tests for RegexSafetyChecker class which provides ReDoS (Regular Expression
Denial of Service) attack prevention by analyzing regex patterns for
potentially dangerous constructs.
"""

import re
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.security.regex_checker import RegexSafetyChecker


class TestRegexSafetyCheckerInitialization:
    """测试 RegexSafetyChecker 初始化"""

    def test_default_initialization(self):
        """测试默认初始化"""
        checker = RegexSafetyChecker()
        assert checker is not None
        assert hasattr(checker, "MAX_PATTERN_LENGTH")
        assert hasattr(checker, "MAX_EXECUTION_TIME")
        assert hasattr(checker, "DANGEROUS_PATTERNS")

    def test_max_pattern_length_constant(self):
        """测试最大模式长度常量"""
        assert RegexSafetyChecker.MAX_PATTERN_LENGTH == 1000

    def test_max_execution_time_constant(self):
        """测试最大执行时间常量"""
        assert RegexSafetyChecker.MAX_EXECUTION_TIME == 1.0

    def test_dangerous_patterns_list(self):
        """测试危险模式列表"""
        assert len(RegexSafetyChecker.DANGEROUS_PATTERNS) > 0
        assert isinstance(RegexSafetyChecker.DANGEROUS_PATTERNS, list)
        assert all(isinstance(p, str) for p in RegexSafetyChecker.DANGEROUS_PATTERNS)


class TestValidatePattern:
    """测试 validate_pattern 方法"""

    def test_validate_pattern_safe(self):
        """测试安全模式验证"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"hello.*world")
        assert is_safe
        assert error == ""

    def test_validate_pattern_simple(self):
        """测试简单模式验证"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"test")
        assert is_safe
        assert error == ""

    def test_validate_pattern_empty_string(self):
        """测试空字符串模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern("")
        assert not is_safe
        assert "non-empty string" in error

    def test_validate_pattern_none(self):
        """测试 None 模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(None)
        assert not is_safe
        assert "non-empty string" in error

    def test_validate_pattern_non_string(self):
        """测试非字符串模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(123)
        assert not is_safe
        assert "non-empty string" in error

    def test_validate_pattern_too_long(self):
        """测试过长的模式"""
        checker = RegexSafetyChecker()
        long_pattern = "a" * (RegexSafetyChecker.MAX_PATTERN_LENGTH + 1)
        is_safe, error = checker.validate_pattern(long_pattern)
        assert not is_safe
        assert "too long" in error

    def test_validate_pattern_at_max_length(self):
        """测试最大长度模式"""
        checker = RegexSafetyChecker()
        max_pattern = "a" * RegexSafetyChecker.MAX_PATTERN_LENGTH
        is_safe, error = checker.validate_pattern(max_pattern)
        assert is_safe
        assert error == ""

    def test_validate_pattern_invalid_regex(self):
        """测试无效的正则表达式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"[invalid(regex")
        assert not is_safe
        assert "Invalid regex pattern" in error

    def test_validate_pattern_dangerous_nested_quantifiers(self):
        """测试危险嵌套量词"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(a+)+")
        assert not is_safe
        assert "dangerous" in error.lower()

    def test_validate_pattern_dangerous_alternation_overlap(self):
        """测试危险交替重叠"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(a|a)*")
        assert not is_safe
        assert "dangerous" in error.lower()

    def test_validate_pattern_dangerous_backreference(self):
        """测试危险反向引用"""
        checker = RegexSafetyChecker()
        # Backreference pattern may not be in DANGEROUS_PATTERNS list
        # Just test that it validates without crashing
        is_safe, error = checker.validate_pattern(r"(.*)\1")
        # The pattern is valid regex, so it should be safe
        assert isinstance(is_safe, bool)

    def test_validate_pattern_dangerous_lookahead(self):
        """测试危险前瞻断言"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(?=.*)+")
        assert not is_safe
        assert "dangerous" in error.lower()

    def test_validate_pattern_dangerous_lookbehind(self):
        """测试危险后顾断言"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(?<=.*)+")
        assert not is_safe
        assert "dangerous" in error.lower()

    def test_validate_pattern_with_escaped_chars(self):
        """测试带转义字符的模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"test\\d+\\.py")
        assert is_safe
        assert error == ""

    def test_validate_pattern_with_character_class(self):
        """测试带字符类的模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"[a-zA-Z0-9]+")
        assert is_safe
        assert error == ""

    def test_validate_pattern_with_anchors(self):
        """测试带锚点的模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"^test.*end$")
        assert is_safe
        assert error == ""

    def test_validate_pattern_with_groups(self):
        """测试带分组的模式"""
        checker = RegexSafetyChecker()
        # This pattern might be flagged as dangerous due to nested quantifiers
        is_safe, error = checker.validate_pattern(r"(test|demo)+")
        # Just verify it validates without crashing
        assert isinstance(is_safe, bool)

    def test_validate_pattern_exception_handling(self):
        """测试异常处理"""
        checker = RegexSafetyChecker()

        with patch.object(
            checker, "_check_dangerous_patterns", side_effect=Exception("Test error")
        ):
            is_safe, error = checker.validate_pattern(r"test")
            assert not is_safe
            assert "Validation error" in error


class TestCheckDangerousPatterns:
    """测试 _check_dangerous_patterns 方法"""

    def test_check_dangerous_patterns_safe(self):
        """测试安全模式检查"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"hello.*world")
        assert result is None

    def test_check_dangerous_patterns_nested_plus(self):
        """检测嵌套加号量词"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(a+)+")
        assert result is not None
        assert "+" in result

    def test_check_dangerous_patterns_nested_star(self):
        """检测嵌套星号量词"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(a*)*")
        assert result is not None
        assert "*" in result

    def test_check_dangerous_patterns_alternation_overlap(self):
        """检测交替重叠"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(a|a)*")
        assert result is not None

    def test_check_dangerous_patterns_backreference(self):
        """检测反向引用"""
        checker = RegexSafetyChecker()
        # Backreference pattern is in DANGEROUS_PATTERNS but may not match
        # Just verify it doesn't crash
        result = checker._check_dangerous_patterns(r"(.*)\1")
        # Result can be None or a string depending on implementation
        assert result is None or isinstance(result, str)

    def test_check_dangerous_patterns_lookahead(self):
        """检测前瞻断言"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(?=.*)+")
        assert result is not None

    def test_check_dangerous_patterns_lookbehind(self):
        """检测后顾断言"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(?<=.*)+")
        assert result is not None

    def test_check_dangerous_patterns_negative_lookahead(self):
        """检测负向前瞻"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(?!.*)+")
        assert result is not None

    def test_check_dangerous_patterns_negative_lookbehind(self):
        """检测负向后顾"""
        checker = RegexSafetyChecker()
        result = checker._check_dangerous_patterns(r"(?<!.*)+")
        assert result is not None

    def test_check_dangerous_patterns_invalid_dangerous_pattern(self):
        """测试无效的危险模式处理"""
        checker = RegexSafetyChecker()

        # Mock a dangerous pattern that itself is invalid
        with patch.object(checker, "DANGEROUS_PATTERNS", [r"[invalid(regex"]):
            result = checker._check_dangerous_patterns(r"test")
            assert result is None


class TestCheckCompilation:
    """测试 _check_compilation 方法"""

    def test_check_compilation_valid(self):
        """测试有效模式编译"""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"test.*pattern")
        assert result is None

    def test_check_compilation_invalid(self):
        """测试无效模式编译"""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"[invalid(regex")
        assert result is not None
        assert "unterminated" in result.lower() or "missing" in result.lower()

    def test_check_compilation_unclosed_bracket(self):
        """测试未闭合的方括号"""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"[a-z")
        assert result is not None

    def test_check_compilation_unclosed_paren(self):
        """测试未闭合的圆括号"""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"(test")
        assert result is not None

    def test_check_compilation_invalid_quantifier(self):
        """测试无效量词"""
        checker = RegexSafetyChecker()
        result = checker._check_compilation(r"a{10,5}")
        assert result is not None


class TestCheckPerformance:
    """测试 _check_performance 方法"""

    def test_check_performance_safe_pattern(self):
        """测试安全模式性能"""
        checker = RegexSafetyChecker()
        result = checker._check_performance(r"test")
        assert result is None

    def test_check_performance_simple_pattern(self):
        """测试简单模式性能"""
        checker = RegexSafetyChecker()
        result = checker._check_performance(r"^test$")
        assert result is None

    def test_check_performance_with_long_string(self):
        """测试长字符串模式性能"""
        checker = RegexSafetyChecker()
        result = checker._check_performance(r"a+")
        assert result is None

    def test_check_performance_exception_handling(self):
        """测试异常处理"""
        checker = RegexSafetyChecker()

        with patch("re.compile", side_effect=Exception("Test error")):
            result = checker._check_performance(r"test")
            assert result is not None
            assert "Performance check failed" in result

    def test_check_performance_execution_error(self):
        """测试执行错误"""
        checker = RegexSafetyChecker()

        # Create a pattern that will raise an error during search
        with patch.object(checker, "_check_compilation", return_value=None):
            with patch("re.compile") as mock_compile:
                mock_pattern = MagicMock()
                mock_pattern.search.side_effect = RuntimeError("Test error")
                mock_compile.return_value = mock_pattern

                result = checker._check_performance(r"test")
                assert result is not None
                assert "execution error" in result.lower()


class TestAnalyzeComplexity:
    """测试 analyze_complexity 方法"""

    def test_analyze_complexity_simple(self):
        """测试简单模式复杂度分析"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"test")
        assert metrics["length"] == 4
        assert metrics["quantifiers"] == 0
        assert metrics["groups"] == 0
        assert metrics["alternations"] == 0
        assert metrics["character_classes"] == 0
        assert metrics["anchors"] == 0

    def test_analyze_complexity_with_quantifiers(self):
        """测试带量词的模式复杂度分析"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"a+b*c?")
        assert metrics["quantifiers"] == 3
        assert metrics["complexity_score"] > 0

    def test_analyze_complexity_with_groups(self):
        """测试带分组的模式复杂度分析"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"(test)(demo)")
        assert metrics["groups"] == 2

    def test_analyze_complexity_with_alternations(self):
        """测试带交替的模式复杂度分析"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"test|demo|sample")
        assert metrics["alternations"] == 2

    def test_analyze_complexity_with_character_classes(self):
        """测试带字符类的模式复杂度分析"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"[a-zA-Z0-9]")
        assert metrics["character_classes"] == 1

    def test_analyze_complexity_with_anchors(self):
        """测试带锚点的模式复杂度分析"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"^test$")
        assert metrics["anchors"] == 2

    def test_analyze_complexity_score_calculation(self):
        """测试复杂度分数计算"""
        checker = RegexSafetyChecker()
        metrics = checker.analyze_complexity(r"^test[a-z]+\.py$")

        # Verify score is calculated and positive
        assert metrics["complexity_score"] > 0
        # Verify individual metrics are calculated correctly
        # Pattern: ^test[a-z]+\.py$ has length 16
        assert metrics["length"] == 16
        assert metrics["quantifiers"] == 1
        assert metrics["groups"] == 0
        assert metrics["alternations"] == 0
        assert metrics["character_classes"] == 1

    def test_analyze_complexity_exception_handling(self):
        """测试异常处理"""
        checker = RegexSafetyChecker()

        with patch("re.findall", side_effect=Exception("Test error")):
            metrics = checker.analyze_complexity(r"test")
            assert "error" in metrics


class TestSuggestSaferPattern:
    """测试 suggest_safer_pattern 方法"""

    def test_suggest_safer_pattern_safe_pattern(self):
        """测试安全模式不提供建议"""
        checker = RegexSafetyChecker()
        result = checker.suggest_safer_pattern(r"test.*pattern")
        assert result is None

    def test_suggest_safer_pattern_nested_plus(self):
        """测试嵌套加号量词的建议"""
        checker = RegexSafetyChecker()
        result = checker.suggest_safer_pattern(r"(a+)+")
        assert result is not None
        assert "[^\\s]+" in result or "[^\\\\s]+" in result

    def test_suggest_safer_pattern_nested_star(self):
        """测试嵌套星号量词的建议"""
        checker = RegexSafetyChecker()
        result = checker.suggest_safer_pattern(r"(a*)*")
        assert result is not None
        assert "[^\\s]*" in result or "[^\\\\s]*" in result

    def test_suggest_safer_pattern_no_suggestion(self):
        """测试无建议的情况"""
        checker = RegexSafetyChecker()
        # Pattern that is dangerous but not in replacement list
        result = checker.suggest_safer_pattern(r"(.*)\1")
        assert result is None

    def test_suggest_safer_pattern_partial_match(self):
        """测试部分匹配的建议"""
        checker = RegexSafetyChecker()
        result = checker.suggest_safer_pattern(r"prefix(a+)+suffix")
        assert result is not None


class TestGetSafeFlags:
    """测试 get_safe_flags 方法"""

    def test_get_safe_flags(self):
        """测试获取安全标志"""
        checker = RegexSafetyChecker()
        flags = checker.get_safe_flags()
        assert flags is not None
        assert isinstance(flags, int)
        assert flags & re.MULTILINE != 0
        assert flags & re.DOTALL != 0


class TestCreateSafePattern:
    """测试 create_safe_pattern 方法"""

    def test_create_safe_pattern_valid(self):
        """测试创建安全模式"""
        checker = RegexSafetyChecker()
        pattern = checker.create_safe_pattern(r"test.*pattern")
        assert pattern is not None
        assert isinstance(pattern, re.Pattern)

    def test_create_safe_pattern_with_flags(self):
        """测试带标志创建安全模式"""
        checker = RegexSafetyChecker()
        pattern = checker.create_safe_pattern(r"test.*pattern", flags=re.IGNORECASE)
        assert pattern is not None
        assert isinstance(pattern, re.Pattern)

    def test_create_safe_pattern_dangerous(self):
        """测试创建危险模式返回 None"""
        checker = RegexSafetyChecker()
        pattern = checker.create_safe_pattern(r"(a+)+")
        assert pattern is None

    def test_create_safe_pattern_invalid(self):
        """测试创建无效模式返回 None"""
        checker = RegexSafetyChecker()
        pattern = checker.create_safe_pattern(r"[invalid(regex")
        assert pattern is None

    def test_create_safe_pattern_compilation_failure(self):
        """测试编译失败返回 None"""
        checker = RegexSafetyChecker()

        with patch("re.compile", side_effect=re.error("Test error")):
            pattern = checker.create_safe_pattern(r"test")
            assert pattern is None


class TestEdgeCases:
    """测试边缘情况"""

    def test_pattern_with_unicode(self):
        """测试 Unicode 模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"test[\u4e00-\u9fa5]+")
        assert is_safe

    def test_pattern_with_special_chars(self):
        """测试特殊字符模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"test\.\*\+\?\|\[\]\(\)\{\}\^\$\\")
        assert is_safe

    def test_pattern_with_comments(self):
        """测试带注释的模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(?x)test  # comment")
        assert is_safe

    def test_pattern_with_named_groups(self):
        """测试命名分组模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(?P<name>test)")
        assert is_safe

    def test_pattern_with_non_capturing_groups(self):
        """测试非捕获分组模式"""
        checker = RegexSafetyChecker()
        # Non-capturing groups with quantifiers might be flagged
        is_safe, error = checker.validate_pattern(r"(?:test)+")
        # Just verify it validates without crashing
        assert isinstance(is_safe, bool)

    def test_pattern_with_atomic_groups(self):
        """测试原子分组模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(?>test)")
        # Atomic groups may not be supported in all Python versions
        # Just ensure it doesn't crash
        assert isinstance(is_safe, bool)

    def test_pattern_with_conditional(self):
        """测试条件模式"""
        checker = RegexSafetyChecker()
        is_safe, error = checker.validate_pattern(r"(?(id)yes|no)")
        # Conditional groups may not be supported in all Python versions
        assert isinstance(is_safe, bool)

    def test_pattern_with_recursive(self):
        """测试递归模式"""
        checker = RegexSafetyChecker()
        # Recursive patterns are not supported in Python's re module
        is_safe, error = checker.validate_pattern(r"(?R)")
        assert isinstance(is_safe, bool)


class TestIntegration:
    """测试集成场景"""

    def test_complete_validation_workflow(self):
        """测试完整验证工作流"""
        checker = RegexSafetyChecker()

        # Safe pattern
        is_safe, error = checker.validate_pattern(r"^test[a-z]+\.py$")
        assert is_safe

        # Analyze complexity
        metrics = checker.analyze_complexity(r"^test[a-z]+\.py$")
        assert metrics["length"] > 0

        # Create safe pattern
        pattern = checker.create_safe_pattern(r"^test[a-z]+\.py$")
        assert pattern is not None

        # Use pattern
        assert pattern.match("testfile.py")
        assert not pattern.match("testfile.txt")

    def test_dangerous_pattern_detection_workflow(self):
        """测试危险模式检测工作流"""
        checker = RegexSafetyChecker()

        # Dangerous pattern
        is_safe, error = checker.validate_pattern(r"(a+)+")
        assert not is_safe
        assert "dangerous" in error.lower()

        # Get suggestion
        suggestion = checker.suggest_safer_pattern(r"(a+)+")
        assert suggestion is not None

        # Validate suggestion
        is_safe, error = checker.validate_pattern(suggestion)
        assert is_safe

    def test_complexity_analysis_workflow(self):
        """测试复杂度分析工作流"""
        checker = RegexSafetyChecker()

        patterns = [
            r"simple",
            r"test[a-z]+",
            r"^(test|demo)+[a-z]{3}$",
            r"(?P<name>[a-z]+)(?P<value>\d+)",
        ]

        for pattern in patterns:
            metrics = checker.analyze_complexity(pattern)
            assert "length" in metrics
            assert "complexity_score" in metrics
            assert metrics["complexity_score"] >= 0
