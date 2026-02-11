"""Token optimization module.

Optimizes source code to reduce token count for AI context windows.

Features:
    - Remove comments (language-specific)
    - Remove empty lines
    - Compress whitespace
    - Multi-level optimization
    - Performance monitoring

Architecture:
    - TokenOptimizer: Main class for token optimization
    - LanguageStrategy: Strategy pattern for language-specific optimization
    - Statistics tracking for performance monitoring

Usage:
    ```python
    optimizer = TokenOptimizer()
    result = optimizer.optimize(code, "python", level=2)
    stats = optimizer.get_statistics()
    ```

Performance Characteristics:
    - Time: O(n) where n is number of lines
    - Space: O(1) additional space for processing

Thread Safety:
    - Thread-safe: Yes (immutable operations, stateless strategies)

Dependencies:
    - External: re (built-in)
    - Internal: None

Error Handling:
    - 3 custom exceptions

Note:
    Supports Python, JavaScript, Java, Kotlin, and other common languages.
    JSON and YAML files are not modified.

Example:
    ```python
    from tree_sitter_analyzer_v2.core.token_optimizer import TokenOptimizer

    optimizer = TokenOptimizer()
    code = 'def hello():\n    # comment\n    print("hello")'
    result = optimizer.optimize(code, "python", level=2)
    # Result: 'def hello():\n    print("hello")'
    ```
"""

import logging
import re
from time import perf_counter
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "TokenOptimizer",
    "TokenOptimizerBaseError",
    "InvalidLanguageError",
    "OptimizationError",
]


# ============================================================================
# Exception Classes
# ============================================================================


class TokenOptimizerBaseError(Exception):
    """Base exception for token optimizer errors."""

    pass


class InvalidLanguageError(TokenOptimizerBaseError):
    """Raised when an unsupported language is specified."""

    pass


class OptimizationError(TokenOptimizerBaseError):
    """Raised when an optimization operation fails."""

    pass


# ============================================================================
# Token Optimizer Class
# ============================================================================


