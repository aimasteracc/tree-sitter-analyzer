#!/usr/bin/env python3
"""
Base formatter for language-specific formatting.
"""

import csv
import io
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseFormatter(ABC):
    """Base class for language-specific formatters"""

    def __init__(self):
        pass

    @abstractmethod
    def format_summary(self, analysis_result: Dict[str, Any]) -> str:
        """Format summary output"""
        pass

    @abstractmethod
    def format_structure(self, analysis_result: Dict[str, Any]) -> str:
        """Format structure analysis output"""
        pass

    @abstractmethod
    def format_advanced(self, analysis_result: Dict[str, Any], output_format: str = "json") -> str:
        """Format advanced analysis output"""
        pass

    @abstractmethod
    def format_table(self, analysis_result: Dict[str, Any], table_type: str = "full") -> str:
        """Format table output"""
        pass


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

        # Header (English)
        writer.writerow(
            ["Type", "Name", "Signature", "Visibility", "Lines", "Complexity", "Documentation"]
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


class GenericTableFormatter(BaseTableFormatter):
    """Generic table formatter for unknown languages"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for generic languages"""
        lines = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Basic Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| File | {file_name} |")
        lines.append(f"| Elements | {stats.get('total_elements', 0)} |")
        lines.append("")

        # Methods/Functions (if any)
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods/Functions")
            lines.append("| Name | Signature | Lines | Complexity |")
            lines.append("|------|-----------|-------|------------|")

            for method in methods:
                name = str(method.get("name", ""))
                signature = self._create_generic_signature(method)
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 0)

                lines.append(f"| {name} | {signature} | {lines_str} | {complexity} |")
            lines.append("")

        # Fields/Properties (if any)
        fields = data.get("fields", [])
        if fields:
            lines.append("## Fields/Properties")
            lines.append("| Name | Type | Lines |")
            lines.append("|------|------|-------|")

            for field in fields:
                name = str(field.get("name", ""))
                field_type = str(field.get("type", ""))
                line_range = field.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                lines.append(f"| {name} | {field_type} | {lines_str} |")
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for generic languages"""
        lines = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| File | {file_name} |")
        lines.append(f"| Elements | {stats.get('total_elements', 0)} |")
        lines.append("")

        # Methods (compact)
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | L | Cx |")
            lines.append("|--------|-----|---|----| ")

            for method in methods:
                name = str(method.get("name", ""))
                signature = self._create_generic_compact_signature(method)
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 0)

                lines.append(f"| {name} | {signature} | {lines_str} | {complexity} |")
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _create_generic_signature(self, method: dict[str, Any]) -> str:
        """Create generic method signature"""
        params = method.get("parameters", [])
        param_strs = []
        
        for param in params:
            if isinstance(param, dict):
                param_name = param.get("name", "param")
                param_type = param.get("type", "any")
                param_strs.append(f"{param_name}:{param_type}")
            else:
                param_strs.append(str(param))
        
        params_str = ", ".join(param_strs)
        return_type = method.get("return_type", "any")
        
        return f"({params_str}):{return_type}"

    def _create_generic_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact generic method signature"""
        params = method.get("parameters", [])
        param_count = len(params) if params else 0
        return_type = method.get("return_type", "any")
        
        if param_count == 0:
            return f"():{return_type}"
        else:
            return f"({param_count} params):{return_type}"
