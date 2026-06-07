#!/usr/bin/env python3
"""
Formatter Registry

Dynamic formatter registration and management system.
Provides extensible formatter architecture following the Registry pattern.

This is the unified entry point for all formatter operations in the project.
"""

import logging
from typing import Any

from ..models import CodeElement
from ._formatter_interface import IFormatter, IStructureFormatter  # noqa: F401

logger = logging.getLogger(__name__)


class FormatterRegistry:
    """
    Unified registry for managing and providing formatter instances.

    Implements the Registry pattern to allow dynamic registration
    and retrieval of formatters by format name and language.

    This is the primary entry point for formatter operations:
    - Use get_formatter() for format-based lookup
    - Use get_formatter_for_language() for language-specific formatting
    """

    _formatters: dict[str, type[IFormatter]] = {}
    _language_formatters: dict[str, Any] = {}
    _default_language_formatter: type[Any] | None = None

    @classmethod
    # Format data for output: register_formatter
    def register_formatter(cls, formatter_class: type[IFormatter]) -> None:
        """
        Register a formatter class in the registry.

        Args:
            formatter_class: Formatter class implementing IFormatter

        Raises:
            ValueError: If formatter_class doesn't implement IFormatter
        """
        if not issubclass(formatter_class, IFormatter):
            raise ValueError("Formatter class must implement IFormatter interface")

        format_name = formatter_class.get_format_name()
        if not format_name:
            raise ValueError("Formatter must provide a non-empty format name")

        if format_name in cls._formatters:
            warn_msg = f"Overriding existing formatter for format: {format_name}"
            logger.warning(warn_msg)

        cls._formatters[format_name] = formatter_class
        logger.debug(f"Registered formatter for format: {format_name}")

    @classmethod
    # Format data for output: get_formatter
    def get_formatter(cls, format_name: str) -> IFormatter:
        """
        Get a formatter instance for the specified format.

        Args:
            format_name: Name of the format to get formatter for

        Returns:
            Formatter instance

        Raises:
            ValueError: If format is not supported
        """
        formatters = cls._formatters
        if format_name not in formatters:
            available_formats = list(formatters)
            err_msg = f"Unsupported format: {format_name}. Available formats: {available_formats}"
            raise ValueError(err_msg)

        formatter_class = formatters[format_name]
        return formatter_class()

    @classmethod
    # Format data for output: get_available_formats
    def get_available_formats(cls) -> list[str]:
        """
        Get list of all available format names.

        Returns:
            List of available format names
        """
        return list(cls._formatters.keys())

    @classmethod
    # Format data for output: is_format_supported
    def is_format_supported(cls, format_name: str) -> bool:
        """
        Check if a format is supported.

        Args:
            format_name: Format name to check

        Returns:
            True if format is supported
        """
        return format_name in cls._formatters

    @classmethod
    # Format data for output: unregister_formatter
    def unregister_formatter(cls, format_name: str) -> bool:
        """
        Unregister a formatter for the specified format.

        Args:
            format_name: Format name to unregister

        Returns:
            True if formatter was unregistered, False if not found
        """
        if format_name in cls._formatters:
            del cls._formatters[format_name]
            dbg_msg = f"Unregistered formatter for format: {format_name}"
            logger.debug(dbg_msg)
            return True
        return False

    @classmethod
    def clear_registry(cls) -> None:
        """
        Clear all registered formatters.

        This method is primarily for testing purposes.
        """
        cls._formatters.clear()
        cls._language_formatters.clear()
        cls._default_language_formatter = None
        logger.debug("Cleared all registered formatters")

    @classmethod
    # Format data for output: register_language_formatter
    def register_language_formatter(
        cls,
        language: str,
        format_type: str,
        formatter_class: type[Any],
    ) -> None:
        """
        Register a language-specific formatter.

        Args:
            language: Programming language name (e.g., "java", "python")
            format_type: Format type (e.g., "full", "compact", "csv")
            formatter_class: Formatter class to register

        Example:
            >>> FormatterRegistry.register_language_formatter(
            ...     "java", "full", JavaTableFormatter
            ... )
        """
        lang_key = language.lower()
        if lang_key not in cls._language_formatters:
            cls._language_formatters[lang_key] = {}

        cls._language_formatters[lang_key][format_type] = formatter_class
        cls_name = formatter_class.__name__
        dbg_msg = (
            f"Registered language formatter: {language}/{format_type} -> {cls_name}"
        )
        logger.debug(dbg_msg)

    @classmethod
    # Format data for output: set_default_language_formatter
    def set_default_language_formatter(cls, formatter_class: type[Any]) -> None:
        """
        Set the default formatter class for languages without specific formatters.

        Args:
            formatter_class: Default formatter class
        """
        cls._default_language_formatter = formatter_class
        logger.debug(f"Set default language formatter: {formatter_class.__name__}")

    @classmethod
    # Format data for output: get_formatter_for_language
    def get_formatter_for_language(
        cls,
        language: str,
        format_type: str = "full",
        **kwargs: Any,
    ) -> Any:
        """
        Get a formatter instance for the specified language and format type.

        This is the primary method for obtaining formatters in the unified architecture.
        It handles language-specific formatter lookup with fallback to defaults.

        Args:
            language: Programming language name
            format_type: Format type (full, compact, csv, json, etc.)
            **kwargs: Additional arguments passed to formatter constructor
                - include_javadoc: bool - Include JavaDoc in output

        Returns:
            Formatter instance appropriate for the language and format

        Example:
            >>> formatter = FormatterRegistry.get_formatter_for_language("java", "full")
            >>> output = formatter.format_structure(analysis_data)
        """
        lang_key = language.lower()
        format_key = format_type.lower()

        # Check for language-specific formatter first
        lang_formatters = cls._language_formatters.get(lang_key, {})
        if lang_key in cls._language_formatters and format_key in lang_formatters:
            formatter_class = lang_formatters[format_key]
            return cls._create_formatter_instance(
                formatter_class, format_key, language, **kwargs
            )

        # Fall back to default language formatter if set
        if cls._default_language_formatter is not None:
            return cls._create_formatter_instance(
                cls._default_language_formatter, format_key, language, **kwargs
            )

        # Final fallback to generic format-based formatter
        if format_key in cls._formatters:
            return cls._formatters[format_key]()

        # If nothing found, raise error with helpful message
        available = cls.get_available_formats()
        raise ValueError(
            f"No formatter found for language '{language}' "
            f"with format '{format_type}'. Available formats: {available}"
        )

    @classmethod
    # Format data for output: _create_formatter_instance
    def _create_formatter_instance(
        cls,
        formatter_class: type[Any],
        format_type: str,
        language: str,
        **kwargs: Any,
    ) -> Any:
        """
        Create a formatter instance with appropriate constructor arguments.

        Handles different formatter constructor signatures gracefully.
        """
        # Extract kwargs before try to reduce nesting depth
        include_javadoc = kwargs.get("include_javadoc", False)
        try:
            # Try full signature first (for TableFormatter-style classes)
            return formatter_class(
                format_type=format_type,
                language=language,
                include_javadoc=include_javadoc,
            )
        except TypeError:
            return cls._try_format_type_or_bare(formatter_class, format_type)

    @classmethod
    def _try_format_type_or_bare(
        cls, formatter_class: type[Any], format_type: str
    ) -> Any:
        """Fallback: try format_type-only constructor, then bare constructor."""
        try:
            return formatter_class(format_type=format_type)
        except TypeError:
            return formatter_class()

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """
        Get list of all languages with registered formatters.

        Returns:
            List of language names
        """
        return list(cls._language_formatters.keys())

    @classmethod
    def is_language_supported(cls, language: str) -> bool:
        """
        Check if a language has specific formatters registered.

        Args:
            language: Language name to check

        Returns:
            True if language has specific formatters
        """
        return language.lower() in cls._language_formatters


