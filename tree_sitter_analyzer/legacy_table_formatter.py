#!/usr/bin/env python3
"""
Legacy Table Formatter for Tree-sitter Analyzer

This module provides the restored v1.6.1.4 TableFormatter implementation
to ensure backward compatibility for analyze_code_structure tool.
"""

import csv
import io
from typing import Any


class LegacyTableFormatter:
    """
    Legacy table formatter for code analysis results.

    This class restores the exact v1.6.1.4 behavior for the analyze_code_structure
    tool, ensuring backward compatibility and specification compliance.
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

    def _get_platform_newline(self) -> str:
        """Get platform-specific newline character"""
        import os

        return "\r\n" if os.name == "nt" else "\n"  # Windows uses \r\n, others use \n

    def _convert_to_platform_newlines(self, text: str) -> str:
        """Convert standard \\n to platform-specific newline characters"""
        platform_newline = self._get_platform_newline()
        if platform_newline != "\n":
            return text.replace("\n", platform_newline)
        return text

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

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format - organized by class"""
        lines = []

        # Header - use package.class format for single class, filename for multi-class files
        classes = data.get("classes", [])
        if classes is None:
            classes = []

        # Determine header format
        package_name = (data.get("package") or {}).get("name", "")
        if len(classes) == 1:
            # Single class: use package.ClassName format
            class_name = classes[0].get("name", "Unknown")
            if package_name:
                header = f"{package_name}.{class_name}"
            else:
                header = class_name
        else:
            # Multiple classes or no classes: use filename or default
            file_path = data.get("file_path", "")
            if file_path and file_path != "Unknown":
                file_name = file_path.split("/")[-1].split("\\")[-1]
                if file_name.endswith(".java"):
                    file_name = file_name[:-5]  # Remove .java extension
                elif file_name.endswith(".py"):
                    file_name = file_name[:-3]  # Remove .py extension
                elif file_name.endswith(".js"):
                    file_name = file_name[:-3]  # Remove .js extension

                if package_name and len(classes) == 0:
                    # No classes but has package: use package.filename
                    header = f"{package_name}.{file_name}"
                else:
                    header = file_name
            else:
                # No file path: use default format
                if package_name:
                    header = f"{package_name}.Unknown"
                else:
                    header = "unknown.Unknown"

        lines.append(f"# {header}")
        lines.append("")

        # Package info
        package_name = (data.get("package") or {}).get("name", "")
        if package_name:
            lines.append("## Package")
            lines.append(f"`{package_name}`")
            lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append(f"```{self.language}")
            for imp in imports:
                lines.append(str(imp.get("statement", "")))
            lines.append("```")
            lines.append("")

        # Class Info section (for single class files or empty data)
        if len(classes) == 1 or len(classes) == 0:
            lines.append("## Class Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")

            package_name = (data.get("package") or {}).get("name", "unknown")

            if len(classes) == 1:
                class_info = classes[0]
                lines.append(f"| Package | {package_name} |")
                lines.append(f"| Type | {str(class_info.get('type', 'class'))} |")
                lines.append(
                    f"| Visibility | {str(class_info.get('visibility', 'public'))} |"
                )

                # Lines
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 1)}-{line_range.get('end', 50)}"
                lines.append(f"| Lines | {lines_str} |")
            else:
                # Empty data case
                lines.append(f"| Package | {package_name} |")
                lines.append("| Type | class |")
                lines.append("| Visibility | public |")
                lines.append("| Lines | 0-0 |")

            # Count methods and fields
            all_methods = data.get("methods", []) or []
            all_fields = data.get("fields", []) or []
            lines.append(f"| Total Methods | {len(all_methods)} |")
            lines.append(f"| Total Fields | {len(all_fields)} |")
            lines.append("")

        # Classes Overview
        if len(classes) > 1:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Calculate method and field counts for this class
                class_methods = self._get_class_methods(data, line_range)
                class_fields = self._get_class_fields(data, line_range)

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_fields)} |"
                )
            lines.append("")

        # Detailed class information - organized by class
        for class_info in classes:
            lines.extend(self._format_class_details(class_info, data))

        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _get_class_methods(
        self, data: dict[str, Any], class_line_range: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get methods that belong to a specific class based on line range, excluding nested classes."""
        methods = data.get("methods", [])
        classes = data.get("classes", [])
        class_methods = []

        # Get nested class ranges to exclude their methods
        nested_class_ranges = []
        for cls in classes:
            cls_range = cls.get("line_range", {})
            cls_start = cls_range.get("start", 0)
            cls_end = cls_range.get("end", 0)

            # If this class is nested within the current class range
            if class_line_range.get(
                "start", 0
            ) < cls_start and cls_end < class_line_range.get("end", 0):
                nested_class_ranges.append((cls_start, cls_end))

        for method in methods:
            method_line = method.get("line_range", {}).get("start", 0)

            # Check if method is within the class range
            if (
                class_line_range.get("start", 0)
                <= method_line
                <= class_line_range.get("end", 0)
            ):
                # Check if method is NOT within any nested class
                in_nested_class = False
                for nested_start, nested_end in nested_class_ranges:
                    if nested_start <= method_line <= nested_end:
                        in_nested_class = True
                        break

                if not in_nested_class:
                    class_methods.append(method)

        return class_methods

    def _get_class_fields(
        self, data: dict[str, Any], class_line_range: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get fields that belong to a specific class based on line range, excluding nested classes."""
        fields = data.get("fields", [])
        classes = data.get("classes", [])
        class_fields = []

        # Get nested class ranges to exclude their fields
        nested_class_ranges = []
        for cls in classes:
            cls_range = cls.get("line_range", {})
            cls_start = cls_range.get("start", 0)
            cls_end = cls_range.get("end", 0)

            # If this class is nested within the current class range
            if class_line_range.get(
                "start", 0
            ) < cls_start and cls_end < class_line_range.get("end", 0):
                nested_class_ranges.append((cls_start, cls_end))

        for field in fields:
            field_line = field.get("line_range", {}).get("start", 0)

            # Check if field is within the class range
            if (
                class_line_range.get("start", 0)
                <= field_line
                <= class_line_range.get("end", 0)
            ):
                # Check if field is NOT within any nested class
                in_nested_class = False
                for nested_start, nested_end in nested_class_ranges:
                    if nested_start <= field_line <= nested_end:
                        in_nested_class = True
                        break

                if not in_nested_class:
                    class_fields.append(field)

        return class_fields

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

        # Fields section
        if class_fields:
            lines.append("### Fields")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")

            for field in class_fields:
                name_field = str(field.get("name", ""))
                type_field = str(field.get("type", ""))
                visibility = self._convert_visibility(str(field.get("visibility", "")))
                modifiers = ",".join(field.get("modifiers", []))
                line_num = field.get("line_range", {}).get("start", 0)
                doc = (
                    self._extract_doc_summary(str(field.get("javadoc", "")))
                    if self.include_javadoc
                    else "-"
                )

                lines.append(
                    f"| {name_field} | {type_field} | {visibility} | {modifiers} | {line_num} | {doc} |"
                )
            lines.append("")

        # Methods section - separate by type
        constructors = [m for m in class_methods if m.get("is_constructor", False)]
        regular_methods = [
            m for m in class_methods if not m.get("is_constructor", False)
        ]

        # Constructors
        if constructors:
            lines.append("### Constructors")
            lines.append("| Constructor | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|-------------|-----------|-----|-------|----|----|")

            for method in constructors:
                lines.append(self._format_method_row_detailed(method))
            lines.append("")

        # Methods grouped by visibility
        public_methods = [
            m for m in regular_methods if m.get("visibility", "") == "public"
        ]
        protected_methods = [
            m for m in regular_methods if m.get("visibility", "") == "protected"
        ]
        package_methods = [
            m for m in regular_methods if m.get("visibility", "") == "package"
        ]
        private_methods = [
            m for m in regular_methods if m.get("visibility", "") == "private"
        ]

        for method_group, title in [
            (public_methods, "Public Methods"),
            (protected_methods, "Protected Methods"),
            (package_methods, "Package Methods"),
            (private_methods, "Private Methods"),
        ]:
            if method_group:
                lines.append(f"### {title}")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")

                for method in method_group:
                    lines.append(self._format_method_row_detailed(method))
                lines.append("")

        return lines

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

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format"""
        lines = []

        # Header
        package_name = (data.get("package") or {}).get("name", "unknown")
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
        lines.append(f"# {package_name}.{class_name}")
        lines.append("")

        # Basic information
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Package | {package_name} |")
        lines.append(f"| Methods | {stats.get('method_count', 0)} |")
        lines.append(f"| Fields | {stats.get('field_count', 0)} |")
        lines.append("")

        # Methods (simplified version with COMPLEXITY)
        methods = data.get("methods", [])
        if methods is None:
            methods = []
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                name = str(method.get("name", ""))
                signature = self._create_compact_signature(method)
                visibility = self._convert_visibility(str(method.get("visibility", "")))
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get(
                    "complexity_score", 0
                )  # CRITICAL: Include complexity
                doc = self._clean_csv_text(
                    self._extract_doc_summary(str(method.get("javadoc", "")))
                )

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
                )
            lines.append("")

        # Fields (if any)
        fields = data.get("fields", [])
        if fields:
            lines.append("## Fields")
            lines.append("| Field | Type | V | L |")
            lines.append("|-------|------|---|---|")

            for field in fields:
                name = str(field.get("name", ""))
                field_type = self._shorten_type(field.get("type", "Object"))
                visibility = self._convert_visibility(str(field.get("visibility", "")))
                line_range = field.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                lines.append(f"| {name} | {field_type} | {visibility} | {lines_str} |")
            lines.append("")

        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format - simple structure matching v1.6.1.4"""
        output = io.StringIO()
        writer = csv.writer(
            output, lineterminator="\n"
        )  # Explicitly specify newline character

        # Header - simple structure
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
                    "",  # Empty complexity for fields
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
                    method.get("complexity_score", 0),  # Include complexity
                    self._clean_csv_text(
                        self._extract_doc_summary(str(method.get("javadoc", "")))
                    ),
                ]
            )

        # Control CSV output newlines
        csv_content = output.getvalue()
        # Unify all newline patterns and remove trailing newlines
        csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
        csv_content = csv_content.rstrip("\n")
        output.close()

        return csv_content

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create complete method signature"""
        params = method.get("parameters", [])
        param_strs = []
        for param in params:
            # Handle both dict and string parameters
            if isinstance(param, dict):
                param_type = str(param.get("type", "Object"))
                param_name = str(param.get("name", "param"))
                param_strs.append(f"{param_name}:{param_type}")
            elif isinstance(param, str):
                # If parameter is already a string, use it directly
                param_strs.append(param)
            else:
                # Fallback for other types
                param_strs.append(str(param))

        params_str = ",".join(param_strs)  # Remove space after comma
        return_type = str(method.get("return_type", "void"))

        modifiers = []
        if method.get("is_static", False):
            modifiers.append("[static]")

        modifier_str = " ".join(modifiers)
        signature = f"({params_str}):{return_type}"

        if modifier_str:
            signature += f" {modifier_str}"

        return signature

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature"""
        params = method.get("parameters", [])
        param_types = []
        for p in params:
            if isinstance(p, dict):
                param_types.append(self._shorten_type(p.get("type", "O")))
            elif isinstance(p, str):
                # If parameter is already a string, shorten it directly
                param_types.append(self._shorten_type(p))
            else:
                # Fallback for other types
                param_types.append(self._shorten_type(str(p)))

        params_str = ",".join(param_types)
        return_type = self._shorten_type(method.get("return_type", "void"))

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name"""
        if type_name is None:
            return "O"

        # Convert non-string types to string
        if not isinstance(type_name, str):
            type_name = str(type_name)

        type_mapping = {
            "String": "S",
            "int": "i",
            "long": "l",
            "double": "d",
            "boolean": "b",
            "void": "void",
            "Object": "O",
            "Exception": "E",
            "SQLException": "SE",
            "IllegalArgumentException": "IAE",
            "RuntimeException": "RE",
        }

        # Map<String,Object> -> M<S,O>
        if "Map<" in type_name:
            return str(
                type_name.replace("Map<", "M<")
                .replace("String", "S")
                .replace("Object", "O")
            )

        # List<String> -> L<S>
        if "List<" in type_name:
            return str(type_name.replace("List<", "L<").replace("String", "S"))

        # String[] -> S[]
        if "[]" in type_name:
            base_type = type_name.replace("[]", "")
            if base_type:
                return str(type_mapping.get(base_type, base_type[0].upper())) + "[]"
            else:
                return "O[]"

        return str(type_mapping.get(type_name, type_name))

    def _convert_visibility(self, visibility: str) -> str:
        """Convert visibility to symbol"""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, visibility)

    def _extract_doc_summary(self, javadoc: str) -> str:
        """Extract summary from JavaDoc"""
        if not javadoc:
            return "-"

        # Remove comment symbols
        clean_doc = (
            javadoc.replace("/**", "").replace("*/", "").replace("*", "").strip()
        )

        # Get first sentence
        if clean_doc:
            sentences = clean_doc.split(".")
            if sentences:
                return sentences[0].strip()

        return "-"

    def _clean_csv_text(self, text: str) -> str:
        """Clean text for CSV output"""
        if not text or text == "-":
            return "-"

        # Remove newlines and extra whitespace
        cleaned = " ".join(text.split())

        # Escape quotes for CSV
        cleaned = cleaned.replace('"', '""')

        return cleaned
