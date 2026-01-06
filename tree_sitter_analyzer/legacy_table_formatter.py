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
        """Full table format - compliant with format specification"""
        lines = []

        # Header - use package.class format for single class
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

        # Get package name once for use throughout
        package_name = (data.get("package") or {}).get("name", "")

        # Package section (if package exists)
        if package_name and package_name != "unknown":
            lines.append("## Package")
            lines.append(f"`{package_name}`")
            lines.append("")

        # Imports section (should appear before class info)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append(f"```{self.language}")
            for imp in imports:
                statement = str(imp.get("statement", ""))
                lines.append(statement)
            lines.append("```")
            lines.append("")

        # Class Info section (required by specification)
        lines.append("## Class Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")

        # Use package_name or default to "unknown" for display
        display_package = package_name if package_name else "unknown"

        if len(classes) >= 1:
            class_info = classes[0]
            class_name = str(class_info.get("name", "Unknown"))
            lines.append(f"| Name | {class_name} |")
            lines.append(f"| Package | {display_package} |")
            lines.append(f"| Type | {str(class_info.get('type', 'class'))} |")
            lines.append(f"| Access | {str(class_info.get('visibility', 'public'))} |")

            # Lines
            line_range = class_info.get("line_range", {})
            lines_str = f"{line_range.get('start', 1)}-{line_range.get('end', 50)}"

            # Add optional fields
            extends = class_info.get("extends")
            if extends:
                lines.append(f"| Extends | {extends} |")

            implements = class_info.get("implements", [])
            if implements:
                lines.append(f"| Implements | {', '.join(implements)} |")
        else:
            # Empty data case
            lines.append("| Name | Unknown |")
            lines.append(f"| Package | {display_package} |")
            lines.append("| Type | class |")
            lines.append("| Access | public |")

        lines.append("")

        # Check if we have multiple classes to organize by class
        all_methods = data.get("methods", []) or []
        all_fields = data.get("fields", []) or []

        if len(classes) > 1:
            # Multiple classes: add Classes Overview section
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                class_name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods and fields for this class
                class_methods = self._get_class_methods(data, line_range)
                class_fields = self._get_class_fields(data, line_range)

                lines.append(
                    f"| {class_name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_fields)} |"
                )
            lines.append("")

            # Multiple classes: organize methods and fields by class
            for class_info in classes:
                class_name = str(class_info.get("name", "Unknown"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                lines.append(f"## {class_name} ({lines_str})")

                # Get methods for this class
                class_methods = self._get_class_methods(data, line_range)

                if class_methods:
                    lines.append("### Methods")
                    lines.append("| Name | Return Type | Parameters | Access | Line |")
                    lines.append("|------|-------------|------------|--------|------|")

                    for method in class_methods:
                        name = str(method.get("name", ""))
                        # Constructors don't have return types
                        is_constructor = method.get("is_constructor", False)
                        return_type = (
                            "-"
                            if is_constructor
                            else str(method.get("return_type", "void"))
                        )

                        # Format parameters as "type1 param1, type2 param2"
                        params = method.get("parameters", [])
                        param_strs = []
                        for param in params:
                            if isinstance(param, dict):
                                param_type = str(param.get("type", "Object"))
                                param_name = str(param.get("name", "param"))
                                param_strs.append(f"{param_type} {param_name}")
                            elif isinstance(param, str):
                                param_strs.append(param)
                            else:
                                param_strs.append(str(param))
                        params_str = ", ".join(param_strs)

                        access = str(method.get("visibility", "public"))
                        line_num = method.get("line_range", {}).get("start", 0)

                        lines.append(
                            f"| {name} | {return_type} | {params_str} | {access} | {line_num} |"
                        )
                    lines.append("")

                # Get fields for this class
                class_fields = self._get_class_fields(data, line_range)

                if class_fields:
                    lines.append("### Fields")
                    lines.append("| Name | Type | Access | Static | Final | Line |")
                    lines.append("|------|------|--------|--------|-------|------|")

                    for field in class_fields:
                        name = str(field.get("name", ""))
                        field_type = str(field.get("type", "Object"))
                        access = str(field.get("visibility", "private"))

                        # Check modifiers for static and final
                        modifiers = field.get("modifiers", [])
                        is_static = "static" in modifiers or field.get(
                            "is_static", False
                        )
                        is_final = "final" in modifiers or field.get("is_final", False)

                        static_str = "true" if is_static else "false"
                        final_str = "true" if is_final else "false"

                        line_num = field.get("line_range", {}).get("start", 0)

                        lines.append(
                            f"| {name} | {field_type} | {access} | {static_str} | {final_str} | {line_num} |"
                        )
                    lines.append("")
        else:
            # Single class or no classes: use original format
            # Methods section (required by specification)
            lines.append("## Methods")
            if all_methods:
                lines.append("| Name | Return Type | Parameters | Access | Line |")
                lines.append("|------|-------------|------------|--------|------|")

                for method in all_methods:
                    name = str(method.get("name", ""))
                    # Constructors don't have return types
                    is_constructor = method.get("is_constructor", False)
                    return_type = (
                        "-"
                        if is_constructor
                        else str(method.get("return_type", "void"))
                    )

                    # Format parameters as "type1 param1, type2 param2"
                    params = method.get("parameters", [])
                    param_strs = []
                    for param in params:
                        if isinstance(param, dict):
                            param_type = str(param.get("type", "Object"))
                            param_name = str(param.get("name", "param"))
                            param_strs.append(f"{param_type} {param_name}")
                        elif isinstance(param, str):
                            param_strs.append(param)
                        else:
                            param_strs.append(str(param))
                    params_str = ", ".join(param_strs)

                    access = str(method.get("visibility", "public"))
                    line_num = method.get("line_range", {}).get("start", 0)

                    lines.append(
                        f"| {name} | {return_type} | {params_str} | {access} | {line_num} |"
                    )
            else:
                lines.append("| Name | Return Type | Parameters | Access | Line |")
                lines.append("|------|-------------|------------|--------|------|")
            lines.append("")

            # Fields section (required by specification)
            lines.append("## Fields")
            if all_fields:
                lines.append("| Name | Type | Access | Static | Final | Line |")
                lines.append("|------|------|--------|--------|-------|------|")

                for field in all_fields:
                    name = str(field.get("name", ""))
                    field_type = str(field.get("type", "Object"))
                    access = str(field.get("visibility", "private"))

                    # Check modifiers for static and final
                    modifiers = field.get("modifiers", [])
                    is_static = "static" in modifiers or field.get("is_static", False)
                    is_final = "final" in modifiers or field.get("is_final", False)

                    static_str = "true" if is_static else "false"
                    final_str = "true" if is_final else "false"

                    line_num = field.get("line_range", {}).get("start", 0)

                    lines.append(
                        f"| {name} | {field_type} | {access} | {static_str} | {final_str} | {line_num} |"
                    )
            else:
                lines.append("| Name | Type | Access | Static | Final | Line |")
                lines.append("|------|------|--------|--------|-------|------|")
            lines.append("")

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

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Convert visibility to symbol."""
        symbols = {
            "public": "+",
            "private": "-",
            "protected": "#",
            "package": "~",
            "internal": "~",
        }
        return symbols.get(visibility.lower(), "+")

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format - compliant with format specification"""
        lines = []

        # Get package and class info
        package_name = data.get("package", {}).get("name", "")
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        class_name = classes[0].get("name", "Unknown") if classes else "Unknown"

        # Header - full qualified name
        if package_name:
            lines.append(f"# {package_name}.{class_name}")
        else:
            lines.append(f"# {class_name}")
        lines.append("")

        # Info section
        methods = data.get("methods", []) or []
        fields = data.get("fields", []) or []

        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        if package_name:
            lines.append(f"| Package | {package_name} |")
        lines.append(f"| Methods | {len(methods)} |")
        lines.append(f"| Fields | {len(fields)} |")
        lines.append("")

        # Methods section with compact signature format
        lines.append("## Methods")
        if methods:
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                row = self._format_compact_method_row(method)
                lines.append(row)
        else:
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")
        lines.append("")

        # Fields section
        lines.append("## Fields")
        if fields:
            lines.append("| Field | Type | V | L |")
            lines.append("|-------|------|---|---|")

            for field in fields:
                name = str(field.get("name", ""))
                field_type = self._abbreviate_type(str(field.get("type", "Object")))
                visibility = self._get_visibility_symbol(
                    str(field.get("visibility", "private"))
                )
                line_range = field.get("line_range", {})
                start = line_range.get("start", 0) if line_range else 0

                lines.append(f"| {name} | {field_type} | {visibility} | {start} |")
        else:
            lines.append("| Field | Type | V | L |")
            lines.append("|-------|------|---|---|")
        lines.append("")

        # Remove trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format - compliant with format specification"""
        output = io.StringIO()
        writer = csv.writer(
            output, lineterminator="\n"
        )  # Explicitly specify newline character

        # Header - specification compliant
        writer.writerow(
            [
                "Type",
                "Name",
                "ReturnType",
                "Parameters",
                "Access",
                "Static",
                "Final",
                "Line",
            ]
        )

        # Class row
        classes = data.get("classes", [])
        if classes:
            for cls in classes:
                writer.writerow(
                    [
                        str(cls.get("type", "class")),
                        str(cls.get("name", "Unknown")),
                        "",  # No return type for class
                        "",  # No parameters for class
                        str(cls.get("visibility", "public")),
                        "false",  # Classes are not static
                        "true" if "final" in cls.get("modifiers", []) else "false",
                        cls.get("line_range", {}).get("start", 0),
                    ]
                )

        # Method rows
        for method in data.get("methods", []):
            # Format parameters as "param1:type1;param2:type2"
            params = method.get("parameters", [])
            param_strs = []
            for param in params:
                if isinstance(param, dict):
                    param_type = str(param.get("type", "Object"))
                    param_name = str(param.get("name", "param"))
                    param_strs.append(f"{param_name}:{param_type}")
                elif isinstance(param, str):
                    # Handle "type param" format - convert to "param:type"
                    parts = param.strip().split()
                    if len(parts) >= 2:
                        # Everything except last part is type, last part is name
                        param_type = " ".join(parts[:-1])
                        param_name = parts[-1]
                        param_strs.append(f"{param_name}:{param_type}")
                    else:
                        # Fallback for single-part parameters
                        param_strs.append(param)
                else:
                    param_strs.append(str(param))
            params_str = ";".join(param_strs)

            # Check modifiers for static and final
            modifiers = method.get("modifiers", [])
            is_static = "static" in modifiers or method.get("is_static", False)
            is_final = "final" in modifiers or method.get("is_final", False)

            writer.writerow(
                [
                    "constructor" if method.get("is_constructor", False) else "method",
                    str(method.get("name", "")),
                    str(method.get("return_type", "void")),
                    params_str,
                    str(method.get("visibility", "public")),
                    "true" if is_static else "false",
                    "true" if is_final else "false",
                    method.get("line_range", {}).get("start", 0),
                ]
            )

        # Field rows
        for field in data.get("fields", []):
            # Check modifiers for static and final
            modifiers = field.get("modifiers", [])
            is_static = "static" in modifiers or field.get("is_static", False)
            is_final = "final" in modifiers or field.get("is_final", False)

            writer.writerow(
                [
                    "field",
                    str(field.get("name", "")),
                    str(field.get("type", "Object")),
                    "",  # No parameters for fields
                    str(field.get("visibility", "private")),
                    "true" if is_static else "false",
                    "true" if is_final else "false",
                    field.get("line_range", {}).get("start", 0),
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