# Built-in formatter implementations


class JsonFormatter(IFormatter):
    """JSON formatter for CodeElement lists"""

    @staticmethod
    # Format data for output: get_format_name
    def get_format_name() -> str:
        return "json"

    @staticmethod
    def _element_to_dict(element: Any) -> dict[str, Any]:
        """Convert one element to a JSON-serialisable dict."""
        elem_type = getattr(element, "element_type", "unknown")
        d: dict[str, Any] = {
            "name": element.name,
            "type": elem_type,
            "start_line": element.start_line,
            "end_line": element.end_line,
            "language": element.language,
        }
        if hasattr(element, "parameters"):
            d["parameters"] = element.parameters
        if hasattr(element, "return_type"):
            d["return_type"] = element.return_type
        if hasattr(element, "visibility"):
            d["visibility"] = element.visibility
        if hasattr(element, "modifiers"):
            d["modifiers"] = element.modifiers
        if hasattr(element, "tag_name"):
            d["tag_name"] = element.tag_name
        if hasattr(element, "selector"):
            d["selector"] = element.selector
        if hasattr(element, "element_class"):
            d["element_class"] = element.element_class
        return d

    # Format data for output: format
    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as JSON"""
        import json

        result = [JsonFormatter._element_to_dict(el) for el in elements]
        return json.dumps(result, indent=2, ensure_ascii=False)


class CsvFormatter(IFormatter):
    """CSV formatter for CodeElement lists"""

    @staticmethod
    # Format data for output: get_format_name
    def get_format_name() -> str:
        return "csv"

    # Format data for output: format
    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as CSV"""
        import csv
        import io

        output = io.StringIO()
        # escapechar handles control chars (e.g. NULL bytes) that Python 3.10's
        # csv.writer cannot quote — without it, "\x00" raises _csv.Error there.
        writer = csv.writer(output, lineterminator="\n", escapechar="\\")

        # Write header
        writer.writerow(
            [
                "Type",
                "Name",
                "Start Line",
                "End Line",
                "Language",
                "Visibility",
                "Parameters",
                "Return Type",
                "Modifiers",
            ]
        )

        # Write data rows
        for element in elements:
            elem_type = getattr(element, "element_type", "unknown")
            visibility = getattr(element, "visibility", "")
            return_type = getattr(element, "return_type", "")
            params_raw = getattr(element, "parameters", [])
            mods_raw = getattr(element, "modifiers", [])
            params_str = str(params_raw)
            mods_str = str(mods_raw)
            writer.writerow(
                [
                    elem_type,
                    element.name,
                    element.start_line,
                    element.end_line,
                    element.language,
                    visibility,
                    params_str,
                    return_type,
                    mods_str,
                ]
            )

        csv_content = output.getvalue()
        output.close()
        return csv_content.rstrip("\n")


