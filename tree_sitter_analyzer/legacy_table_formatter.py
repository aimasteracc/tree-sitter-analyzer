#!/usr/bin/env python3
"""
Legacy Table Formatter for Tree-sitter Analyzer

This module provides the restored v1.6.1.4 TableFormatter implementation
to ensure backward compatibility for analyze_code_structure tool.
"""

from typing import Any

from ._legacy_table_formatter_helpers import (
    append_compact_fields_section as _append_compact_fields_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_compact_info_section as _append_compact_info_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_compact_methods_section as _append_compact_methods_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_detail_fields_section as _append_detail_fields_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_detailed_methods_section as _append_detailed_methods_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_full_class_info_section as _append_full_class_info_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_full_imports_section as _append_full_imports_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_full_package_section as _append_full_package_section_helper,
)
from ._legacy_table_formatter_helpers import (
    append_multi_class_full_sections as _append_multi_class_full_sections_helper,
)
from ._legacy_table_formatter_helpers import (
    append_single_class_full_sections as _append_single_class_full_sections_helper,
)
from ._legacy_table_formatter_helpers import (
    clean_csv_text as _clean_csv_text_helper,
)
from ._legacy_table_formatter_helpers import (
    compact_table_header as _compact_table_header_helper,
)
from ._legacy_table_formatter_helpers import (
    convert_visibility as _convert_visibility_helper,
)
from ._legacy_table_formatter_helpers import (
    create_full_signature as _create_full_signature_helper,
)
from ._legacy_table_formatter_helpers import (
    detail_method_groups as _detail_method_groups_helper,
)
from ._legacy_table_formatter_helpers import (
    extract_doc_summary as _extract_doc_summary_helper,
)
from ._legacy_table_formatter_helpers import (
    format_csv as _format_csv_helper,
)
from ._legacy_table_formatter_helpers import (
    full_table_header as _full_table_header_helper,
)
from ._legacy_table_formatter_helpers import (
    get_class_fields as _get_class_fields_helper,
)
from ._legacy_table_formatter_helpers import (
    get_class_methods as _get_class_methods_helper,
)
from ._legacy_table_formatter_helpers import (
    get_platform_newline as _get_platform_newline_helper,
)
from ._legacy_table_formatter_helpers import (
    get_visibility_symbol as _get_visibility_symbol_helper,
)
from ._legacy_table_formatter_helpers import (
    shorten_type as _shorten_type_helper,
)