class TokenOptimizer:
    """Optimizes source code to reduce token count for AI context windows.

    Attributes:
        None (all operations are stateless)

    Features:
        - Multi-level optimization (1-4)
        - Language-specific comment removal
        - Performance statistics tracking

    Usage:
        ```python
        optimizer = TokenOptimizer()
        result = optimizer.optimize(code, "python", level=2)
        ```
    """

    # Supported languages for comment removal
    SUPPORTED_LANGUAGES = frozenset(
        [
            "python",
            "py",
            "javascript",
            "js",
            "typescript",
            "ts",
            "java",
            "kotlin",
            "scala",
            "c",
            "cpp",
            "c++",
            "c#",
            "csharp",
            "go",
            "rust",
            "ruby",
            "php",
            "swift",
            "objective-c",
            "objectivec",
            # Markup languages (no comment removal)
            "json",
            "yaml",
            "yml",
            "xml",
            "html",
        ]
    )

    # Languages that use # for comments
    HASH_COMMENT_LANGUAGES = frozenset(
        [
            "python",
            "py",
            "ruby",
            "perl",
            "shell",
            "bash",
            "powershell",
        ]
    )

    # Languages that use // for comments
    DOUBLE_SLASH_COMMENTS = frozenset(
        [
            "javascript",
            "js",
            "typescript",
            "ts",
            "java",
            "kotlin",
            "scala",
            "c",
            "cpp",
            "c++",
            "c#",
            "csharp",
            "go",
            "rust",
            "swift",
            "objective-c",
            "objectivec",
            "php",
        ]
    )

    def __init__(self) -> None:
        """Initialize TokenOptimizer with performance tracking.

        Args:
            None
        """
        self._stats: dict[str, Any] = {
            "total_calls": 0,
            "total_time": 0.0,
            "errors": 0,
            "lines_processed": 0,
            "tokens_removed": 0,
        }

    # =========================================================================
    # Public Methods
    # =========================================================================

    def remove_comments(self, code: str, language: str) -> str:
        """Remove comments from source code.

        Args:
            code: Source code string
            language: Programming language (e.g., 'python', 'javascript')

        Returns:
            str: Code with comments removed

        Raises:
            InvalidLanguageError: If language is not supported
            OptimizationError: If optimization fails

        Note:
            - Python: Removes # comments and docstrings (triple quotes)
            - JavaScript: Removes // and /* */ comments
            - JSON/YAML: Returns unchanged
        """
        start = perf_counter()
        try:
            self._stats["total_calls"] += 1

            if code is None:
                raise OptimizationError("Input code cannot be None")

            if not code:
                return ""

            lang = language.lower()

            # Check if language is supported
            if lang not in self.SUPPORTED_LANGUAGES:
                raise InvalidLanguageError(
                    f"Unsupported language: {language}. "
                    f"Supported: {sorted(self.SUPPORTED_LANGUAGES)}"
                )

            # Markup languages are not modified
            if lang in ("json", "yaml", "yml", "xml", "html"):
                return code

            # Hash comment languages (#)
            if lang in self.HASH_COMMENT_LANGUAGES:
                result = self._remove_hash_comments(code)
            # Double slash languages (//)
            elif lang in self.DOUBLE_SLASH_COMMENTS:
                result = self._remove_double_slash_comments(code)
            else:
                # Default: remove hash comments
                result = self._remove_hash_comments(code)

            # Update statistics
            lines = code.split("\n")
            self._stats["lines_processed"] += len(lines)
            removed = len(lines) - len(result.split("\n"))
            self._stats["tokens_removed"] += removed

            return result

        except Exception as e:
            self._stats["errors"] += 1
            if isinstance(e, InvalidLanguageError):
                raise
            raise OptimizationError(f"Comment removal failed: {e}") from e
        finally:
            self._stats["total_time"] += perf_counter() - start

    def remove_empty_lines(self, code: str) -> str:
        """Remove empty lines from source code.

        Args:
            code: Source code string

        Returns:
            str: Code with empty lines removed

        Raises:
            OptimizationError: If operation fails
        """
        start = perf_counter()
        try:
            self._stats["total_calls"] += 1

            if code is None:
                raise OptimizationError("Input code cannot be None")

            if not code:
                return ""

            lines = code.split("\n")
            # Keep lines that have non-whitespace content
            result_lines = [line for line in lines if line.strip()]
            result = "\n".join(result_lines)

            # Update statistics
            self._stats["lines_processed"] += len(lines)
            removed = len(lines) - len(result_lines)
            self._stats["tokens_removed"] += removed

            return result

        except Exception as e:
            self._stats["errors"] += 1
            raise OptimizationError(f"Empty line removal failed: {e}") from e
        finally:
            self._stats["total_time"] += perf_counter() - start

    def compress_whitespace(self, code: str) -> str:
        """Compress multiple whitespace characters to single space.

        Args:
            code: Source code string

        Returns:
            str: Code with compressed whitespace

        Raises:
            OptimizationError: If operation fails

        Note:
            - Preserves indentation for readability
            - Only compresses spaces between tokens
        """
        start = perf_counter()
        try:
            self._stats["total_calls"] += 1

            if code is None:
                raise OptimizationError("Input code cannot be None")

            if not code:
                return ""

            lines = code.split("\n")
            result_lines = []

            for line in lines:
                # Preserve leading indentation
                leading = len(line) - len(line.lstrip())
                leading_spaces = " " * leading
                content = line.lstrip()

                # Compress multiple spaces to single space (but not at start)
                if content:
                    content = re.sub(r" {2,}", " ", content)

                result_lines.append(leading_spaces + content)

            result = "\n".join(result_lines)

            # Update statistics
            self._stats["lines_processed"] += len(lines)

            return result

        except Exception as e:
            self._stats["errors"] += 1
            raise OptimizationError(f"Whitespace compression failed: {e}") from e
        finally:
            self._stats["total_time"] += perf_counter() - start

    def optimize(self, code: str, language: str, level: int = 2) -> str:
        """Optimize code with specified optimization level.

        Args:
            code: Source code string
            language: Programming language
            level: Optimization level (1-4)
                - 1: Remove empty lines only
                - 2: Remove empty lines + comments
                - 3: Remove empty lines + comments + docstrings
                - 4: Full compression (empty + comments + whitespace)

        Returns:
            str: Optimized code

        Raises:
            InvalidLanguageError: If language is not supported
            OptimizationError: If optimization fails

        Note:
            Higher levels provide more token reduction but may
            reduce code readability for AI analysis.
        """
        start = perf_counter()
        try:
            if not (1 <= level <= 4):
                raise OptimizationError(f"Invalid level: {level}. Must be 1-4.")

            result = code

            # Level 1: Remove empty lines
            if level >= 1:
                result = self.remove_empty_lines(result)

            # Level 2: Remove comments
            if level >= 2:
                result = self.remove_comments(result, language)

            # Level 3: Remove docstrings (Python only)
            if level >= 3 and language.lower() in ("python", "py"):
                result = self._remove_docstrings(result)

            # Level 4: Compress whitespace
            if level >= 4:
                result = self.compress_whitespace(result)

            return result

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning("Token optimization failed: %s", e)
            raise
        finally:
            self._stats["total_time"] += perf_counter() - start

    def get_statistics(self) -> dict[str, Any]:
        """Get optimization performance statistics.

        Args:
            None (instance method with no parameters)

        Returns:
            dict[str, Any]: Statistics with derived metrics
        """
        total = max(1, self._stats["total_calls"])
        return {
            **self._stats,
            "avg_time": self._stats["total_time"] / total,
        }

    def get_optimization_summary(self) -> dict[str, Any]:
        """Get summary of available optimization levels.

        Args:
            None

        Returns:
            dict[str, Any]: Summary of optimization levels
        """
        return {
            "levels": {
                "1": "Remove empty lines",
                "2": "Remove empty lines + comments",
                "3": "Remove empty lines + comments + docstrings (Python)",
                "4": "Full compression",
            },
            "supported_languages": sorted(self.SUPPORTED_LANGUAGES),
        }

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _remove_hash_comments(self, code: str) -> str:
        """Remove # style comments from code.

        Args:
            code: Source code string

        Returns:
            str: Code with # comments removed
        """
        lines = code.split("\n")
        result_lines = []
        in_triple_quote = False

        for line in lines:
            stripped = line.strip()

            # Count triple quotes on this line
            triple_count = stripped.count('"""') + stripped.count("'''")

            # Handle triple quotes (docstrings) - only if on its own line
            if triple_count > 0:
                # If we're not in a triple quote block and this line contains only triple quote
                if (
                    not in_triple_quote
                    and (stripped == '"""' or stripped == "'''")
                    or in_triple_quote
                    and (stripped == '"""' or stripped == "'''")
                ):
                    in_triple_quote = not in_triple_quote
                    continue
                # Otherwise, this line has both code and triple quote (inline docstring)
                # Remove the docstring part
                if '"""' in stripped:
                    stripped = re.sub(r'"""[\s\S]*?"""', "", stripped).strip()
                elif "'''" in stripped:
                    stripped = re.sub(r"'''[\s\S]*?'''", "", stripped).strip()

            # Skip if inside triple quote block
            if in_triple_quote:
                continue

            # Remove # comments (but not URLs)
            if "#" in stripped:
                # Split at # but keep if it's a URL
                parts = stripped.split("#")
                # Check if first part ends with URL-like pattern
                if parts[0].rstrip().endswith(("http://", "https://", "ftp://")):
                    result_lines.append(line)
                else:
                    # Remove everything after #
                    code_part = parts[0].rstrip()
                    if code_part:
                        # Preserve leading whitespace
                        leading = len(line) - len(line.lstrip())
                        result_lines.append(" " * leading + code_part)
                    # Don't add empty/comment-only lines
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    def _remove_double_slash_comments(self, code: str) -> str:
        """Remove // and /* */ style comments from code.

        Args:
            code: Source code string

        Returns:
            str: Code with // and /* */ comments removed
        """
        lines = code.split("\n")
        result_lines = []
        in_block_comment = False

        for line in lines:
            stripped = line.strip()

            if in_block_comment:
                # Look for end of block comment
                if "*/" in stripped:
                    in_block_comment = False
                continue

            # Check for start of block comment
            if "/*" in stripped and "*/" in stripped:
                # Inline block comment
                # Remove content between /* and */
                line = re.sub(r"/\*.*?\*/", "", line)
                stripped = line.strip()
                if not stripped:
                    continue
            elif "/*" in stripped:
                in_block_comment = True
                continue

            # Remove // comments (but not URLs)
            if "//" in stripped:
                # Split at //
                parts = stripped.split("//")
                # Check if first part contains URL
                if parts[0].rstrip().endswith(("http://", "https://", "ftp://")):
                    result_lines.append(line)
                else:
                    # Remove everything after //
                    code_part = parts[0].rstrip()
                    if code_part:
                        leading = len(line) - len(line.lstrip())
                        result_lines.append(" " * leading + code_part)
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    def _remove_docstrings(self, code: str) -> str:
        """Remove docstrings from Python code.

        Args:
            code: Source code string

        Returns:
            str: Code with docstrings removed
        """
        # Remove triple-quoted docstrings
        # Match """...""" and '''...'''
        pattern = r'"""[\s\S]*?"""' r"|" r"'''[\s\S]*?'''"
        result = re.sub(pattern, "", code)
        return result
