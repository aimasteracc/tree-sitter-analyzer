#!/usr/bin/env python3
"""
Java-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class JavaTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Java"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Java - matches golden master format"""
        lines: list[str] = []

        # Get package and classes
        package_name = (data.get("package") or {}).get("name", "")
        classes = data.get("classes", [])

        # Header - use package.FileName format (from file_path, without extension)
        file_path = data.get("file_path", "")
        if file_path:
            # Extract filename without extension
            file_name = file_path.split("/")[-1].split("\\")[-1]
            if file_name.endswith(".java"):
                file_name = file_name[:-5]
            if package_name:
                lines.append(f"# {package_name}.{file_name}")
            else:
                lines.append(f"# {file_name}")
        elif classes:
            # Fallback to first class name if no file path
            main_classes = [c for c in classes if not self._is_inner_class(c, classes)]
            main_class = main_classes[0] if main_classes else classes[0]
            class_name = main_class.get("name", "Unknown")
            if package_name:
                lines.append(f"# {package_name}.{class_name}")
            else:
                lines.append(f"# {class_name}")
        else:
            lines.append("# Unknown")
        lines.append("")

        # Package section
        if package_name:
            lines.append("## Package")
            lines.append(f"`{package_name}`")
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

        # Determine if this is a single-class or multi-class file
        # Filter out inner classes for this determination
        top_level_classes = [c for c in classes if not self._is_inner_class(c, classes)]

        if len(top_level_classes) == 1:
            # Single class format: use Class Info property table
            single_class = top_level_classes[0]
            stats = data.get("statistics") or {}

            lines.append("## Class Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append(f"| Package | {package_name} |")
            lines.append(f"| Type | {single_class.get('type', 'class')} |")
            lines.append(
                f"| Visibility | {single_class.get('visibility', 'package')} |"
            )
            line_range = single_class.get("line_range", {})
            lines.append(
                f"| Lines | {line_range.get('start', 0)}-{line_range.get('end', 0)} |"
            )
            lines.append(f"| Total Methods | {stats.get('method_count', 0)} |")
            lines.append(f"| Total Fields | {stats.get('field_count', 0)} |")
            lines.append("")

            # Generate section for the single class
            class_lines = self._format_class_section(single_class, data, classes)
            lines.extend(class_lines)
        else:
            # Multi-class format: use Classes Overview table
            if classes:
                lines.append("## Classes Overview")
                lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
                lines.append("|-------|------|------------|-------|---------|--------|")

                for class_info in classes:
                    name = str(class_info.get("name", "Unknown"))
                    class_type = str(class_info.get("type", "class"))
                    visibility = str(class_info.get("visibility", "package"))
                    line_range = class_info.get("line_range", {})
                    lines_str = (
                        f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                    )

                    # Count methods/fields within the class range
                    class_methods = self._get_class_methods(
                        data.get("methods", []), line_range
                    )
                    class_fields = self._get_class_fields(
                        data.get("fields", []), line_range
                    )

                    # Exclude inner class methods/fields from parent class count
                    inner_classes = self._get_inner_classes(class_info, classes)
                    for inner in inner_classes:
                        inner_range = inner.get("line_range", {})
                        class_methods = [
                            m
                            for m in class_methods
                            if not self._is_in_range(
                                m.get("line_range", {}), inner_range
                            )
                        ]
                        class_fields = [
                            f
                            for f in class_fields
                            if not self._is_in_range(
                                f.get("line_range", {}), inner_range
                            )
                        ]

                    lines.append(
                        f"| {name} | {class_type} | {visibility} | "
                        f"{lines_str} | {len(class_methods)} | {len(class_fields)} |"
                    )
                lines.append("")

            # Generate per-class sections
            for class_info in classes:
                class_lines = self._format_class_section(class_info, data, classes)
                lines.extend(class_lines)

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_class_section(
        self,
        class_info: dict[str, Any],
        data: dict[str, Any],
        all_classes: list[dict[str, Any]],
    ) -> list[str]:
        """Format a single class section with its fields and methods"""
        lines: list[str] = []

        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)

        # Section header with line range
        lines.append(f"## {name} ({start}-{end})")

        # Get methods and fields for this class
        class_methods = self._get_class_methods(data.get("methods", []), line_range)
        class_fields = self._get_class_fields(data.get("fields", []), line_range)

        # Exclude inner class methods/fields
        inner_classes = self._get_inner_classes(class_info, all_classes)
        for inner in inner_classes:
            inner_range = inner.get("line_range", {})
            class_methods = [
                m
                for m in class_methods
                if not self._is_in_range(m.get("line_range", {}), inner_range)
            ]
            class_fields = [
                f
                for f in class_fields
                if not self._is_in_range(f.get("line_range", {}), inner_range)
            ]

        # Fields section
        if class_fields:
            lines.append("### Fields")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")

            for field in class_fields:
                field_name = str(field.get("name", ""))
                field_type = str(field.get("type", ""))
                visibility = self._convert_visibility(str(field.get("visibility", "")))
                modifiers = ",".join([str(m) for m in field.get("modifiers", [])])
                line = field.get("line_range", {}).get("start", 0)
                doc = str(field.get("javadoc", "")) or "-"
                doc = doc.replace("\n", " ").replace("|", "\\|")[:50]
                if not doc or doc == "None":
                    doc = "-"

                lines.append(
                    f"| {field_name} | {field_type} | {visibility} | "
                    f"{modifiers} | {line} | {doc} |"
                )
            lines.append("")

        # Constructors section
        constructors = [m for m in class_methods if m.get("is_constructor", False)]
        if constructors:
            lines.append("### Constructors")
            lines.append("| Constructor | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|-------------|-----------|-----|-------|----|----|")

            for method in constructors:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Group remaining methods by visibility
        non_constructors = [
            m for m in class_methods if not m.get("is_constructor", False)
        ]

        # Public Methods
        public_methods = [
            m for m in non_constructors if str(m.get("visibility", "")) == "public"
        ]
        if public_methods:
            lines.append("### Public Methods")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----|")
            for method in public_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Protected Methods
        protected_methods = [
            m for m in non_constructors if str(m.get("visibility", "")) == "protected"
        ]
        if protected_methods:
            lines.append("### Protected Methods")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----|")
            for method in protected_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Package Methods (default visibility)
        package_methods = [
            m
            for m in non_constructors
            if str(m.get("visibility", "")) in ("package", "default", "")
        ]
        if package_methods:
            lines.append("### Package Methods")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----|")
            for method in package_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Private Methods
        private_methods = [
            m for m in non_constructors if str(m.get("visibility", "")) == "private"
        ]
        if private_methods:
            lines.append("### Private Methods")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----|")
            for method in private_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        return lines

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for Java (golden master format)"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)
        lines_str = f"{start}-{end}"
        complexity = method.get("complexity_score", 1)
        doc = str(method.get("javadoc", "")) or "-"
        doc = doc.replace("\n", " ").replace("|", "\\|")[:50]
        if not doc or doc == "None":
            doc = "-"

        return f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"

    def _get_class_methods(
        self, methods: list[dict[str, Any]], class_range: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get methods that belong to a class based on line range"""
        start = class_range.get("start", 0)
        end = class_range.get("end", 0)
        return [
            m
            for m in methods
            if start <= m.get("line_range", {}).get("start", 0) <= end
        ]

    def _get_class_fields(
        self, fields: list[dict[str, Any]], class_range: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get fields that belong to a class based on line range"""
        start = class_range.get("start", 0)
        end = class_range.get("end", 0)
        return [
            f for f in fields if start <= f.get("line_range", {}).get("start", 0) <= end
        ]

    def _get_inner_classes(
        self, parent_class: dict[str, Any], all_classes: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Get inner classes of a parent class"""
        parent_range = parent_class.get("line_range", {})
        parent_start = parent_range.get("start", 0)
        parent_end = parent_range.get("end", 0)

        inner_classes = []
        for c in all_classes:
            if c is parent_class:
                continue
            c_range = c.get("line_range", {})
            c_start = c_range.get("start", 0)
            c_end = c_range.get("end", 0)
            # Inner class is fully contained within parent
            if parent_start < c_start and c_end < parent_end:
                inner_classes.append(c)

        return inner_classes

    def _is_inner_class(
        self, class_info: dict[str, Any], all_classes: list[dict[str, Any]]
    ) -> bool:
        """Check if a class is an inner class of another class"""
        c_range = class_info.get("line_range", {})
        c_start = c_range.get("start", 0)
        c_end = c_range.get("end", 0)

        for parent in all_classes:
            if parent is class_info:
                continue
            p_range = parent.get("line_range", {})
            p_start = p_range.get("start", 0)
            p_end = p_range.get("end", 0)
            # This class is fully contained within parent
            if p_start < c_start and c_end < p_end:
                return True

        return False

    def _is_in_range(
        self, item_range: dict[str, Any], container_range: dict[str, Any]
    ) -> bool:
        """Check if an item's line range is within a container's range"""
        item_start = int(item_range.get("start", 0))
        container_start = int(container_range.get("start", 0))
        container_end = int(container_range.get("end", 0))
        return container_start <= item_start <= container_end

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Java"""
        # Set the format type based on table_type parameter
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            # Use the existing format_structure method
            return self.format_structure(analysis_result)
        finally:
            # Restore original format type
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Java"""
        return self._format_full_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Java"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "toon"
    ) -> str:
        """Format advanced analysis output for Java"""
        if output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)