def _append_full_element_lines(lines: list[str], element: CodeElement) -> None:
    """Append the per-element block lines used by ``FullFormatter.format``.

    r37cl (dogfood): tool flagged ``FullFormatter.format`` at nesting
    depth 7 (L498). The per-element ``hasattr`` chain (visibility →
    parameters → return_type) moves here so the outer formatter body
    stays flat.
    """
    lines.append(f"  {element.name}")
    lines.append(f"    Lines: {element.start_line}-{element.end_line}")
    lines.append(f"    Language: {element.language}")

    if hasattr(element, "visibility"):
        lines.append(f"    Visibility: {element.visibility}")
    if hasattr(element, "parameters") and (params := element.parameters):
        params_str = ", ".join(map(str, params))
        lines.append(f"    Parameters: {params_str}")
    if hasattr(element, "return_type"):
        ret_type = getattr(element, "return_type", None)
        if ret_type:
            lines.append(f"    Return Type: {ret_type}")
    lines.append("")


class FullFormatter(IFormatter):
    """Full table formatter for CodeElement lists"""

    @staticmethod
    # Format data for output: get_format_name
    def get_format_name() -> str:
        return "full"

    # Format data for output: format
    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as full table"""
        if not elements:
            return "No elements found."

        lines = []
        lines.append("=" * 80)
        lines.append("CODE STRUCTURE ANALYSIS")
        lines.append("=" * 80)
        lines.append("")

        # Group elements by type
        element_groups: dict[str, Any] = {}
        for element in elements:
            element_type = getattr(element, "element_type", "unknown")
            if element_type not in element_groups:
                element_groups[element_type] = []
            element_groups[element_type].append(element)

        # Format each group
        for element_type, group_elements in element_groups.items():
            type_label = element_type.upper()
            group_count = len(group_elements)
            lines.append(f"{type_label}S ({group_count})")
            lines.append("-" * 40)
            for element in group_elements:
                # r37cl (dogfood): extracted to flatten nesting 7 → 3.
                _append_full_element_lines(lines, element)
            lines.append("")

        return "\n".join(lines)


class CompactFormatter(IFormatter):
    """Compact formatter for CodeElement lists"""

    @staticmethod
    # Format data for output: get_format_name
    def get_format_name() -> str:
        return "compact"

    # Format data for output: format
    def format(self, elements: list[CodeElement]) -> str:
        """Format elements in compact format"""
        if not elements:
            return "No elements found."

        lines = []
        lines.append("CODE ELEMENTS")
        lines.append("-" * 20)

        for element in elements:
            element_type = getattr(element, "element_type", "unknown")
            visibility = getattr(element, "visibility", "")
            vis_symbol = self._get_visibility_symbol(visibility)

            line = f"{vis_symbol} {element.name} ({element_type}) [{element.start_line}-{element.end_line}]"
            lines.append(line)

        return "\n".join(lines)

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Get symbol for visibility"""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, "?")


