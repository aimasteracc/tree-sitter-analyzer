#!/usr/bin/env python3
"""
Base formatter for language-specific formatting.
"""

import csv
import io
from abc import ABC, abstractmethod
from typing import Any

from ._csv_safety import csv_safe_row


class BaseFormatter(ABC):
    """Base class for language-specific formatters"""

    def __init__(self) -> None:
        """Base class for language-specific formatters"""
        # Base implementation - B027 workaround by adding an operation
        self._init_timestamp = None

    def format(self, data: Any) -> str:
        """
        Unified format method for OutputManager compatibility.

        This method provides a common interface that OutputManager can call
        without needing to know the specific formatter implementation.

        Default implementation delegates to format_structure for dict data.
        Subclasses can override this to provide custom dispatching logic.

        Args:
            data: The data to format (AnalysisResult, dict, or other types)

        Returns:
            Formatted string representation
        """
        if isinstance(data, dict):
            return self.format_structure(data)
        else:
            # Fallback: convert to string
            import json

            return json.dumps(data, indent=2, ensure_ascii=False)

    @abstractmethod
    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output"""
        pass

    @abstractmethod
    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output"""
        pass

    @abstractmethod
    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output"""
        pass

    @abstractmethod
    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output"""
        pass


class BaseTableFormatter(BaseFormatter):
    """Base class for language-specific table formatters"""

    def __init__(self, format_type: str = "full") -> None:
        self.format_type = format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Default summary implementation for table formatters"""
        return self._format_compact_table(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Default advanced implementation for table formatters"""
        if output_format == "json":
            import json

            return json.dumps(analysis_result, indent=2, ensure_ascii=False)
        return self._format_full_table(analysis_result)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output"""
        original_format_type = self.format_type
        self.format_type = table_type
        try:
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def _get_platform_newline(self) -> str:
        """Get platform-specific newline code"""
        import os

        return "\r\n" if os.name == "nt" else "\n"  # Windows uses \r\n, others use \n

    def _convert_to_platform_newlines(self, text: str) -> str:
        """Convert regular \n to platform-specific newline code"""
        platform_newline = self._get_platform_newline()
        if platform_newline != "\n":
            return text.replace("\n", platform_newline)
        return text

    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """Format structure data in table format"""
        if self.format_type == "full":
            result = self._format_full_table(structure_data)
        elif self.format_type == "compact":
            result = self._format_compact_table(structure_data)
        elif self.format_type == "csv":
            result = self._format_csv(structure_data)
        elif self.format_type == "signatures":
            # Lightweight directory mode: name →returnType(Np) L-L per method.
            # Delegates to the mixin if available; raises with the sorted list of
            # languages that DO support signatures (#449: error must be enumerable).
            if not hasattr(self, "_format_signatures_table"):
                _SIGNATURES_SUPPORTED = sorted(["java", "python", "typescript"])
                raise ValueError(
                    "signatures format not supported for this language formatter; "
                    f"supported languages: {', '.join(_SIGNATURES_SUPPORTED)}"
                )
            result = self._format_signatures_table(structure_data)
        else:
            raise ValueError(f"Unsupported format type: {self.format_type}")

        # Finally convert to platform-specific newline code
        if self.format_type == "csv":
            return result

        return self._convert_to_platform_newlines(result)

    @abstractmethod
    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format (language-specific implementation)"""
        pass

    @abstractmethod
    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format (language-specific implementation)"""
        pass

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format (common implementation).

        r37dk (dogfood): flattened nesting 6 → 3 by extracting per-row
        builders (``_csv_field_row`` / ``_csv_method_row``).

        Data rows are sanitized with ``csv_safe_row``: Python 3.10's
        ``csv.writer`` raises ``_csv.Error: need to escape, but no escapechar
        set`` on a NULL byte and emits a bare ``\\r`` unquoted (producing an
        unreadable CSV). The previous ``escapechar="\\"`` silenced the NULL
        error but doubled literal backslashes in ordinary fields (Windows
        paths, regex), a format regression. Stripping the unrepresentable
        controls instead leaves the dialect — and backslashes — untouched.
        """
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        writer.writerow(
            ["Type", "Name", "Signature", "Visibility", "Lines", "Complexity", "Doc"]
        )
        for field in data.get("fields", []):
            writer.writerow(csv_safe_row(self._csv_field_row(field)))
        for method in data.get("methods", []):
            writer.writerow(csv_safe_row(self._csv_method_row(method)))

        csv_content = output.getvalue()
        csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
        csv_content = csv_content.rstrip("\n")
        output.close()
        return csv_content

    def _csv_field_row(self, field: dict[str, Any]) -> list[Any]:
        """Build the CSV row for one ``field`` entry."""
        name = str(field.get("name", ""))
        ftype = str(field.get("type", ""))
        signature = f"{name}:{ftype}"
        line_range = field.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        javadoc = str(field.get("javadoc", ""))
        return [
            "Field",
            self._clean_csv_text(name),
            self._clean_csv_text(signature),
            self._clean_csv_text(str(field.get("visibility", ""))),
            lines_str,
            "",
            self._clean_csv_text(self._extract_doc_summary(javadoc)),
        ]

    def _csv_method_row(self, method: dict[str, Any]) -> list[Any]:
        """Build the CSV row for one ``method`` entry."""
        row_type = "Constructor" if method.get("is_constructor", False) else "Method"
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        javadoc = str(method.get("javadoc", ""))
        return [
            row_type,
            self._clean_csv_text(str(method.get("name", ""))),
            self._clean_csv_text(self._create_full_signature(method)),
            self._clean_csv_text(str(method.get("visibility", ""))),
            lines_str,
            method.get("complexity_score", 0),
            self._clean_csv_text(self._extract_doc_summary(javadoc)),
        ]

    # Common helper methods
    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create complete method signature"""
        params = method.get("parameters", [])
        param_strs = []
        for param in params:
            if isinstance(param, dict):
                param_type = str(param.get("type", "Object"))
                param_name = str(param.get("name", "param"))
                param_strs.append(f"{param_name}:{param_type}")
            else:
                param_strs.append(str(param))

        params_str = ", ".join(param_strs)
        return_type = str(method.get("return_type", "void"))

        modifiers = []
        if method.get("is_static", False):
            modifiers.append("[static]")

        modifier_str = " ".join(modifiers)
        signature = f"({params_str}):{return_type}"

        if modifier_str:
            signature += f" {modifier_str}"

        return signature

    def _convert_visibility(self, visibility: str) -> str:
        """Convert visibility to symbol"""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, visibility)

    def _extract_doc_summary(self, javadoc: str) -> str:
        """Extract summary from documentation"""
        if not javadoc:
            return "-"

        # Remove comment symbols
        clean_doc = javadoc.replace("/**", "")
        clean_doc = clean_doc.replace("*/", "")
        clean_doc = clean_doc.replace("*", "")
        clean_doc = clean_doc.strip()

        # Get first line
        lines = clean_doc.split("\n")
        first_line = lines[0].strip()

        # Truncate if too long
        if len(first_line) > 50:
            first_line = first_line[:47] + "..."

        return first_line.replace("|", "\\|").replace("\n", " ")

    def _clean_csv_text(self, text: str) -> str:
        """Text cleaning for CSV format"""
        if not text:
            return ""

        # Remove null bytes and normalize whitespace
        cleaned = text.replace("\0", "")
        cleaned = cleaned.replace("\r\n", " ")
        cleaned = cleaned.replace("\r", " ")
        cleaned = cleaned.replace("\n", " ")
        cleaned = " ".join(cleaned.split())
        cleaned = cleaned.replace('"', '""')

        return cleaned

    # Public aliases used by companion formatter helper modules
    convert_visibility = _convert_visibility
    extract_doc_summary = _extract_doc_summary
    clean_csv_text = _clean_csv_text