class LegacyTableFormatter:
    """
    Legacy table formatter — renamed to DefaultTableFormatter.

    This class is kept for backward compatibility. New code should use
    ``default_table_formatter.DefaultTableFormatter`` instead.
    """

    def __init__(
        self,
        format_type: str = "full",
        language: str = "java",
        include_javadoc: bool = False,
    ):
        """
        Initialize the legacy table formatter.

        Args:
            format_type: Format type (full, compact, csv)
            language: Programming language for syntax highlighting
            include_javadoc: Whether to include JavaDoc/documentation
        """
        self.format_type = format_type
        self.language = language
        self.include_javadoc = include_javadoc

    _get_platform_newline = staticmethod(_get_platform_newline_helper)
    _get_class_methods = staticmethod(_get_class_methods_helper)
    _get_class_fields = staticmethod(_get_class_fields_helper)
    _format_csv = staticmethod(_format_csv_helper)
    _get_visibility_symbol = staticmethod(_get_visibility_symbol_helper)
    _create_full_signature = staticmethod(_create_full_signature_helper)
    _shorten_type = staticmethod(_shorten_type_helper)
    _convert_visibility = staticmethod(_convert_visibility_helper)
    _extract_doc_summary = staticmethod(_extract_doc_summary_helper)
    _clean_csv_text = staticmethod(_clean_csv_text_helper)

    # Convert between formats: _convert_to_platform_newlines
    def _convert_to_platform_newlines(self, text: str) -> str:
        """Convert standard \\n to platform-specific newline characters"""
        platform_newline = self._get_platform_newline()
        if platform_newline != "\n":
            return text.replace("\n", platform_newline)
        return text

    # Format data for output: format_structure
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """
        Format structure data as table.

        Args:
            structure_data: Dictionary containing analysis results

        Returns:
            Formatted string in the specified format

        Raises:
            ValueError: If format_type is not supported
        """
        if self.format_type == "full":
            result = self._format_full_table(structure_data)
        elif self.format_type == "compact":
            result = self._format_compact_table(structure_data)
        elif self.format_type == "csv":
            result = self._format_csv(structure_data)
        else:
            raise ValueError(f"Unsupported format type: {self.format_type}")

        # Convert to platform-specific newline characters
        # Skip newline conversion for CSV format
        if self.format_type in ["csv"]:
            return result

        return self._convert_to_platform_newlines(result)

    # Format data for output: _format_full_table
    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format - compliant with format specification"""
        lines = []

        classes = data.get("classes", [])
        if classes is None:
            classes = []

        package_name = (data.get("package") or {}).get("name", "")
        header = _full_table_header_helper(data, classes)
        lines.append(f"# {header}")
        lines.append("")

        _append_full_package_section_helper(lines, package_name)
        _append_full_imports_section_helper(
            lines, data.get("imports", []), self.language
        )
        display_package = package_name if package_name else "unknown"
        _append_full_class_info_section_helper(lines, classes, display_package)

        if len(classes) > 1:
            _append_multi_class_full_sections_helper(
                lines,
                data,
                classes,
                self._get_class_methods,
                self._get_class_fields,
            )
        else:
            _append_single_class_full_sections_helper(
                lines,
                data.get("methods", []) or [],
                data.get("fields", []) or [],
            )

        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    # Format data for output: _format_class_details
    def _format_class_details(
        self, class_info: dict[str, Any], data: dict[str, Any]
    ) -> list[str]:
        """Format detailed information for a single class."""
        lines = []

        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

        # Class header
        lines.append(f"## {name} ({lines_str})")

        # Get class-specific methods and fields
        class_methods = self._get_class_methods(data, line_range)
        class_fields = self._get_class_fields(data, line_range)

        _append_detail_fields_section_helper(
            lines,
            class_fields,
            self.include_javadoc,
        )

        # Methods section - separate by type
        constructors = [m for m in class_methods if m.get("is_constructor", False)]
        regular_methods = [
            m for m in class_methods if not m.get("is_constructor", False)
        ]

        _append_detailed_methods_section_helper(
            lines,
            "Constructors",
            constructors,
            self._format_method_row_detailed,
            constructor=True,
        )

        for method_group, title in _detail_method_groups_helper(regular_methods):
            _append_detailed_methods_section_helper(
                lines,
                title,
                method_group,
                self._format_method_row_detailed,
            )

        return lines

    # Format data for output: _format_method_row_detailed
    def _format_method_row_detailed(self, method: dict[str, Any]) -> str:
        """Format method row for detailed class view."""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 0)
        doc = (
            self._extract_doc_summary(str(method.get("javadoc", "")))
            if self.include_javadoc
            else "-"
        )

        return f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"

    # Format data for output: _format_compact_method_row
    def _format_compact_method_row(self, method: dict[str, Any]) -> str:
        """Format method row for compact table format."""
        name = str(method.get("name", ""))
        signature = self._create_compact_signature(method)
        visibility = self._get_visibility_symbol(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        start = line_range.get("start", 0) if line_range else 0
        end = line_range.get("end", 0) if line_range else 0
        lines_str = f"{start}-{end}" if end > start else str(start)
        complexity = method.get("complexity_score", 1)
        doc = "-"

        return f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature like (S,S):b"""
        params = method.get("parameters", [])
        return_type = str(method.get("return_type", "void"))

        # Abbreviate parameter types
        param_abbrevs = []
        for param in params:
            param_type = str(param.get("type", "Object"))
            param_abbrevs.append(self._abbreviate_type(param_type))

        params_str = ",".join(param_abbrevs) if param_abbrevs else ""
        return_abbrev = self._abbreviate_type(return_type)

        return f"({params_str}):{return_abbrev}"

    def _abbreviate_type(self, type_str: str) -> str:
        """Abbreviate type name for compact display."""
        # Common abbreviations
        abbrev_map = {
            "String": "S",
            "string": "S",
            "int": "i",
            "Integer": "I",
            "long": "l",
            "Long": "L",
            "double": "d",
            "Double": "D",
            "float": "f",
            "Float": "F",
            "boolean": "b",
            "Boolean": "B",
            "void": "void",
            "Object": "O",
            "List": "L",
            "Map": "M",
            "Set": "St",
            "Collection": "C",
        }

        # Handle generic types like Map<String, Object>
        if "<" in type_str:
            base_type = type_str.split("<")[0]
            inner = type_str[type_str.index("<") + 1 : type_str.rindex(">")]
            inner_parts = [p.strip() for p in inner.split(",")]
            inner_abbrevs = [self._abbreviate_type(p) for p in inner_parts]
            base_abbrev = abbrev_map.get(base_type, base_type[0].upper())
            return f"{base_abbrev}<{', '.join(inner_abbrevs)}>"

        # Handle array types
        if type_str.endswith("[]"):
            base = type_str[:-2]
            return f"{self._abbreviate_type(base)}[]"

        return abbrev_map.get(type_str, type_str[0].upper() if type_str else "?")

    # Format data for output: _format_compact_table
    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format - compliant with format specification"""
        lines = []

        package_name = data.get("package", {}).get("name", "")
        classes = data.get("classes", [])
        if classes is None:
            classes = []

        lines.append(f"# {_compact_table_header_helper(package_name, classes)}")
        lines.append("")

        methods = data.get("methods", []) or []
        fields = data.get("fields", []) or []

        _append_compact_info_section_helper(lines, package_name, methods, fields)
        _append_compact_methods_section_helper(
            lines,
            methods,
            self._format_compact_method_row,
        )
        _append_compact_fields_section_helper(lines, fields, self._abbreviate_type)

        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)