# Register built-in formatters
def register_builtin_formatters() -> None:
    """Register all built-in formatters"""
    FormatterRegistry.register_formatter(JsonFormatter)

    # Fallback to simple formatters first to avoid circular import issues
    FormatterRegistry.register_formatter(CsvFormatter)
    FormatterRegistry.register_formatter(FullFormatter)
    FormatterRegistry.register_formatter(CompactFormatter)

    # Register language-specific formatters
    _register_language_formatters_safe()


# Format data for output: _register_language_formatters_safe
def _register_language_formatters_safe() -> None:
    """Register language-specific formatters safely to avoid circular imports"""
    try:
        # Import language-specific formatters
        from ..default_table_formatter import DefaultTableFormatter
        from .cpp_formatter import CppTableFormatter
        from .csharp_formatter import CSharpTableFormatter
        from .css_formatter import CSSFormatter
        from .go_formatter import GoTableFormatter
        from .html_formatter import HtmlFormatter
        from .java_formatter import JavaTableFormatter
        from .javascript_formatter import JavaScriptTableFormatter
        from .json_formatter import JSONFormatter
        from .kotlin_formatter import KotlinTableFormatter
        from .markdown_formatter import MarkdownFormatter
        from .php_formatter import PHPTableFormatter
        from .python_formatter import PythonTableFormatter
        from .ruby_formatter import RubyTableFormatter
        from .rust_formatter import RustTableFormatter
        from .sql_formatter_wrapper import SQLFormatterWrapper
        from .typescript_formatter import TypeScriptTableFormatter
        from .yaml_formatter import YAMLFormatter

        # Set DefaultTableFormatter as default for unsupported languages
        FormatterRegistry.set_default_language_formatter(DefaultTableFormatter)

        # Language to formatter mapping
        language_formatters = {
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
            "go": GoTableFormatter,
            "rust": RustTableFormatter,
            "rs": RustTableFormatter,
            "c": CppTableFormatter,
            "cpp": CppTableFormatter,
            "h": CppTableFormatter,
            "hpp": CppTableFormatter,
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

        # Register each language with all format types
        # "signatures" is the lightweight method-directory mode (~25 % of full tokens).
        format_types = ["full", "compact", "csv", "signatures"]
        for lang, formatter_class in language_formatters.items():
            for fmt in format_types:
                FormatterRegistry.register_language_formatter(
                    lang, fmt, formatter_class
                )

        logger.info("Registered language-specific formatters")
    except ImportError as e:
        logger.warning(f"Failed to register language formatters: {e}")


# NOTE: HTML formatters are intentionally excluded from analyze_code_structure
# as they are not part of the v1.6.1.4 specification and cause format regression.
# HTML formatters can still be registered separately for other tools if needed.


# Auto-register built-in formatters when module is imported
register_builtin_formatters()
