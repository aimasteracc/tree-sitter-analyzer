"""
Exception types for parser and analysis operations.

This module defines all custom exceptions used in the v2 codebase.
"""


class ParserError(Exception):
    """Base exception for parser-related errors."""

    pass


class UnsupportedLanguageError(ParserError):
    """Raised when attempting to parse an unsupported language."""

    def __init__(self, language: str) -> None:
        """
        Initialize error.

        Args:
            language: The unsupported language identifier
        """
        self.language = language
        super().__init__(
            f"Language '{language}' is not supported. "
            "See SupportedLanguage enum for available languages."
        )


class ParseError(ParserError):
    """Raised when parsing fails."""

    def __init__(self, message: str, file_path: str | None = None) -> None:
        """
        Initialize error.

        Args:
            message: Error message
            file_path: Optional path to file that failed to parse
        """
        self.file_path = file_path
        if file_path:
            super().__init__(f"{message} (file: {file_path})")
        else:
            super().__init__(message)


class FileTooLargeError(ParserError):
    """Raised when file exceeds maximum size limit."""

    def __init__(self, file_path: str, size: int, max_size: int) -> None:
        """
        Initialize error.

        Args:
            file_path: Path to the file
            size: Actual file size in bytes
            max_size: Maximum allowed size in bytes
        """
        self.file_path = file_path
        self.size = size
        self.max_size = max_size
        super().__init__(
            f"File {file_path} is {size:,} bytes, "
            f"exceeds maximum allowed size of {max_size:,} bytes"
        )


class SecurityViolationError(ParserError):
    """Raised when a security violation is detected."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        """
        Initialize error.

        Args:
            message: Error message describing the violation
            details: Optional dictionary with additional details
        """
        self.details = details or {}
        super().__init__(message)
