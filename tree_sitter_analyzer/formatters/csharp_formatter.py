#!/usr/bin/env python3
"""
C#-specific table formatter.
"""

from typing import Any

from ._csharp_formatter_helpers import (
    format_csharp_compact_table,
    format_csharp_csv,
    format_csharp_full_table,
)
from .base_formatter import BaseTableFormatter


class CSharpTableFormatter(BaseTableFormatter):
    """Table formatter specialized for C#"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for C# - matches golden master format"""
        return format_csharp_full_table(
            data,
            self._get_class_methods,
            self._get_class_fields,
            self._format_modifiers,
            self._convert_visibility,
            self._format_method_row,
        )

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for C# - matches golden master format"""
        return format_csharp_compact_table(
            data,
            self._extract_namespace,
            self._create_compact_signature,
            self._convert_visibility,
        )

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for C# - matches golden master format"""
        return format_csharp_csv(data, self._create_full_signature)

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
