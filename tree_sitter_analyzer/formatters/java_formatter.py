#!/usr/bin/env python3
"""
Java-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class JavaTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Java"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Java"""
        lines = []

        # Header - Java (multi-class supported)
        classes = data.get("classes", [])
        package_name = (data.get("package") or {}).get("name", "unknown")

        if len(classes) > 1:
            # If multiple classes exist, use filename
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            if package_name == "unknown":
                lines.append(f"# {file_name}")
            else:
                lines.append(f"# {package_name}.{file_name}")
        else:
            # Single class: use class name
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            if package_name == "unknown":
                lines.append(f"# {class_name}")
            else:
                lines.append(f"# {package_name}.{class_name}")
        lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```java")
            for imp in imports:
                lines.append(str(imp.get("statement", "")))
            lines.append("```")
            lines.append("")

        # Class Info - Java (multi-class aware)
        if len(classes) > 1:
            lines.append("## Classes")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                visibility = str(class_info.get("visibility", "package"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods/fields within the class range
                class_methods = [
                    m
                    for m in data.get("methods", [])
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]
                class_fields = [
                    f
                    for f in data.get("fields", [])
                    if line_range.get("start", 0)
                    <= f.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_fields)} |"
                )
        else:
            # Single class details
            lines.append("## Class Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")

            class_info = data.get("classes", [{}])[0] if data.get("classes") else {}
            stats = data.get("statistics") or {}

            lines.append(f"| Package | {package_name} |")
            lines.append(f"| Type | {str(class_info.get('type', 'class'))} |")
            lines.append(
                f"| Visibility | {str(class_info.get('visibility', 'package'))} |"
            )
            lines.append(
                f"| Lines | {class_info.get('line_range', {}).get('start', 0)}-{class_info.get('line_range', {}).get('end', 0)} |"
            )
            lines.append(f"| Total Methods | {stats.get('method_count', 0)} |")
            lines.append(f"| Total Fields | {stats.get('field_count', 0)} |")

        lines.append("")

        # Fields
        fields = data.get("fields", [])
        if fields:
            lines.append("## Fields")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")

            for field in fields:
                name = str(field.get("name", ""))
                field_type = str(field.get("type", ""))
                visibility = self._convert_visibility(str(field.get("visibility", "")))
                modifiers = ",".join([str(m) for m in field.get("modifiers", [])])
                line = field.get("line_range", {}).get("start", 0)
                doc = str(field.get("javadoc", "")) or "-"
                doc = doc.replace("\n", " ").replace("|", "\\|")[:50]

                lines.append(
                    f"| {name} | {field_type} | {visibility} | {modifiers} | {line} | {doc} |"
                )
            lines.append("")

        # Constructor
        constructors = [
            m for m in (data.get("methods") or []) if m.get("is_constructor", False)
        ]
        if constructors:
            lines.append("## Constructor")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in constructors:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Public Methods
        public_methods = [
            m
            for m in (data.get("methods") or [])
            if not m.get("is_constructor", False)
            and str(m.get("visibility")) == "public"
        ]
        if public_methods:
            lines.append("## Public Methods")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in public_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Private Methods
        private_methods = [
            m
            for m in (data.get("methods") or [])
            if not m.get("is_constructor", False)
            and str(m.get("visibility")) == "private"
        ]
        if private_methods:
            lines.append("## Private Methods")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in private_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Enum sections - generate individual sections for each enum
        enum_classes = [c for c in classes if c.get("type") == "enum"]
        for enum_class in enum_classes:
            enum_name = enum_class.get("name", "Unknown")
            lines.append(f"## {enum_name}")

            # Enum info
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append("| Type | enum |")
            lines.append(f"| Visibility | {enum_class.get('visibility', 'package')} |")
            line_range = enum_class.get("line_range", {})
            lines.append(
                f"| Lines | {line_range.get('start', 0)}-{line_range.get('end', 0)} |"
            )

            # Enum constants (if available)
            enum_constants = enum_class.get("constants", [])
            if enum_constants:
                lines.append(f"| Constants | {', '.join(enum_constants)} |")

            lines.append("")

            # Enum fields
            enum_line_start = line_range.get("start", 0)
            enum_line_end = line_range.get("end", 0)
            enum_fields = [
                f
                for f in fields
                if enum_line_start
                <= f.get("line_range", {}).get("start", 0)
                <= enum_line_end
            ]
            if enum_fields:
                lines.append("### Fields")
                lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
                lines.append("|------|------|-----|-----------|------|-----|")
                for field in enum_fields:
                    name = str(field.get("name", ""))
                    field_type = str(field.get("type", ""))
                    visibility = self._convert_visibility(
                        str(field.get("visibility", ""))
                    )
                    modifiers = ",".join([str(m) for m in field.get("modifiers", [])])
                    line = field.get("line_range", {}).get("start", 0)
                    doc = str(field.get("javadoc", "")) or "-"
                    doc = doc.replace("\n", " ").replace("|", "\\|")[:50]
                    lines.append(
                        f"| {name} | {field_type} | {visibility} | {modifiers} | {line} | {doc} |"
                    )
                lines.append("")

            # Enum methods
            enum_methods = [
                m
                for m in (data.get("methods") or [])
                if enum_line_start
                <= m.get("line_range", {}).get("start", 0)
                <= enum_line_end
            ]
            if enum_methods:
                lines.append("### Methods")
                lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|------|----|----|")
                for method in enum_methods:
                    lines.append(self._format_method_row(method))
                lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Java"""
        lines = []

        # Header
        package_name = (data.get("package") or {}).get("name", "unknown")
        classes = data.get("classes", [])
        if len(classes) > 1:
            # If multiple classes exist, use filename
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            if package_name == "unknown":
                lines.append(f"# {file_name}")
            else:
                lines.append(f"# {package_name}.{file_name}")
        else:
            # Single class: use class name
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            if package_name == "unknown":
                lines.append(f"# {class_name}")
            else:
                lines.append(f"# {package_name}.{class_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Package | {package_name} |")
        lines.append(f"| Methods | {stats.get('method_count', 0)} |")
        lines.append(f"| Fields | {stats.get('field_count', 0)} |")
        lines.append("")

        # Methods (compact)
        methods = data.get("methods", [])
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
                complexity = method.get("complexity_score", 0)
                doc = self._clean_csv_text(
                    self._extract_doc_summary(str(method.get("javadoc", "")))
                )

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
                )
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for Java"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        cols_str = "5-6"  # default placeholder
        complexity = method.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(method.get("javadoc", "")))
        )

        return f"| {name} | {signature} | {visibility} | {lines_str} | {cols_str} | {complexity} | {doc} |"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature for Java"""
        params = method.get("parameters", [])
        param_types = [
            self._shorten_type(p.get("type", "O") if isinstance(p, dict) else str(p))
            for p in params
        ]
        params_str = ",".join(param_types)
        return_type = self._shorten_type(method.get("return_type", "void"))

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for Java tables"""
        if type_name is None:
            return "O"

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
            result = (
                type_name.replace("Map<", "M<")
                .replace("String", "S")
                .replace("Object", "O")
            )
            return str(result)

        # List<String> -> L<S>
        if "List<" in type_name:
            result = type_name.replace("List<", "L<").replace("String", "S")
            return str(result)

        # String[] -> S[]
        if "[]" in type_name:
            base_type = type_name.replace("[]", "")
            if base_type:
                result = type_mapping.get(base_type, base_type[0].upper()) + "[]"
                return str(result)
            else:
                return "O[]"

        result = type_mapping.get(type_name, type_name)
        return str(result)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Java"""
        # Set the format type based on table_type parameter
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            # Handle json format separately
            if table_type == "json":
                return self._format_json(analysis_result)
            # Use the existing format_structure method
            return self.format_structure(analysis_result)
        finally:
            # Restore original format type
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Java"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Java"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Java"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)

    def _format_json(self, data: dict[str, Any]) -> str:
        """Format data as JSON"""
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\n"
