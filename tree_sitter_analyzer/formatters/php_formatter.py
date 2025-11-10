#!/usr/bin/env python3
"""
PHP-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class PHPTableFormatter(BaseTableFormatter):
    """Table formatter specialized for PHP"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for PHP"""
        lines = []

        # Header - PHP (multi-class supported)
        classes = data.get("classes", [])
        namespace_name = self._extract_namespace(data)

        if len(classes) > 1:
            # If multiple classes exist, use filename
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            if namespace_name == "unknown":
                lines.append(f"# {file_name}")
            else:
                lines.append(f"# {namespace_name}\\{file_name}")
        else:
            # Single class: use class name
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            if namespace_name == "unknown":
                lines.append(f"# {class_name}")
            else:
                lines.append(f"# {namespace_name}\\{class_name}")
        lines.append("")

        # Use statements (imports)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```php")
            for imp in imports:
                import_text = imp.get("raw_text", "").strip()
                if import_text:
                    lines.append(import_text)
            lines.append("```")
            lines.append("")

        # Class Info - PHP (multi-class aware)
        if len(classes) > 1:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Properties |")
            lines.append("|-------|------|------------|-------|---------|------------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("class_type", "class"))
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods/properties within the class range
                class_methods = [
                    m
                    for m in data.get("methods", [])
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]
                class_properties = [
                    f
                    for f in data.get("fields", [])
                    if line_range.get("start", 0)
                    <= f.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_properties)} |"
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
                f"| Visibility | {str(class_info.get('visibility', 'public'))} |"
            )
            lines.append(f"| Methods | {stats.get('method_count', 0)} |")
            lines.append(f"| Properties | {stats.get('field_count', 0)} |")

        lines.append("")

        # Methods
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append(
                "| Name | Visibility | Static | Lines | Parameters | Return Type |"
            )
            lines.append(
                "|------|------------|--------|-------|------------|-------------|"
            )

            for method in methods:
                name = str(method.get("name", "Unknown"))
                visibility = str(method.get("visibility", "public"))
                is_static = "✓" if method.get("is_static", False) else ""
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                params = ", ".join(method.get("parameters", []))
                return_type = str(method.get("return_type", "void"))

                # Highlight magic methods
                if name.startswith("__"):
                    name = f"**{name}**"

                lines.append(
                    f"| {name} | {visibility} | {is_static} | {lines_str} | {params} | {return_type} |"
                )

        lines.append("")

        # Properties
        fields = data.get("fields", [])
        if fields:
            lines.append("## Properties")
            lines.append("| Name | Visibility | Type | Static | Readonly | Lines |")
            lines.append("|------|------------|------|--------|----------|-------|")

            for field in fields:
                name = str(field.get("name", "Unknown"))
                visibility = str(field.get("visibility", "public"))
                field_type = str(field.get("type", "mixed"))
                is_static = "✓" if field.get("is_static", False) else ""
                is_readonly = "✓" if field.get("is_readonly", False) else ""
                line_range = field.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                lines.append(
                    f"| {name} | {visibility} | {field_type} | {is_static} | {is_readonly} | {lines_str} |"
                )

        lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for PHP"""
        lines = []

        # Header
        classes = data.get("classes", [])
        namespace_name = self._extract_namespace(data)

        if len(classes) > 1:
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            if namespace_name == "unknown":
                lines.append(f"# {file_name}")
            else:
                lines.append(f"# {namespace_name}\\{file_name}")
        else:
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            if namespace_name == "unknown":
                lines.append(f"# {class_name}")
            else:
                lines.append(f"# {namespace_name}\\{class_name}")
        lines.append("")

        # Statistics
        stats = data.get("statistics") or {}
        lines.append("## Statistics")
        lines.append(f"- Classes: {stats.get('class_count', 0)}")
        lines.append(f"- Methods: {stats.get('method_count', 0)}")
        lines.append(f"- Properties: {stats.get('field_count', 0)}")
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
                visibility = str(method.get("visibility", "public"))
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Highlight magic methods
                if name.startswith("__"):
                    name = f"**{name}**"

                lines.append(f"- {visibility} {name} - Lines {lines_str}")
            lines.append("")

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for PHP"""
        lines = []

        # Header
        lines.append("Type,Name,Visibility,Lines,Additional")

        # Classes
        for class_info in data.get("classes", []):
            name = str(class_info.get("name", "Unknown"))
            class_type = str(class_info.get("class_type", "class"))
            visibility = str(class_info.get("visibility", "public"))
            line_range = class_info.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            lines.append(f"{class_type},{name},{visibility},{lines_str},")

        # Methods
        for method in data.get("methods", []):
            name = str(method.get("name", "Unknown"))
            visibility = str(method.get("visibility", "public"))
            line_range = method.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            return_type = str(method.get("return_type", "void"))
            is_static = "static" if method.get("is_static", False) else ""
            additional = f"{is_static} {return_type}".strip()
            lines.append(f"method,{name},{visibility},{lines_str},{additional}")

        # Properties
        for field in data.get("fields", []):
            name = str(field.get("name", "Unknown"))
            visibility = str(field.get("visibility", "public"))
            line_range = field.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            field_type = str(field.get("type", "mixed"))
            is_static = "static" if field.get("is_static", False) else ""
            is_readonly = "readonly" if field.get("is_readonly", False) else ""
            additional = f"{is_static} {is_readonly} {field_type}".strip()
            lines.append(f"property,{name},{visibility},{lines_str},{additional}")

        return "\n".join(lines)

    def _extract_namespace(self, data: dict[str, Any]) -> str:
        """Extract namespace from data"""
        # Try to get namespace from classes
        classes = data.get("classes", [])
        if classes:
            for class_info in classes:
                metadata = class_info.get("metadata", {})
                namespace = metadata.get("namespace", "")
                if namespace:
                    return namespace

        # Try to get from methods
        methods = data.get("methods", [])
        if methods:
            for method in methods:
                metadata = method.get("metadata", {})
                namespace = metadata.get("namespace", "")
                if namespace:
                    return namespace

        return "unknown"


class PHPFullFormatter(PHPTableFormatter):
    """Full table formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as full table"""
        return self._format_full_table(data)


class PHPCompactFormatter(PHPTableFormatter):
    """Compact table formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as compact table"""
        return self._format_compact_table(data)


class PHPCSVFormatter(PHPTableFormatter):
    """CSV formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as CSV"""
        return self._format_csv(data)
