"""Language-specific formatter registration without registry import cycles."""

import logging
from typing import Any


def ensure_default_language_formatter(
    registry: type[Any], logger: logging.Logger
) -> None:
    """Install the default table formatter once its module is importable."""
    if registry._default_language_formatter is not None:
        return
    try:
        from ..default_table_formatter import DefaultTableFormatter
    except ImportError as error:
        logger.debug("Deferred default formatter registration: %s", error)
        return
    registry.set_default_language_formatter(DefaultTableFormatter)


def _code_language_formatters() -> dict[str, type[Any]]:
    """Load formatter classes for programming languages."""
    from .bash_formatter import BashTableFormatter
    from .cpp_formatter import CppTableFormatter
    from .csharp_formatter import CSharpTableFormatter
    from .go_formatter import GoTableFormatter
    from .java_formatter import JavaTableFormatter
    from .javascript_formatter import JavaScriptTableFormatter
    from .kotlin_formatter import KotlinTableFormatter
    from .php_formatter import PHPTableFormatter
    from .python_formatter import PythonTableFormatter
    from .ruby_formatter import RubyTableFormatter
    from .rust_formatter import RustTableFormatter
    from .typescript_formatter import TypeScriptTableFormatter

    return {
        "java": JavaTableFormatter,
        "python": PythonTableFormatter,
        "py": PythonTableFormatter,
        "javascript": JavaScriptTableFormatter,
        "js": JavaScriptTableFormatter,
        "typescript": TypeScriptTableFormatter,
        "ts": TypeScriptTableFormatter,
        "csharp": CSharpTableFormatter,
        "cs": CSharpTableFormatter,
        "php": PHPTableFormatter,
        "ruby": RubyTableFormatter,
        "rb": RubyTableFormatter,
        "kotlin": KotlinTableFormatter,
        "kt": KotlinTableFormatter,
        "kts": KotlinTableFormatter,
        "bash": BashTableFormatter,
        "sh": BashTableFormatter,
        "go": GoTableFormatter,
        "rust": RustTableFormatter,
        "rs": RustTableFormatter,
        "c": CppTableFormatter,
        "cpp": CppTableFormatter,
        "h": CppTableFormatter,
        "hpp": CppTableFormatter,
    }


def _data_language_formatters() -> dict[str, type[Any]]:
    """Load formatter classes for data and markup languages."""
    from .css_formatter import CSSFormatter
    from .html_formatter import HtmlFormatter
    from .json_formatter import JSONFormatter
    from .markdown_formatter import MarkdownFormatter
    from .sql_formatter_wrapper import SQLFormatterWrapper
    from .yaml_formatter import YAMLFormatter

    return {
        "yaml": YAMLFormatter,
        "yml": YAMLFormatter,
        "json": JSONFormatter,
        "jsonc": JSONFormatter,
        "json5": JSONFormatter,
        "css": CSSFormatter,
        "html": HtmlFormatter,
        "htm": HtmlFormatter,
        "markdown": MarkdownFormatter,
        "md": MarkdownFormatter,
        "sql": SQLFormatterWrapper,
    }


def _load_language_formatters(
    logger: logging.Logger,
) -> dict[str, type[Any]] | None:
    """Load all bundled formatter classes or report a broken installation."""
    try:
        return {**_code_language_formatters(), **_data_language_formatters()}
    except ImportError as error:
        logger.warning("Failed to register language formatters: %s", error)
        return None


def register_language_formatters(registry: type[Any], logger: logging.Logger) -> None:
    """Register every bundled language formatter while tolerating a default cycle."""
    language_formatters = _load_language_formatters(logger)
    if language_formatters is None:
        registry._language_registration_complete = False
        return
    for language, formatter_class in language_formatters.items():
        for format_type in ("full", "compact", "csv", "signatures"):
            registry.register_language_formatter(language, format_type, formatter_class)
    registry._language_registration_complete = True
    ensure_default_language_formatter(registry, logger)
    logger.info("Registered language-specific formatters")
