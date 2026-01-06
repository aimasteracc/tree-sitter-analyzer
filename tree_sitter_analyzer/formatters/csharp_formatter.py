#!/usr/bin/env python3
"""
C#-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class CSharpTableFormatter(BaseTableFormatter):
    """Table formatter specialized for C#"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for C# - matches golden master format"""
        lines: list[str] = []

        # Get file name for header
        file_path = data.get("file_path", "Unknown")
        file_name = str(file_path).split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
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

        # Get classes, methods, and fields
        classes = data.get("classes", [])
        methods = data.get("methods", [])
        fields = data.get("fields", [])

        # Classes Overview table
        if classes:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                # Check both "class_type" and "type" for compatibility
                class_type = str(
                    class_info.get("class_type", class_info.get("type", "class"))
                )
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods/fields within the class range
                class_methods = self._get_class_methods(methods, line_range)
                class_fields = self._get_class_fields(fields, line_range)

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | "
                    f"{len(class_methods)} | {len(class_fields)} |"
                )
            lines.append("")

        # Per-class sections
        for class_info in classes:
            class_name = str(class_info.get("name", "Unknown"))
            line_range = class_info.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

            lines.append(f"## {class_name} ({lines_str})")

            # Get methods/fields for this class
            class_methods = self._get_class_methods(methods, line_range)
            class_fields = self._get_class_fields(fields, line_range)

            # Fields section
            if class_fields:
                lines.append("### Fields")
                lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
                lines.append("|------|------|-----|-----------|------|-----|")

                for field in class_fields:
                    name = str(field.get("name", ""))
                    field_type = str(
                        field.get("type", "")
                        or field.get("field_type", "")
                        or field.get("variable_type", "")
                    )
                    visibility = self._convert_visibility(
                        str(field.get("visibility", "private"))
                    )
                    modifiers = self._format_modifiers(field)
                    field_line = field.get("line_range", {}).get("start", 0)
                    doc = "-"

                    lines.append(
                        f"| {name} | {field_type} | {visibility} | {modifiers} "
                        f"| {field_line} | {doc} |"
                    )
                lines.append("")

            # Group methods by type
            constructors = [m for m in class_methods if m.get("is_constructor", False)]
            public_methods = [
                m
                for m in class_methods
                if not m.get("is_constructor", False)
                and str(m.get("visibility", "public")).lower() == "public"
            ]
            private_methods = [
                m
                for m in class_methods
                if not m.get("is_constructor", False)
                and str(m.get("visibility", "")).lower() == "private"
            ]
            protected_methods = [
                m
                for m in class_methods
                if not m.get("is_constructor", False)
                and str(m.get("visibility", "")).lower() == "protected"
            ]

            # Constructors
            if constructors:
                lines.append("### Constructors")
                lines.append("| Constructor | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|-------------|-----------|-----|-------|----|----|")
                for method in constructors:
                    lines.append(self._format_method_row(method))
                lines.append("")

            # Public Methods
            if public_methods:
                lines.append("### Public Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for method in public_methods:
                    lines.append(self._format_method_row(method))
                lines.append("")

            # Protected Methods
            if protected_methods:
                lines.append("### Protected Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for method in protected_methods:
                    lines.append(self._format_method_row(method))
                lines.append("")

            # Private Methods
            if private_methods:
                lines.append("### Private Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for method in private_methods:
                    lines.append(self._format_method_row(method))
                lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for C# - matches golden master format"""
        lines: list[str] = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = str(file_path).split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Info
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")

        namespace_name = self._extract_namespace(data)
        stats = data.get("statistics") or {}

        lines.append(f"| Package | {namespace_name} |")
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
                signature = self._create_compact_signature(method)
                visibility = self._convert_visibility(
                    str(method.get("visibility", "public"))
                )
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 1)
                doc = "-"

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | "
                    f"{complexity} | {doc} |"
                )
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for C# - matches golden master format"""
        lines: list[str] = []

        # Header
        lines.append("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

        # Fields
        fields = data.get("fields", [])
        for field in fields:
            name = str(field.get("name", ""))
            field_type = str(
                field.get("type", "")
                or field.get("field_type", "")
                or field.get("variable_type", "")
            )
            signature = f"{name}:{field_type}" if field_type else name
            visibility = str(field.get("visibility", "private"))
            line_range = field.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            doc = "-"

            lines.append(f"Field,{name},{signature},{visibility},{lines_str},,{doc}")

        # Methods
        methods = data.get("methods", [])
        for method in methods:
            name = str(method.get("name", ""))
            is_constructor = method.get("is_constructor", False)
            method_type = "Constructor" if is_constructor else "Method"

            signature = self._create_full_signature(method)
            visibility = str(method.get("visibility", "public"))
            line_range = method.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            complexity = method.get("complexity_score", 1)
            doc = "-"

            # Add static modifier if applicable
            if method.get("is_static"):
                signature = f"{signature} [static]"

            # Escape signature if it contains commas
            if "," in signature:
                signature = f'"{signature}"'

            lines.append(
                f"{method_type},{name},{signature},{visibility},{lines_str},"
                f"{complexity},{doc}"
            )

        lines.append("")
        return "\n".join(lines)

    def _get_class_methods(
        self, methods: list[dict[str, Any]], line_range: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get methods within a class range"""
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)
        return [
            m
            for m in methods
            if start <= (m.get("line_range") or {}).get("start", 0) <= end
        ]

    def _get_class_fields(
        self, fields: list[dict[str, Any]], line_range: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get fields within a class range"""
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)
        return [
            f
            for f in fields
            if start <= (f.get("line_range") or {}).get("start", 0) <= end
        ]

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "public")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 1)
        doc = "-"

        return (
            f"| {name} | {signature} | {visibility} | {lines_str} | "
            f"{complexity} | {doc} |"
        )

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create full method signature"""
        params = method.get("parameters", [])
        param_strs = []

        for p in params:
            if isinstance(p, dict):
                param_name = str(p.get("name", ""))
                param_type = str(p.get("type", ""))
                if param_name and param_type:
                    param_strs.append(f"{param_name}:{param_type}")
                elif param_type:
                    param_strs.append(param_type)
                elif param_name:
                    param_strs.append(param_name)
            else:
                param_strs.append(str(p))

        params_str = ", ".join(param_strs)
        return_type = str(method.get("return_type", "void"))

        return f"({params_str}):{return_type}"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature"""
        params = method.get("parameters", [])
        param_types = []

        for p in params:
            if isinstance(p, dict):
                param_type = str(p.get("type", "Any"))
                param_types.append(self._abbreviate_type(param_type))
            else:
                param_types.append(str(p))

        # Limit to first 3 params
        if len(param_types) > 3:
            params_str = ",".join(param_types[:2]) + ",..."
        else:
            params_str = ",".join(param_types)

        return_type = str(method.get("return_type", "void"))
        ret_str = self._abbreviate_type(return_type)

        return f"({params_str}):{ret_str}"

    def _format_modifiers(self, element: dict[str, Any]) -> str:
        """Format element modifiers"""
        modifiers = []

        # Check visibility as modifier
        visibility = str(element.get("visibility", "")).lower()
        if visibility and visibility != "public":
            modifiers.append(visibility)

        # Check other modifiers
        if element.get("is_static"):
            modifiers.append("static")
        if element.get("is_readonly"):
            modifiers.append("readonly")
        if element.get("is_const"):
            modifiers.append("const")
        if element.get("is_abstract"):
            modifiers.append("abstract")

        # Also check modifiers list
        mod_list = element.get("modifiers", [])
        for m in mod_list:
            m_str = str(m).lower()
            if m_str not in modifiers:
                modifiers.append(m_str)

        return ",".join(modifiers)

    def _extract_namespace(self, data: dict[str, Any]) -> str:
        """Extract namespace from data"""
        # Try to get namespace from classes
        classes = data.get("classes", [])
        if classes:
            full_name = classes[0].get("full_qualified_name", "")
            if full_name and "." in full_name:
                parts = full_name.rsplit(".", 1)
                if len(parts) == 2:
                    return str(parts[0])
        return "unknown"

    def _abbreviate_type(self, type_str: str) -> str:
        """Abbreviate type name for compact display"""
        if not type_str:
            return "void"

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
            "integer": "i",
            "int": "i",
            "string": "string",
            "void": "void",
            "bool": "bool",
            "Any": "Any",
        }

        return abbrev_map.get(type_str, type_str)

    def _convert_visibility(self, visibility: str) -> str:
        """Convert visibility to symbol"""
        symbols = {
            "public": "+",
            "private": "-",
            "protected": "#",
            "internal": "~",
        }
        return symbols.get(visibility.lower(), "-")
