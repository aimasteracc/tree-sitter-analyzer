#!/usr/bin/env python3
"""
C#-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class CSharpTableFormatter(BaseTableFormatter):
    """Table formatter specialized for C#"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for C#"""
        lines = []

        # Header - C# (multi-class supported)
        classes = data.get("classes", [])
        namespace_name = self._extract_namespace(data)

        if len(classes) > 1:
            # If multiple classes exist, use filename
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            if namespace_name == "unknown":
                lines.append(f"# {file_name}")
            else:
                lines.append(f"# {namespace_name}.{file_name}")
        else:
            # Single class: use class name
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            if namespace_name == "unknown":
                lines.append(f"# {class_name}")
            else:
                lines.append(f"# {namespace_name}.{class_name}")
        lines.append("")

        # Using directives (imports)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```csharp")
            for imp in imports:
                import_text = imp.get("raw_text", "").strip()
                if import_text:
                    lines.append(import_text)
            lines.append("```")
            lines.append("")

        # Class Info - C# (multi-class aware)
        if len(classes) > 1:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("class_type", "class"))
                visibility = str(class_info.get("visibility", "internal"))
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
            lines.append("## Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")

            class_info = data.get("classes", [{}])[0] if data.get("classes") else {}
            stats = data.get("statistics") or {}

            lines.append(f"| Namespace | {namespace_name} |")
            lines.append(f"| Type | {str(class_info.get('class_type', 'class'))} |")
            lines.append(
                f"| Visibility | {str(class_info.get('visibility', 'internal'))} |"
            )
            lines.append(f"| Methods | {stats.get('method_count', 0)} |")
            lines.append(f"| Fields | {stats.get('field_count', 0)} |")

        lines.append("")

        # Methods section
        methods = data.get("methods", [])
        if methods:
            # Group methods by class if multiple classes
            if len(classes) > 1:
                for class_info in classes:
                    class_name = class_info.get("name", "Unknown")
                    line_range = class_info.get("line_range", {})
                    class_methods = [
                        m
                        for m in methods
                        if line_range.get("start", 0)
                        <= m.get("line_range", {}).get("start", 0)
                        <= line_range.get("end", 0)
                    ]

                    if class_methods:
                        lines.append(f"## {class_name} Methods")
                        self._add_methods_table(lines, class_methods)
                        lines.append("")
            else:
                lines.append("## Methods")
                self._add_methods_table(lines, methods)
                lines.append("")

        # Fields section
        fields = data.get("fields", [])
        if fields:
            # Group fields by class if multiple classes
            if len(classes) > 1:
                for class_info in classes:
                    class_name = class_info.get("name", "Unknown")
                    line_range = class_info.get("line_range", {})
                    class_fields = [
                        f
                        for f in fields
                        if line_range.get("start", 0)
                        <= f.get("line_range", {}).get("start", 0)
                        <= line_range.get("end", 0)
                    ]

                    if class_fields:
                        lines.append(f"## {class_name} Fields")
                        self._add_fields_table(lines, class_fields)
                        lines.append("")
            else:
                lines.append("## Fields")
                self._add_fields_table(lines, fields)
                lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for C#"""
        lines = []

        # Header
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Info
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")

        namespace_name = self._extract_namespace(data)
        stats = data.get("statistics") or {}

        lines.append(f"| Namespace | {namespace_name} |")
        lines.append(f"| Methods | {stats.get('method_count', 0)} |")
        lines.append(f"| Fields | {stats.get('field_count', 0)} |")
        lines.append("")

        # Methods
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                name = str(method.get("name", ""))
                params = method.get("parameters", [])
                return_type = str(method.get("return_type", "void"))

                # Format parameters
                if params:
                    param_str = ",".join(
                        [self._format_param_type(p) for p in params[:2]]
                    )
                    if len(params) > 2:
                        param_str += ",..."
                else:
                    param_str = ""

                # Format return type (abbreviated)
                ret_str = self._abbreviate_type(return_type)

                signature = f"({param_str}):{ret_str}"
                visibility = self._get_visibility_symbol(
                    method.get("visibility", "private")
                )
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 1)
                has_doc = "✓" if method.get("documentation") else "-"

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {has_doc} |"
                )

        return "\n".join(lines)

    def _add_methods_table(
        self, lines: list[str], methods: list[dict[str, Any]]
    ) -> None:
        """Add methods table to lines"""
        lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
        lines.append("|--------|-----------|-----|-------|----|----|")

        for method in methods:
            name = str(method.get("name", ""))
            params = method.get("parameters", [])
            return_type = str(method.get("return_type", "void"))

            # Format parameters
            param_strs = []
            for param in params:
                param_strs.append(self._format_parameter(param))

            signature = f"({', '.join(param_strs)}):{return_type}"
            visibility = self._get_visibility_symbol(
                method.get("visibility", "private")
            )
            line_range = method.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            complexity = method.get("complexity_score", 1)
            has_doc = "✓" if method.get("documentation") else "-"

            lines.append(
                f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {has_doc} |"
            )

    def _add_fields_table(self, lines: list[str], fields: list[dict[str, Any]]) -> None:
        """Add fields table to lines"""
        lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
        lines.append("|------|------|-----|-----------|------|-----|")

        for field in fields:
            name = str(field.get("name", ""))
            field_type = str(field.get("variable_type", "unknown"))
            visibility = self._get_visibility_symbol(field.get("visibility", "private"))
            modifiers = ",".join(field.get("modifiers", []))
            line = field.get("line_range", {}).get("start", 0)
            has_doc = "✓" if field.get("documentation") else "-"

            lines.append(
                f"| {name} | {field_type} | {visibility} | {modifiers} | {line} | {has_doc} |"
            )

    def _extract_namespace(self, data: dict[str, Any]) -> str:
        """Extract namespace from data"""
        # Try to get namespace from classes
        classes = data.get("classes", [])
        if classes:
            full_name = classes[0].get("full_qualified_name", "")
            if full_name and "." in full_name:
                # Extract namespace from full qualified name
                parts = full_name.rsplit(".", 1)
                if len(parts) == 2:
                    return parts[0]

        return "unknown"

    def _format_parameter(self, param: str) -> str:
        """Format a parameter string"""
        # Parameter is already formatted as "type name" or just "type"
        return param

    def _format_param_type(self, param: str) -> str:
        """Extract and abbreviate parameter type"""
        # Extract type from "type name" format
        parts = param.strip().split()
        if parts:
            return self._abbreviate_type(parts[0])
        return "?"

    def _abbreviate_type(self, type_str: str) -> str:
        """Abbreviate type name for compact display"""
        # Remove namespace qualifiers
        if "." in type_str:
            type_str = type_str.split(".")[-1]

        # Common abbreviations
        abbrev_map = {
            "String": "string",
            "Int32": "int",
            "Int64": "long",
            "Boolean": "bool",
            "Double": "double",
            "Decimal": "decimal",
            "DateTime": "DateTime",
            "Object": "object",
        }

        # Handle generic types
        if "<" in type_str:
            base_type = type_str.split("<")[0]
            base_type = abbrev_map.get(base_type, base_type)
            # Simplify generic parameters
            return f"{base_type}<T>"

        return abbrev_map.get(type_str, type_str)

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Convert visibility to symbol"""
        symbols = {
            "public": "+",
            "private": "-",
            "protected": "#",
            "internal": "~",
        }
        return symbols.get(visibility.lower(), "-")

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for C#"""
        lines = []

        # Header
        lines.append("Type,Name,Visibility,Lines,Signature,Complexity")

        # Classes
        for class_info in data.get("classes", []):
            name = class_info.get("name", "")
            visibility = class_info.get("visibility", "internal")
            line_range = class_info.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            class_type = class_info.get("class_type", "class")

            lines.append(f"Class,{name},{visibility},{lines_str},{class_type},")

        # Methods
        for method in data.get("methods", []):
            name = method.get("name", "")
            visibility = method.get("visibility", "private")
            line_range = method.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            params = method.get("parameters", [])
            return_type = method.get("return_type", "void")
            signature = f"({len(params)} params):{return_type}"
            complexity = method.get("complexity_score", 1)

            lines.append(
                f"Method,{name},{visibility},{lines_str},{signature},{complexity}"
            )

        # Fields
        for field in data.get("fields", []):
            name = field.get("name", "")
            visibility = field.get("visibility", "private")
            line = field.get("line_range", {}).get("start", 0)
            field_type = field.get("variable_type", "unknown")

            lines.append(f"Field,{name},{visibility},{line},{field_type},")

        return "\n".join(lines)
