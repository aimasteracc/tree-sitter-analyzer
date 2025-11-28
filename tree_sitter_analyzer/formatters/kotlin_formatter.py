#!/usr/bin/env python3
"""
Kotlin-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class KotlinTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Kotlin"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Kotlin"""
        lines = []

        # Header - Kotlin
        package_name = (data.get("package") or {}).get("name", "default")
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
        if package_name != "default":
            lines.append(f"# {package_name}.{file_name}")
        else:
            lines.append(f"# {file_name}")
        lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```kotlin")
            for imp in imports:
                lines.append(str(imp.get("statement", "")))
            lines.append("```")
            lines.append("")

        # Classes/Objects/Interfaces
        classes = data.get("classes", [])
        if classes:
            lines.append("## Classes & Objects")
            lines.append("| Name | Type | Visibility | Lines | Props | Methods |")
            lines.append("|------|------|------------|-------|-------|---------|")

            for cls in classes:
                name = str(cls.get("name", "Unknown"))
                cls_type = str(cls.get("type", "class"))
                visibility = str(cls.get("visibility", "public"))
                line_range = cls.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count props/methods within
                class_props = len(
                    [
                        p
                        for p in data.get("fields", [])
                        if line_range.get("start", 0)
                        <= p.get("line_range", {}).get("start", 0)
                        <= line_range.get("end", 0)
                    ]
                )
                class_methods = len(
                    [
                        m
                        for m in data.get("methods", [])
                        if line_range.get("start", 0)
                        <= m.get("line_range", {}).get("start", 0)
                        <= line_range.get("end", 0)
                    ]
                )

                lines.append(
                    f"| {name} | {cls_type} | {visibility} | {lines_str} | {class_props} | {class_methods} |"
                )
            lines.append("")

        # Top-level Functions
        # We want to list all functions, but maybe group them or just list them.
        # BaseTableFormatter lists all methods in data.get("methods") usually.
        fns = data.get("methods", [])
        if fns:
            lines.append("## Functions")
            lines.append("| Function | Signature | Vis | Lines | Suspend | Doc |")
            lines.append("|----------|-----------|-----|-------|---------|-----|")

            for fn in fns:
                lines.append(self._format_fn_row(fn))
            lines.append("")

        # Top-level Properties
        props = data.get("fields", [])  # Mapped to fields
        if props:
            lines.append("## Properties")
            lines.append("| Name | Type | Vis | Kind | Line | Doc |")
            lines.append("|------|------|-----|------|------|-----|")

            for prop in props:
                lines.append(self._format_prop_row(prop))
            lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Kotlin"""
        lines = []

        # Header
        package_name = (data.get("package") or {}).get("name", "default")
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
        if package_name != "default":
            lines.append(f"# {package_name}.{file_name}")
        else:
            lines.append(f"# {file_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Package | {package_name} |")
        lines.append(f"| Classes | {len(data.get('classes', []))} |")
        lines.append(f"| Functions | {stats.get('method_count', 0)} |")
        lines.append(f"| Properties | {stats.get('field_count', 0)} |")
        lines.append("")

        # Functions (compact)
        fns = data.get("methods", [])
        if fns:
            lines.append("## Functions")
            lines.append("| Fn | Sig | V | S | L | Doc |")
            lines.append("|----|-----|---|---|---|-----|")

            for fn in fns:
                name = str(fn.get("name", ""))
                signature = self._create_compact_signature(fn)
                visibility = self._convert_visibility(str(fn.get("visibility", "")))
                is_suspend = "Y" if fn.get("is_suspend", False) else "-"
                line_range = fn.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                doc = self._clean_csv_text(
                    self._extract_doc_summary(str(fn.get("docstring", "") or ""))
                )

                lines.append(
                    f"| {name} | {signature} | {visibility} | {is_suspend} | {lines_str} | {doc} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _format_fn_row(self, fn: dict[str, Any]) -> str:
        """Format a function table row for Kotlin"""
        name = str(fn.get("name", ""))
        signature = self._create_full_signature(fn)
        visibility = self._convert_visibility(str(fn.get("visibility", "")))
        is_suspend = "Yes" if fn.get("is_suspend", False) else "-"
        line_range = fn.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(fn.get("docstring", "") or ""))
        )

        return f"| {name} | {signature} | {visibility} | {lines_str} | {is_suspend} | {doc} |"

    def _format_prop_row(self, prop: dict[str, Any]) -> str:
        """Format a property table row for Kotlin"""
        name = str(prop.get("name", ""))
        prop_type = str(prop.get("type", ""))
        visibility = self._convert_visibility(str(prop.get("visibility", "")))
        # Check val/var if extracted
        kind = (
            "val"
            if prop.get("is_val", False)
            else ("var" if prop.get("is_var", False) else "-")
        )
        line = prop.get("line_range", {}).get("start", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(prop.get("docstring", "") or ""))
        )

        return f"| {name} | {prop_type} | {visibility} | {kind} | {line} | {doc} |"

    def _create_full_signature(self, fn: dict[str, Any]) -> str:
        """Create full function signature for Kotlin"""
        # Kotlin: fun name(p1: T1, p2: T2): R
        params = fn.get("parameters", [])
        params_str_list = []
        for p in params:
            if isinstance(p, dict):
                # "name: type" is expected
                params_str_list.append(f"{p.get('name')}: {p.get('type')}")
            else:
                params_str_list.append(str(p))

        params_str = ", ".join(params_str_list)
        return_type = fn.get("return_type", "")
        ret_str = f": {return_type}" if return_type and return_type != "Unit" else ""

        return f"fun({params_str}){ret_str}"

    def _create_compact_signature(self, fn: dict[str, Any]) -> str:
        """Create compact function signature for Kotlin"""
        params = fn.get("parameters", [])
        params_summary = f"({len(params)})"
        return_type = fn.get("return_type", "")
        ret_str = f":{return_type}" if return_type and return_type != "Unit" else ""

        return f"{params_summary}{ret_str}"

    def _convert_visibility(self, visibility: str) -> str:
        """Convert visibility to short symbol"""
        if visibility == "public":
            return "pub"
        elif visibility == "private":
            return "priv"
        elif visibility == "protected":
            return "prot"
        elif visibility == "internal":
            return "int"
        return visibility

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Kotlin"""
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
        """Format summary output for Kotlin"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Kotlin"""
        if self.format_type == "compact":
            return self._format_compact_table(analysis_result)
        return self._format_full_table(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Kotlin"""
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
