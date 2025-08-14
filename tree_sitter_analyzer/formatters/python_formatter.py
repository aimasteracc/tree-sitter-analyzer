#!/usr/bin/env python3
"""
Python-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class PythonTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Python"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Python"""
        lines = []

        # Header - Python (multi-class supported)
        classes = data.get("classes", [])
        if len(classes) > 1:
            # If multiple classes exist, use filename
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            lines.append(f"# {file_name}")
        else:
            # Single class: use class name
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            lines.append(f"# {class_name}")
        lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```python")
            for imp in imports:
                lines.append(str(imp.get("statement", "")))
            lines.append("```")
            lines.append("")

        # Classes - Python (multi-class aware)
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

            lines.append("| Package | (default) |")
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

        # Methods - Python (no constructor separation)
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")

            for method in methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Python"""
        lines = []

        # Header
        classes = data.get("classes", [])
        if len(classes) > 1:
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            lines.append(f"# {file_name}")
        else:
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            lines.append(f"# {class_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Classes | {len(classes)} |")
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
        """Format a method table row for Python"""
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
        """Create compact method signature for Python"""
        params = method.get("parameters", [])
        param_types = []

        for p in params:
            if isinstance(p, dict):
                param_types.append(self._shorten_type(p.get("type", "Any")))
            else:
                param_types.append("Any")

        params_str = ",".join(param_types)
        return_type = self._shorten_type(method.get("return_type", "Any"))

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for Python tables"""
        if type_name is None:
            return "Any"

        if not isinstance(type_name, str):
            type_name = str(type_name)

        type_mapping = {
            "str": "s",
            "int": "i",
            "float": "f",
            "bool": "b",
            "None": "N",
            "Any": "A",
            "List": "L",
            "Dict": "D",
            "Optional": "O",
            "Union": "U",
        }

        # List[str] -> L[s]
        if "List[" in type_name:
            result = (
                type_name.replace("List[", "L[").replace("str", "s").replace("int", "i")
            )
            return str(result)

        # Dict[str, int] -> D[s,i]
        if "Dict[" in type_name:
            result = (
                type_name.replace("Dict[", "D[").replace("str", "s").replace("int", "i")
            )
            return str(result)

        # Optional[str] -> O[s]
        if "Optional[" in type_name:
            result = type_name.replace("Optional[", "O[").replace("str", "s")
            return str(result)

        result = type_mapping.get(
            type_name, type_name[:3] if len(type_name) > 3 else type_name
        )
        return str(result)
