#!/usr/bin/env python3
"""
Ruby-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class RubyTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Ruby"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Ruby"""
        lines = []

        # Header - Ruby (multi-class supported)
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

        # Require statements (imports)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```ruby")
            for imp in imports:
                import_text = imp.get("raw_text", "").strip()
                if import_text:
                    lines.append(import_text)
            lines.append("```")
            lines.append("")

        # Class Info - Ruby (multi-class aware)
        if len(classes) > 1:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Lines | Methods | Constants |")
            lines.append("|-------|------|-------|---------|-----------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("class_type", "class"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods/constants within the class range
                class_methods = [
                    m
                    for m in data.get("methods", [])
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]
                class_constants = [
                    f
                    for f in data.get("fields", [])
                    if f.get("is_constant", False)
                    and line_range.get("start", 0)
                    <= f.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]

                lines.append(
                    f"| {name} | {class_type} | {lines_str} | {len(class_methods)} | {len(class_constants)} |"
                )
        else:
            # Single class details
            lines.append("## Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")

            class_info = data.get("classes", [{}])[0] if data.get("classes") else {}
            stats = data.get("statistics") or {}

            lines.append(f"| Type | {str(class_info.get('class_type', 'class'))} |")
            lines.append(f"| Methods | {stats.get('method_count', 0)} |")
            lines.append(
                f"| Constants | {sum(1 for f in data.get('fields', []) if f.get('is_constant', False))} |"
            )

        lines.append("")

        # Methods
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append("| Name | Type | Lines | Parameters |")
            lines.append("|------|------|-------|------------|")

            for method in methods:
                name = str(method.get("name", "Unknown"))
                metadata = method.get("metadata", {})
                method_type = metadata.get("method_type", "instance")
                attr_type = metadata.get("attr_type", "")

                # Determine display type
                if attr_type:
                    display_type = attr_type
                elif method_type == "class":
                    display_type = "class method"
                else:
                    display_type = "instance method"

                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                params = ", ".join(method.get("parameters", []))

                lines.append(f"| {name} | {display_type} | {lines_str} | {params} |")

        lines.append("")

        # Variables (Constants, Instance Variables, Class Variables)
        fields = data.get("fields", [])
        if fields:
            lines.append("## Variables")
            lines.append("| Name | Type | Visibility | Lines |")
            lines.append("|------|------|------------|-------|")

            for field in fields:
                name = str(field.get("name", "Unknown"))
                metadata = field.get("metadata", {})

                # Determine variable type
                if field.get("is_constant", False):
                    var_type = "constant"
                elif metadata.get("is_class_variable", False):
                    var_type = "class variable"
                elif metadata.get("is_instance_variable", False):
                    var_type = "instance variable"
                elif metadata.get("is_global", False):
                    var_type = "global variable"
                else:
                    var_type = "variable"

                visibility = str(field.get("visibility", "public"))
                line_range = field.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                lines.append(f"| {name} | {var_type} | {visibility} | {lines_str} |")

        lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Ruby"""
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

        # Statistics
        stats = data.get("statistics") or {}
        lines.append("## Statistics")
        lines.append(f"- Classes: {stats.get('class_count', 0)}")
        lines.append(f"- Methods: {stats.get('method_count', 0)}")
        lines.append(
            f"- Constants: {sum(1 for f in data.get('fields', []) if f.get('is_constant', False))}"
        )
        lines.append(f"- Imports: {len(data.get('imports', []))}")
        lines.append("")

        # Classes
        if classes:
            lines.append("## Classes")
            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("class_type", "class"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                lines.append(f"- **{name}** ({class_type}) - Lines {lines_str}")
            lines.append("")

        # Methods
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            for method in methods:
                name = str(method.get("name", "Unknown"))
                metadata = method.get("metadata", {})
                method_type = metadata.get("method_type", "instance")
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                type_prefix = "." if method_type == "class" else "#"
                lines.append(f"- {type_prefix}{name} - Lines {lines_str}")
            lines.append("")

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for Ruby"""
        lines = []

        # Header
        lines.append("Type,Name,Additional,Lines")

        # Classes
        for class_info in data.get("classes", []):
            name = str(class_info.get("name", "Unknown"))
            class_type = str(class_info.get("class_type", "class"))
            line_range = class_info.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            lines.append(f"{class_type},{name},,{lines_str}")

        # Methods
        for method in data.get("methods", []):
            name = str(method.get("name", "Unknown"))
            metadata = method.get("metadata", {})
            method_type = metadata.get("method_type", "instance")
            attr_type = metadata.get("attr_type", "")
            line_range = method.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

            additional = attr_type if attr_type else method_type
            lines.append(f"method,{name},{additional},{lines_str}")

        # Variables
        for field in data.get("fields", []):
            name = str(field.get("name", "Unknown"))
            metadata = field.get("metadata", {})

            # Determine variable type
            if field.get("is_constant", False):
                var_type = "constant"
            elif metadata.get("is_class_variable", False):
                var_type = "class_variable"
            elif metadata.get("is_instance_variable", False):
                var_type = "instance_variable"
            else:
                var_type = "variable"

            line_range = field.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            lines.append(f"{var_type},{name},,{lines_str}")

        return "\n".join(lines)


class RubyFullFormatter(RubyTableFormatter):
    """Full table formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as full table"""
        return self._format_full_table(data)


class RubyCompactFormatter(RubyTableFormatter):
    """Compact table formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as compact table"""
        return self._format_compact_table(data)


class RubyCSVFormatter(RubyTableFormatter):
    """CSV formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as CSV"""
        return self._format_csv(data)
