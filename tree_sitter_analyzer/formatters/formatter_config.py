#!/usr/bin/env python3
"""
Formatter configuration for language-specific formatting.

This configuration determines which formatter system (legacy or new)
should be used for each language and format type combination.
"""

from typing import Literal

FormatType = Literal["table", "compact", "full", "csv", "json"]
FormatterStrategy = Literal["legacy", "new"]

# Configuration mapping: language → format_type → strategy
LANGUAGE_FORMATTER_CONFIG: dict[str, dict[str, str]] = {
    # Legacy languages - use original TableFormatter
    "java": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "python": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "py": {  # Alias for Python
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "javascript": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "js": {  # Alias for JavaScript
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "typescript": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "ts": {  # Alias for TypeScript
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    # New languages - use language-specific formatters
    "sql": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "html": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "css": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "markdown": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "md": {  # Alias for Markdown
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "csharp": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "cs": {  # Alias for C#
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "php": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "ruby": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "rb": {  # Alias for Ruby
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
}

# Default strategy for unknown languages
DEFAULT_STRATEGY: str = "legacy"


def get_formatter_strategy(language: str, format_type: str) -> str:
    """
    Get formatter strategy for language and format type.

    Args:
        language: Programming language name
        format_type: Output format type

    Returns:
        Formatter strategy ("legacy" or "new")
    """
    lang_config = LANGUAGE_FORMATTER_CONFIG.get(language.lower(), {})
    return lang_config.get(format_type, DEFAULT_STRATEGY)
