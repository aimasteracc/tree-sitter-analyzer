#!/usr/bin/env python3
"""
Regex Safety Checker for Tree-sitter Analyzer

Provides ReDoS (Regular Expression Denial of Service) attack prevention
by analyzing regex patterns for potentially dangerous constructs.
"""

import re
import time

from ..utils import log_debug, log_warning


class RegexSafetyChecker:
    """
    Regex safety checker for ReDoS attack prevention.

    This class analyzes regular expressions for patterns that could
    lead to catastrophic backtracking and ReDoS attacks.

    Features:
    - Pattern complexity analysis
    - Dangerous construct detection
    - Execution time monitoring
    - Safe pattern compilation
    """

    # Maximum allowed pattern length
    MAX_PATTERN_LENGTH = 1000

    # Maximum execution time for pattern testing (seconds)
    MAX_EXECUTION_TIME = 1.0

    # Dangerous regex patterns that can cause ReDoS
    DANGEROUS_PATTERNS = [
        # Nested quantifiers
        r"\(.+\)\+",  # (a+)+
        r"\(.*\)\*",  # (a*)*
        r"\(.{0,}\)\+",  # (.{0,})+
        r"\(.+\)\{.*\}",  # (a+){n,m}
        # Alternation with overlap
        r"\(a\|a\)\*",  # (a|a)*
        r"\([^|]*\|[^|]*\)\+",  # (abc|abd)+
        # Exponential backtracking patterns
        r"\(.*\)\1",  # (.*)\1 - backreference
        r"\(\?\=.*\)\+",  # (?=.*)+
        r"\(\?\!.*\)\+",  # (?!.*)+
        r"\(\?\<\=.*\)\+",  # (?<=.*)+
        r"\(\?\<\!.*\)\+",  # (?<!.*)+
        # Catastrophic patterns
        r"\([^)]*\+[^)]*\)\+",  # Nested + quantifiers
        r"\([^)]*\*[^)]*\)\*",  # Nested * quantifiers
    ]

    def __init__(self) -> None:
        """Initialize regex safety checker."""
        log_debug("RegexSafetyChecker initialized")

    def validate_pattern(self, pattern: str) -> tuple[bool, str]:
        """
        Validate regex pattern for safety.

        Args:
            pattern: Regex pattern to validate

        Returns:
            Tuple of (is_safe, error_message)

        Example:
            >>> checker = RegexSafetyChecker()
            >>> is_safe, error = checker.validate_pattern(r"hello.*world")
            >>> assert is_safe
        """
        try:
            # Basic validation
            if not pattern or not isinstance(pattern, str):
                return False, "Pattern must be a non-empty string"

            # Length check
            if len(pattern) > self.MAX_PATTERN_LENGTH:
                return (
                    False,
                    f"Pattern too long: {len(pattern)} > {self.MAX_PATTERN_LENGTH}",
                )

            # Check for dangerous patterns
            dangerous_found = self._check_dangerous_patterns(pattern)
            if dangerous_found:
                return (
                    False,
                    f"Potentially dangerous regex pattern detected: {dangerous_found}",
                )

            # Compilation check
            compilation_error = self._check_compilation(pattern)
            if compilation_error:
                return False, f"Invalid regex pattern: {compilation_error}"

            # Performance check
            performance_error = self._check_performance(pattern)
            if performance_error:
                return False, f"Pattern performance issue: {performance_error}"

            log_debug(f"Regex pattern validation passed: {pattern}")
            return True, ""

        except Exception as e:
            log_warning(f"Regex validation error: {e}")
            return False, f"Validation error: {str(e)}"

    def _check_dangerous_patterns(self, pattern: str) -> str | None:
        """
        Check for known dangerous regex patterns.

        Args:
            pattern: Pattern to check

        Returns:
            Description of dangerous pattern found, or None if safe
        """
        for dangerous_pattern in self.DANGEROUS_PATTERNS:
            try:
                if re.search(dangerous_pattern, pattern):
                    log_warning(
                        f"Dangerous pattern detected: {dangerous_pattern} in {pattern}"
                    )
                    return dangerous_pattern
            except re.error:
                # If the dangerous pattern itself is invalid, skip it
                continue

        return None

    def _check_compilation(self, pattern: str) -> str | None:
        """
        Check if pattern compiles successfully.

        Args:
            pattern: Pattern to compile

        Returns:
            Error message if compilation fails, None if successful
        """
        try:
            re.compile(pattern)
            return None
        except re.error as e:
            log_warning(f"Regex compilation failed: {e}")
            return str(e)

    def _check_performance(self, pattern: str) -> str | None:
        """
        Check pattern performance with test strings.

        Args:
            pattern: Pattern to test

        Returns:
            Error message if performance is poor, None if acceptable
        """
        try:
            compiled_pattern = re.compile(pattern)

            # Test strings that might cause backtracking
            test_strings = [
                "a" * 100,  # Long string of same character
                "ab" * 50,  # Alternating pattern
                "x" * 50 + "y",  # Long string with different ending
                "a" * 30 + "b" * 30 + "c" * 30,  # Mixed long string
            ]

            for test_string in test_strings:
                start_time = time.time()

                try:
                    # Test both search and match operations
                    compiled_pattern.search(test_string)
                    compiled_pattern.match(test_string)

                    execution_time = time.time() - start_time

                    if execution_time > self.MAX_EXECUTION_TIME:
                        log_warning(
                            f"Regex performance issue: {execution_time:.3f}s > {self.MAX_EXECUTION_TIME}s"
                        )
                        return f"Pattern execution too slow: {execution_time:.3f}s"

                except Exception as e:
                    log_warning(f"Regex execution error: {e}")
                    return f"Pattern execution error: {str(e)}"

            return None

        except Exception as e:
            log_warning(f"Performance check error: {e}")
            return f"Performance check failed: {str(e)}"

    def analyze_complexity(self, pattern: str) -> dict:
        """
        Analyze regex pattern complexity.

        Args:
            pattern: Pattern to analyze

        Returns:
            Dictionary with complexity metrics
        """
        try:
            metrics = {
                "length": len(pattern),
                "quantifiers": len(re.findall(r"[+*?{]", pattern)),
                "groups": len(re.findall(r"\(", pattern)),
                "alternations": len(re.findall(r"\|", pattern)),
                "character_classes": len(re.findall(r"\[", pattern)),
                "anchors": len(re.findall(r"[\^$]", pattern)),
                "complexity_score": 0,
            }

            # Calculate complexity score
            metrics["complexity_score"] = (
                metrics["length"] * 0.1
                + metrics["quantifiers"] * 2
                + metrics["groups"] * 1.5
                + metrics["alternations"] * 3
                + metrics["character_classes"] * 1
            )

            return metrics

        except Exception as e:
            log_warning(f"Complexity analysis error: {e}")
            return {"error": str(e)}

    def suggest_safer_pattern(self, pattern: str) -> str | None:
        """
        Suggest a safer alternative for dangerous patterns.

        Args:
            pattern: Original pattern

        Returns:
            Suggested safer pattern, or None if no suggestion available
        """
        # Only suggest for patterns that are actually dangerous
        is_dangerous = self._check_dangerous_patterns(pattern)
        if not is_dangerous:
            return None

        # Simple pattern replacements for common dangerous cases
        replacements = {
            r"\(.+\)\+": r"[^\\s]+",  # Replace (a+)+ with [^\s]+
            r"\(.*\)\*": r"[^\\s]*",  # Replace (.*)* with [^\s]*
        }

        for dangerous, safer in replacements.items():
            if re.search(dangerous, pattern):
                suggested = re.sub(dangerous, safer, pattern)
                log_debug(f"Suggested safer pattern: {pattern} -> {suggested}")
                return suggested

        return None

    def get_safe_flags(self) -> int:
        """
        Get recommended safe regex flags.

        Returns:
            Combination of safe regex flags
        """
        # Use flags that prevent some ReDoS attacks
        return re.MULTILINE | re.DOTALL

    def create_safe_pattern(
        self, pattern: str, flags: int | None = None
    ) -> re.Pattern | None:
        """
        Create a safely compiled regex pattern.

        Args:
            pattern: Pattern to compile
            flags: Optional regex flags

        Returns:
            Compiled pattern if safe, None if dangerous
        """
        is_safe, error = self.validate_pattern(pattern)
        if not is_safe:
            log_warning(f"Cannot create unsafe pattern: {error}")
            return None

        try:
            safe_flags = flags if flags is not None else self.get_safe_flags()
            return re.compile(pattern, safe_flags)
        except re.error as e:
            log_warning(f"Pattern compilation failed: {e}")
            return None
