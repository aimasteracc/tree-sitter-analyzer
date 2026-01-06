#!/usr/bin/env python3
"""
TypeScript-specific table formatter.

Provides specialized formatting for TypeScript code analysis results,
handling TypeScript-specific features like interfaces, type aliases, enums,
generics, decorators, and modern JavaScript features with type annotations.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class TypeScriptTableFormatter(BaseTableFormatter):
    """Table formatter specialized for TypeScript"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data using the configured format type"""
        return self.format_structure(data)

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for TypeScript - matches golden master format"""
        lines: list[str] = []

        # Get classes/types from data
        classes = data.get("classes", [])
        methods = data.get("methods", []) or data.get("functions", [])
        fields = data.get("fields", []) or data.get("variables", [])

        # Header - use first class/type name (no file extension)
        if classes:
            first_class = classes[0]
            class_name = str(first_class.get("name", "Unknown"))
            lines.append(f"# {class_name}")
        else:
            file_path = data.get("file_path", "Unknown")
            file_name = str(file_path).split("/")[-1].split("\\")[-1]
            module_name = (
                file_name.replace(".ts", "").replace(".tsx", "").replace(".d.ts", "")
            )
            lines.append(f"# {module_name}")
        lines.append("")

        # Classes Overview table
        if classes:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(
                    class_info.get("class_type", "") or class_info.get("type", "class")
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
                        str(field.get("visibility", "public"))
                    )
                    modifiers = self._format_modifiers(field)
                    field_line_range = field.get("line_range", {})
                    line = field_line_range.get("start", 0)
                    doc = (
                        self._extract_doc_summary(
                            str(field.get("javadoc", "") or field.get("doc", ""))
                        )
                        or "-"
                    )

                    lines.append(
                        f"| {name} | {field_type} | {visibility} | {modifiers} | "
                        f"{line} | {doc} |"
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
        """Compact table format for TypeScript - matches golden master format"""
        lines: list[str] = []

        # Get classes from data
        classes = data.get("classes", [])
        methods = data.get("methods", []) or data.get("functions", [])
        fields = data.get("fields", []) or data.get("variables", [])

        # Header - use first class name
        if classes:
            first_class = classes[0]
            class_name = str(first_class.get("name", "Unknown"))
            lines.append(f"# {class_name}")
        else:
            file_path = data.get("file_path", "Unknown")
            file_name = str(file_path).split("/")[-1].split("\\")[-1]
            module_name = file_name.replace(".ts", "").replace(".tsx", "")
            lines.append(f"# {module_name}")
        lines.append("")

        # Info section
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")

        # Get package name if available
        package_name = (data.get("package") or {}).get("name", "")
        lines.append(f"| Package | {package_name} |")
        lines.append(f"| Methods | {len(methods)} |")
        lines.append(f"| Fields | {len(fields)} |")
        lines.append("")

        # Methods section
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
                complexity = method.get("complexity_score", 0)
                doc = (
                    self._extract_doc_summary(
                        str(method.get("javadoc", "") or method.get("doc", ""))
                    )
                    or "-"
                )

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
        """CSV format for TypeScript - matches golden master format"""
        lines: list[str] = []

        # Header
        lines.append("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

        # Fields
        fields = data.get("fields", []) or data.get("variables", [])
        for field in fields:
            name = str(field.get("name", ""))
            field_type = str(
                field.get("type", "")
                or field.get("field_type", "")
                or field.get("variable_type", "")
            )
            signature = f"{name}:{field_type}" if field_type else name
            visibility = str(field.get("visibility", "public"))
            line_range = field.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            doc = (
                self._extract_doc_summary(
                    str(field.get("javadoc", "") or field.get("doc", ""))
                )
                or "-"
            )

            lines.append(f"Field,{name},{signature},{visibility},{lines_str},,{doc}")

        # Methods
        methods = data.get("methods", []) or data.get("functions", [])
        for method in methods:
            name = str(method.get("name", ""))
            is_constructor = method.get("is_constructor", False)
            method_type = "Constructor" if is_constructor else "Method"

            signature = self._create_csv_signature(method)
            visibility = str(method.get("visibility", "public"))
            line_range = method.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            complexity = method.get("complexity_score", 0)
            doc = (
                self._extract_doc_summary(
                    str(method.get("javadoc", "") or method.get("doc", ""))
                )
                or "-"
            )

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
        complexity = method.get("complexity_score", 0)
        doc = (
            self._extract_doc_summary(
                str(method.get("javadoc", "") or method.get("doc", ""))
            )
            or "-"
        )

        return f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create full method signature"""
        params = method.get("parameters", [])
        param_strs = []

        for p in params:
            if isinstance(p, dict):
                param_name = str(p.get("name", ""))
                param_type = str(p.get("type", "any"))
                # Include modifiers like 'public'
                modifiers = p.get("modifiers", [])
                if modifiers:
                    modifier_str = " ".join(str(m) for m in modifiers) + " "
                else:
                    modifier_str = ""
                param_strs.append(f"{modifier_str}{param_name}:{param_type}")
            else:
                param_strs.append(str(p))

        params_str = ", ".join(param_strs)
        return_type = str(method.get("return_type", "any"))

        return f"({params_str}):{return_type}"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature"""
        params = method.get("parameters", [])
        param_types = []

        for p in params:
            if isinstance(p, dict):
                param_type = str(p.get("type", "any"))
                param_types.append(param_type)
            else:
                param_types.append(str(p))

        params_str = ",".join(param_types)
        return_type = str(method.get("return_type", "any"))

        return f"({params_str}):{return_type}"

    def _create_csv_signature(self, method: dict[str, Any]) -> str:
        """Create CSV method signature with full parameter details"""
        params = method.get("parameters", [])
        param_strs = []

        for p in params:
            if isinstance(p, dict):
                param_name = str(p.get("name", ""))
                param_type = str(p.get("type", "any"))
                # Include modifiers like 'public'
                modifiers = p.get("modifiers", [])
                if modifiers:
                    modifier_str = " ".join(str(m) for m in modifiers) + " "
                else:
                    modifier_str = ""
                param_strs.append(f"{modifier_str}{param_name}:{param_type}")
            else:
                param_strs.append(str(p))

        params_str = ", ".join(param_strs)
        return_type = str(method.get("return_type", "any"))

        return f"({params_str}):{return_type}"

    def _format_modifiers(self, element: dict[str, Any]) -> str:
        """Format element modifiers"""
        modifiers = []
        if element.get("is_static"):
            modifiers.append("static")
        if element.get("is_readonly"):
            modifiers.append("readonly")
        if element.get("is_abstract"):
            modifiers.append("abstract")
        return " ".join(modifiers)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for TypeScript"""
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for TypeScript"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for TypeScript"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for TypeScript"""
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
