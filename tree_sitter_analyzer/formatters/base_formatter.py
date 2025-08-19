#!/usr/bin/env python3
"""
Base formatter for language-specific table formatting.
"""

import csv
import io
from abc import ABC, abstractmethod
from typing import Any


class BaseTableFormatter(ABC):
    """Base class for language-specific table formatters"""

    def __init__(self, format_type: str = "full"):
        self.format_type = format_type

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
        """CSV format (common implementation)"""
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        # Header
        writer.writerow(
            ["Type", "Name", "Signature", "Visibility", "Lines", "Complexity", "Doc"]
        )

        # Fields
        for field in data.get("fields", []):
            writer.writerow(
                [
                    "Field",
                    str(field.get("name", "")),
                    f"{str(field.get('name', ''))}:{str(field.get('type', ''))}",
                    str(field.get("visibility", "")),
                    f"{field.get('line_range', {}).get('start', 0)}-{field.get('line_range', {}).get('end', 0)}",
                    "",
                    self._clean_csv_text(
                        self._extract_doc_summary(str(field.get("javadoc", "")))
                    ),
                ]
            )

        # Methods
        for method in data.get("methods", []):
            writer.writerow(
                [
                    "Constructor" if method.get("is_constructor", False) else "Method",
                    str(method.get("name", "")),
                    self._clean_csv_text(self._create_full_signature(method)),
                    str(method.get("visibility", "")),
                    f"{method.get('line_range', {}).get('start', 0)}-{method.get('line_range', {}).get('end', 0)}",
                    method.get("complexity_score", 0),
                    self._clean_csv_text(
                        self._extract_doc_summary(str(method.get("javadoc", "")))
                    ),
                ]
            )

        csv_content = output.getvalue()
        csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
        csv_content = csv_content.rstrip("\n")
        output.close()

        return csv_content

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
        clean_doc = (
            javadoc.replace("/**", "").replace("*/", "").replace("*", "").strip()
        )

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

        cleaned = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        cleaned = " ".join(cleaned.split())
        cleaned = cleaned.replace('"', '""')

        return cleaned
