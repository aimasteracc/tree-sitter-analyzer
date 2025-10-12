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
            lines.append(f"# {package_name}.{file_name}")
        else:
            # Single class: use class name
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
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
                visibility = str(class_info.get("visibility", "public"))
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
                f"| Visibility | {str(class_info.get('visibility', 'public'))} |"
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
        class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
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
        param_types = []
        
        for p in params:
            if isinstance(p, dict):
                param_type = p.get("type")
                if param_type:
                    param_types.append(self._shorten_type(param_type))
                else:
                    param_types.append("O")
            elif isinstance(p, str) and p.strip():
                param_types.append(self._shorten_type(p))
            else:
                param_types.append("O")
        
        params_str = ",".join(param_types) if param_types else ""
        return_type = self._shorten_type(method.get("return_type", "void"))

        # Add modifiers if present
        modifiers = method.get("modifiers", [])
        modifier_str = ""
        if modifiers:
            static_mods = [m for m in modifiers if m in ["static", "abstract", "final"]]
            if static_mods:
                modifier_str = f" [{','.join(static_mods)}]"

        return f"({params_str}):{return_type}{modifier_str}"

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

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create full method signature for Java"""
        params = method.get("parameters", [])
        param_strs = []
        
        for param in params:
            if isinstance(param, dict):
                param_name = param.get("name", "param")
                param_type = param.get("type", "Object")
                if param_name and param_type:
                    param_strs.append(f"{param_name}:{param_type}")
                elif param_type:
                    param_strs.append(f"param:{param_type}")
                else:
                    param_strs.append("param:Object")
            elif isinstance(param, str) and param.strip():
                param_strs.append(f"param:{param}")
            else:
                param_strs.append("param:Object")
        
        params_str = ",".join(param_strs) if param_strs else ""
        return_type = method.get("return_type", "void")
        
        # Add modifiers if present
        modifiers = method.get("modifiers", [])
        modifier_str = ""
        if modifiers:
            static_mods = [m for m in modifiers if m in ["static", "abstract", "final", "synchronized"]]
            if static_mods:
                modifier_str = f" [{','.join(static_mods)}]"
        
        return f"({params_str}):{return_type}{modifier_str}"
