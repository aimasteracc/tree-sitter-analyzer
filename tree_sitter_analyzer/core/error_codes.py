#!/usr/bin/env python3
"""
Error Code System

Provides structured error handling with:
- Unique error codes
- User-friendly messages
- Repair suggestions
- Multi-language support

Phase 4 User Experience Enhancement.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ErrorCategory(Enum):
    """Categories for error classification."""
    FILE_ACCESS = "FILE_ACCESS"
    PARSING = "PARSING"
    LANGUAGE = "LANGUAGE"
    MEMORY = "MEMORY"
    VALIDATION = "VALIDATION"
    CONFIGURATION = "CONFIGURATION"
    SYSTEM = "SYSTEM"


@dataclass
class ErrorCode:
    """Structured error code with repair suggestions."""
    code: str
    category: ErrorCategory
    message: str
    repair_suggestion: str
    severity: str = "error"  # error, warning, info
    doc_url: Optional[str] = None


# Error code registry
ERROR_CODES: dict[str, ErrorCode] = {
    # File Access Errors (E001-E099)
    "E001": ErrorCode(
        code="E001",
        category=ErrorCategory.FILE_ACCESS,
        message="File not found: {path}",
        repair_suggestion="Check that the file path is correct and the file exists.",
        severity="error",
    ),
    "E002": ErrorCode(
        code="E002",
        category=ErrorCategory.FILE_ACCESS,
        message="Permission denied: {path}",
        repair_suggestion="Check file permissions or run with appropriate privileges.",
        severity="error",
    ),
    "E003": ErrorCode(
        code="E003",
        category=ErrorCategory.FILE_ACCESS,
        message="File too large: {path} ({size_mb}MB > {limit_mb}MB)",
        repair_suggestion="Use --chunk-size option or split the file into smaller parts.",
        severity="error",
    ),
    "E004": ErrorCode(
        code="E004",
        category=ErrorCategory.FILE_ACCESS,
        message="Encoding error in file: {path}",
        repair_suggestion="Try specifying encoding with --encoding option (e.g., utf-8, latin-1).",
        severity="warning",
    ),
    "E005": ErrorCode(
        code="E005",
        category=ErrorCategory.FILE_ACCESS,
        message="Binary file detected: {path}",
        repair_suggestion="This file appears to be binary. Text analysis is not applicable.",
        severity="warning",
    ),
    
    # Parsing Errors (E100-E199)
    "E100": ErrorCode(
        code="E100",
        category=ErrorCategory.PARSING,
        message="Syntax error at line {line}, column {column}",
        repair_suggestion="Check for syntax errors like missing brackets, quotes, or semicolons.",
        severity="error",
    ),
    "E101": ErrorCode(
        code="E101",
        category=ErrorCategory.PARSING,
        message="Failed to parse file: {reason}",
        repair_suggestion="Ensure the file contains valid code for the detected language.",
        severity="error",
    ),
    "E102": ErrorCode(
        code="E102",
        category=ErrorCategory.PARSING,
        message="Tree-sitter parser not available for language: {language}",
        repair_suggestion="Install the tree-sitter language package: pip install tree-sitter-{language}",
        severity="error",
    ),
    
    # Language Errors (E200-E299)
    "E200": ErrorCode(
        code="E200",
        category=ErrorCategory.LANGUAGE,
        message="Unsupported language: {language}",
        repair_suggestion="Use --language to specify a supported language (python, java, javascript, etc.).",
        severity="error",
    ),
    "E201": ErrorCode(
        code="E201",
        category=ErrorCategory.LANGUAGE,
        message="Language detection failed for: {path}",
        repair_suggestion="Use --language option to explicitly specify the language.",
        severity="warning",
    ),
    "E202": ErrorCode(
        code="E202",
        category=ErrorCategory.LANGUAGE,
        message="Plugin initialization failed: {plugin}",
        repair_suggestion="Check plugin dependencies and configuration.",
        severity="error",
    ),
    
    # Memory Errors (E300-E399)
    "E300": ErrorCode(
        code="E300",
        category=ErrorCategory.MEMORY,
        message="Memory limit exceeded: {used_mb}MB > {limit_mb}MB",
        repair_suggestion="Use --max-memory option to increase limit, or analyze smaller files.",
        severity="error",
    ),
    "E301": ErrorCode(
        code="E301",
        category=ErrorCategory.MEMORY,
        message="Cache eviction triggered: {evicted_count} entries removed",
        repair_suggestion="Consider using --no-cache for one-time analysis or increase cache size.",
        severity="info",
    ),
    
    # Validation Errors (E400-E499)
    "E400": ErrorCode(
        code="E400",
        category=ErrorCategory.VALIDATION,
        message="Invalid query: {query}",
        repair_suggestion="Check query syntax. Use --list-queries to see available queries.",
        severity="error",
    ),
    "E401": ErrorCode(
        code="E401",
        category=ErrorCategory.VALIDATION,
        message="Invalid output format: {format}",
        repair_suggestion="Supported formats: json, text, markdown. Use --format option.",
        severity="error",
    ),
    "E402": ErrorCode(
        code="E402",
        category=ErrorCategory.VALIDATION,
        message="Invalid option combination: {details}",
        repair_suggestion="Check command documentation for valid option combinations.",
        severity="error",
    ),
    
    # Configuration Errors (E500-E599)
    "E500": ErrorCode(
        code="E500",
        category=ErrorCategory.CONFIGURATION,
        message="Configuration file not found: {path}",
        repair_suggestion="Create the configuration file or use default settings.",
        severity="warning",
    ),
    "E501": ErrorCode(
        code="E501",
        category=ErrorCategory.CONFIGURATION,
        message="Invalid configuration value: {key}={value}",
        repair_suggestion="Check configuration documentation for valid values.",
        severity="error",
    ),
    
    # System Errors (E600-E699)
    "E600": ErrorCode(
        code="E600",
        category=ErrorCategory.SYSTEM,
        message="Operation timed out after {seconds}s",
        repair_suggestion="Use --timeout option to increase timeout or analyze smaller files.",
        severity="error",
    ),
    "E601": ErrorCode(
        code="E601",
        category=ErrorCategory.SYSTEM,
        message="Concurrent operation limit reached: {active}/{max}",
        repair_suggestion="Wait for current operations to complete or increase --max-workers.",
        severity="warning",
    ),
}


class AnalyzerError(Exception):
    """
    Structured exception with error code.
    
    Attributes:
        error_code: The ErrorCode definition
        details: Format parameters for the error message
    """
    
    def __init__(
        self,
        code: str,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        """
        Initialize error.
        
        Args:
            code: Error code (e.g., "E001")
            details: Parameters for message formatting
            cause: Original exception that caused this error
        """
        self.code = code
        self.error_code = ERROR_CODES.get(code)
        self.details = details or {}
        self.cause = cause
        
        if self.error_code:
            message = self.error_code.message.format(**self.details)
        else:
            message = f"Unknown error code: {code}"
        
        super().__init__(message)
    
    def get_repair_suggestion(self) -> str:
        """Get repair suggestion for this error."""
        if self.error_code:
            return self.error_code.repair_suggestion.format(**self.details)
        return "No repair suggestion available."
    
    def get_full_message(self) -> str:
        """Get full error message with code and suggestion."""
        parts = [f"[{self.code}] {self.message}"]
        
        suggestion = self.get_repair_suggestion()
        if suggestion:
            parts.append(f"Suggestion: {suggestion}")
        
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        
        return "\n".join(parts)


def create_error(code: str, **details: Any) -> AnalyzerError:
    """
    Create a structured error.
    
    Args:
        code: Error code
        **details: Parameters for message formatting
    
    Returns:
        AnalyzerError instance
    """
    return AnalyzerError(code, details)


def get_error_info(code: str) -> Optional[ErrorCode]:
    """
    Get error code information.
    
    Args:
        code: Error code
    
    Returns:
        ErrorCode definition or None
    """
    return ERROR_CODES.get(code)


def list_errors(category: Optional[ErrorCategory] = None) -> list[ErrorCode]:
    """
    List all error codes, optionally filtered by category.
    
    Args:
        category: Category to filter by
    
    Returns:
        List of ErrorCode definitions
    """
    errors = list(ERROR_CODES.values())
    
    if category:
        errors = [e for e in errors if e.category == category]
    
    return sorted(errors, key=lambda e: e.code)
